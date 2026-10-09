"""Claude Code command hook: `python -m inbox_mcp.hook <event>` with the hook JSON on stdin.

The hook manager owns the policy of every event. It asks the server for the session's open
messages and decides what to answer Claude Code:

  session-start   prints the session's inbox context
  stop            blocks stopping while blocking messages are open; announces other new
                  messages once, which lets Claude act on them before it stops

The server runs on its own; when it cannot be reached the hook stays silent and never
blocks Claude.
"""

import json
import os
import socket
import sys
import urllib.error
import urllib.request

from . import consts, prompts
from .logs import get_logger

log = get_logger(consts.LOG_HOOK)

# No proxies: the server is always local.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get_base_url() -> str:
    return os.environ.get(consts.ENV_URL, consts.BASE_URL)


def get_token() -> str | None:
    return os.environ.get(consts.ENV_TOKEN) or None


def request_headers() -> dict:
    headers = {
        "Content-Type": "application/json",
        consts.HEADER_CLIENT_HOST: socket.gethostname(),
    }
    token = get_token()
    if token:
        headers[consts.HEADER_AUTHORIZATION] = consts.TOKEN_SCHEME + token
    return headers


def post(path: str, body: bytes) -> dict:
    req = urllib.request.Request(get_base_url() + path, data=body, headers=request_headers())
    with _opener.open(req, timeout=consts.HOOK_REQUEST_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read())


def read_session_id(payload: bytes) -> str | None:
    try:
        return json.loads(payload).get("session_id")
    except (ValueError, AttributeError):
        return None


def format_messages(messages: list[dict]) -> list[str]:
    return [
        prompts.MESSAGE_LINE.format(
            id=m["id"],
            severity=m["severity"],
            sender=m["from"],
            thread_id=m["thread_id"],
            body=m["body"],
        )
        for m in messages
    ]


def start_context(inbox: dict) -> str:
    """What a session is told when it starts."""
    lines = [prompts.START_RUNNING.format(session_id=inbox["session_id"])]
    if not inbox["registered"]:
        lines.append(prompts.START_NOT_REGISTERED)
    else:
        total = len(inbox["messages"])
        lines.append(
            prompts.START_REGISTERED.format(name=inbox["name"], total=total)
            + (prompts.START_READ_HINT if total else "")
        )
    return "\n".join(lines)


def decide_stop(session_id: str, messages: list[dict]) -> tuple[dict | None, list[int]]:
    """The Stop policy, from the session's open messages.

    Returns the JSON to answer Claude Code with (None lets Claude stop) and the ids of the
    messages this answer announces for the first time.
    """
    blocking = [m for m in messages if m["severity"] == consts.SEVERITY_BLOCKING]
    fresh = [
        m
        for m in messages
        if m["severity"] != consts.SEVERITY_BLOCKING and not m["announced"]
    ]
    fresh_ids = [m["id"] for m in fresh]
    footer = prompts.STOP_FOOTER.format(session_id=session_id)

    if blocking:
        lines = [prompts.STOP_BLOCK_HEADER.format(count=len(blocking))]
        lines += format_messages(blocking)
        if fresh:
            lines.append(prompts.STOP_ALSO_WAITING.format(count=len(fresh)))
            lines += format_messages(fresh)
        lines.append(footer)
        return {"decision": consts.STOP_DECISION_BLOCK, "reason": "\n".join(lines)}, fresh_ids

    if fresh:
        lines = [prompts.STOP_ANNOUNCE_HEADER.format(count=len(fresh))]
        lines += format_messages(fresh)
        lines.append(footer)
        output = {
            "hookSpecificOutput": {
                "hookEventName": consts.CLAUDE_EVENT_STOP,
                "additionalContext": "\n".join(lines),
            }
        }
        return output, fresh_ids

    return None, []


def run_session_start(payload: bytes) -> dict:
    inbox = post(consts.ROUTE_HOOK_MESSAGES, payload)
    sys.stdout.buffer.write(start_context(inbox).encode("utf-8"))
    return {"outcome": "context printed", "registered": inbox["registered"]}


def run_stop(payload: bytes) -> dict:
    inbox = post(consts.ROUTE_HOOK_MESSAGES, payload)
    messages = inbox["messages"]
    output, announced = decide_stop(inbox["session_id"], messages)
    if output is not None:
        sys.stdout.buffer.write(json.dumps(output).encode("utf-8"))
    if announced:
        body = {"session_id": inbox["session_id"], "message_ids": announced}
        post(consts.ROUTE_HOOK_ANNOUNCED, json.dumps(body).encode("utf-8"))
    if output is None:
        outcome = "stop allowed"
    elif "decision" in output:
        outcome = "stop blocked"
    else:
        outcome = "messages announced"
    return {"outcome": outcome, "open_messages": len(messages), "announced_ids": announced}


EVENTS = {
    consts.EVENT_SESSION_START: run_session_start,
    consts.EVENT_STOP: run_stop,
}


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = sys.stdin.buffer.read()
    session_id = read_session_id(payload)

    handler = EVENTS.get(event)
    if handler is None:
        sys.stderr.write(prompts.UNKNOWN_HOOK_EVENT.format(event=event) + "\n")
        log.error("unknown event", event=event, session_id=session_id)
        return consts.EXIT_UNKNOWN_EVENT

    try:
        result = handler(payload)
    except urllib.error.HTTPError as error:
        # The server answered and said no: a missing or wrong token, most likely.
        log.warning(
            "server refused",
            event=event,
            session_id=session_id,
            url=get_base_url(),
            status=error.code,
            token_sent=get_token() is not None,
        )
        result = {"outcome": "server refused"}
    except (urllib.error.URLError, OSError) as error:
        log.warning(
            "server unreachable",
            event=event,
            session_id=session_id,
            url=get_base_url(),
            error=str(error),
        )
        result = {"outcome": "server unreachable"}
    log.info(
        "hook ran",
        event=event,
        session_id=session_id,
        **result,
        exit_code=consts.EXIT_OK,
        cwd=os.getcwd(),
    )
    return consts.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
