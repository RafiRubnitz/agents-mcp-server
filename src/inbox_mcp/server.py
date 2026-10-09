"""Inbox MCP server: MCP tools, the HTTP routes the Claude Code hooks call, and the UI."""

import functools
import hmac
import os
import socket
import sys
import threading
import time

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from . import consts, prompts
from .db import get_db_path
from .errors import InboxError, NetworkWithoutTokenError
from .logs import add_console, get_logger, get_logs_dir
from .models import Message
from .store import Store

log = get_logger(consts.LOG_SERVER)


def get_host() -> str:
    return os.environ.get(consts.ENV_HOST, consts.HOST)


def get_port() -> int:
    return int(os.environ.get(consts.ENV_PORT, consts.PORT))


def get_token() -> str | None:
    return os.environ.get(consts.ENV_TOKEN) or None


def is_loopback(host: str) -> bool:
    return host in consts.LOOPBACK_HOSTS


def check_exposure(host: str, token: str | None) -> None:
    """The server opens to the network only when a token guards it."""
    if not is_loopback(host) and not token:
        raise NetworkWithoutTokenError(host)


def network_urls(port: int) -> list[str]:
    """The addresses other computers can use to reach this server."""
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []
    return [f"http://{a}:{port}" for a in addresses if not is_loopback(a)]


class RequireToken:
    """ASGI middleware: every route that carries inbox data needs the access token."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self.expected = (consts.TOKEN_SCHEME + token).encode()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["path"] in consts.OPEN_ROUTES:
            await self.app(scope, receive, send)
            return
        given = dict(scope["headers"]).get(consts.HEADER_AUTHORIZATION.lower().encode(), b"")
        if hmac.compare_digest(given, self.expected):
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        log.warning(
            "request rejected",
            path=scope["path"],
            client=client[0] if client else None,
            token_sent=bool(given),
        )
        response = JSONResponse(consts.UNAUTHORIZED_BODY, status_code=consts.STATUS_UNAUTHORIZED)
        await response(scope, receive, send)


def loggable(arguments: dict) -> dict:
    """Tool arguments as log parameters: long strings are replaced by their length."""
    return {
        key: f"<{len(value)} chars>"
        if isinstance(value, str) and len(value) > consts.LOG_MAX_VALUE_CHARS
        else value
        for key, value in arguments.items()
    }


def logged_tool(fn):
    """Log every call of an MCP tool with its arguments and how it ended."""

    @functools.wraps(fn)
    def wrapper(**arguments):
        params = loggable(arguments)
        try:
            result = fn(**arguments)
        except InboxError as error:
            log.warning(
                "tool rejected", tool=fn.__name__, error=type(error).__name__, **params
            )
            raise
        log.info("tool called", tool=fn.__name__, **params)
        return result

    return wrapper


def format_message(msg: Message, full: bool = True) -> str:
    body = msg.body if full else msg.body.strip().splitlines()[0][: consts.PREVIEW_CHARS]
    return prompts.MESSAGE_LINE.format(
        id=msg.id,
        severity=msg.severity,
        sender=msg.from_name,
        thread_id=msg.thread_id,
        body=body,
    )


def note_transcript(store: Store, data: dict, host: str | None) -> str:
    """Record the transcript path every hook input carries; returns the session_id."""
    session_id = data.get("session_id", "")
    if session_id and data.get("transcript_path"):
        store.set_transcript(session_id, data["transcript_path"], host)
    return session_id




def create_app(store: Store, host: str = consts.HOST, token: str | None = None) -> Starlette:
    mcp = MCPServer(consts.SERVER_NAME, instructions=prompts.INSTRUCTIONS)

    @mcp.tool(description=prompts.TOOL_REGISTER)
    @logged_tool
    def register(session_id: str, name: str, description: str) -> str:
        session = store.register(session_id, name, description)
        return prompts.REGISTERED.format(name=session.name)

    @mcp.tool(description=prompts.TOOL_LIST_SESSIONS)
    @logged_tool
    def list_sessions() -> str:
        sessions = store.list_sessions()
        if not sessions:
            return prompts.NO_SESSIONS
        hosts = {s.session_id: store.host_of(s.session_id) for s in sessions}
        # The computer is only worth a mention when sessions run on more than one.
        line = (
            prompts.SESSION_LINE_WITH_HOST
            if len(set(hosts.values())) > 1
            else prompts.SESSION_LINE
        )
        return "\n".join(
            line.format(name=s.name, description=s.description, host=hosts[s.session_id])
            for s in sessions
        )

    @mcp.tool(description=prompts.TOOL_SEND)
    @logged_tool
    def send(
        session_id: str, to: str, severity: str, body: str, reply_to: int | None = None
    ) -> str:
        msg = store.send(session_id, to, severity, body, reply_to)
        return prompts.SENT.format(id=msg.id, to=to, thread_id=msg.thread_id)

    @mcp.tool(description=prompts.TOOL_COUNT)
    @logged_tool
    def count(session_id: str) -> str:
        counts = store.count(session_id)
        detail = ", ".join(
            prompts.COUNT_PART.format(count=counts[level], severity=level)
            for level in reversed(consts.SEVERITIES)
        )
        return prompts.COUNT.format(total=sum(counts.values()), detail=detail)

    @mcp.tool(description=prompts.TOOL_PICK)
    @logged_tool
    def pick(session_id: str, message_id: int | None = None) -> str:
        if message_id is not None:
            msg = store.get(session_id, message_id)
            suffix = f"\n{prompts.ALREADY_DELETED_NOTE}" if msg.deleted else ""
            return format_message(msg) + suffix
        msgs = store.open_messages(session_id)
        if not msgs:
            return prompts.INBOX_EMPTY
        return "\n".join(format_message(m, full=False) for m in msgs)

    @mcp.tool(description=prompts.TOOL_DELETE)
    @logged_tool
    def delete(session_id: str, message_id: int) -> str:
        store.delete(session_id, message_id)
        return prompts.DELETED.format(id=message_id)

    @mcp.tool(description=prompts.TOOL_READ_THREAD)
    @logged_tool
    def read_thread(session_id: str, thread_id: int) -> str:
        return "\n".join(
            prompts.THREAD_LINE.format(
                id=m.id,
                sender=m.from_name,
                recipient=store.name_of(m.to_id),
                severity=m.severity,
                body=m.body,
            )
            for m in store.thread(session_id, thread_id)
        )

    @mcp.custom_route(consts.ROUTE_HEALTH, methods=["GET"])
    async def health(request: Request) -> Response:
        return PlainTextResponse(consts.HEALTH_BODY)

    @mcp.custom_route(consts.ROUTE_UI, methods=["GET"])
    async def ui(request: Request) -> Response:
        return FileResponse(consts.UI_FILE)

    @mcp.custom_route(consts.ROUTE_STATE, methods=["GET"])
    async def api_state(request: Request) -> Response:
        sessions = []
        for session in store.list_sessions():
            messages = [
                {
                    "id": m.id,
                    "from": m.from_name,
                    "severity": m.severity,
                    "body": m.body,
                    "thread_id": m.thread_id,
                    "created_at": m.created_at,
                    "deleted": m.deleted,
                    "announced": m.announced,
                }
                for m in store.inbox(session.session_id)
            ]
            sessions.append(
                {
                    "session_id": session.session_id,
                    "name": session.name,
                    "description": session.description,
                    "host": store.host_of(session.session_id),
                    "messages": messages,
                }
            )
        return JSONResponse({"sessions": sessions})

    @mcp.custom_route(consts.ROUTE_HOOK_MESSAGES, methods=["POST"])
    async def hook_messages(request: Request) -> Response:
        """The session's open messages. What to do about them is the hook manager's call."""
        data = await request.json()
        session_id = note_transcript(store, data, request.headers.get(consts.HEADER_CLIENT_HOST))
        session = store.sessions.get(session_id)
        messages = [
            {
                "id": m.id,
                "from": m.from_name,
                "severity": m.severity,
                "body": m.body,
                "thread_id": m.thread_id,
                "announced": m.announced,
            }
            for m in store.open_messages(session_id)
        ]
        log.info(
            "inbox reported",
            hook_event=data.get("hook_event_name"),
            session_id=session_id,
            session_name=session.name if session else None,
            open=store.count(session_id),
            unannounced=sum(not m["announced"] for m in messages),
        )
        return JSONResponse(
            {
                "session_id": session_id,
                "registered": session is not None,
                "name": session.name if session else None,
                "messages": messages,
            }
        )

    @mcp.custom_route(consts.ROUTE_HOOK_ANNOUNCED, methods=["POST"])
    async def hook_announced(request: Request) -> Response:
        data = await request.json()
        marked = store.mark_announced(data.get("session_id", ""), data.get("message_ids", []))
        return JSONResponse({"marked": marked})

    # On the network the Host header is the server's LAN address, which the MCP library's
    # local-only check would refuse. The token guards the server there instead.
    security = (
        None
        if is_loopback(host)
        else TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    # Stateless so that clients keep working across a server restart.
    app = mcp.streamable_http_app(
        stateless_http=True, json_response=True, host=host, transport_security=security
    )
    if token:
        app.add_middleware(RequireToken, token=token)
    return app


def purge_loop(store: Store) -> None:
    while True:
        purged = store.purge_missing()
        log.info("purge finished", purged_sessions=purged, sessions_left=len(store.sessions))
        time.sleep(consts.PURGE_INTERVAL_SECONDS)


def main() -> None:
    add_console(consts.LOG_SERVER, sys.stderr)
    host, port, token = get_host(), get_port(), get_token()
    try:
        check_exposure(host, token)
    except NetworkWithoutTokenError as error:
        log.error("startup refused", host=host, error=type(error).__name__)
        sys.exit(str(error))
    store = Store(get_db_path())
    log.info(
        "server starting",
        host=host,
        port=port,
        token_required=token is not None,
        db=str(get_db_path()),
        logs=str(get_logs_dir()),
        pid=os.getpid(),
    )
    if not is_loopback(host):
        log.info("open to the network", urls=network_urls(port), computer=store.host)
    threading.Thread(target=purge_loop, args=(store,), daemon=True).start()
    uvicorn.run(create_app(store, host, token), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
