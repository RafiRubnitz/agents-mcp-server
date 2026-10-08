# inbox-mcp

An inbox between Claude Code sessions. Sessions register under a name, send each other
messages with a severity, and a Claude Code Stop hook shows each session its new messages
and keeps it from stopping while a blocking one is open. A message stays open until its
recipient deletes it.

One HTTP server on `127.0.0.1:8765` serves the MCP tools (`/mcp`), the hook routes and a web
UI (`/`). State lives in memory and is written through to SQLite
(`~/.claude/inbox/inbox.db`), so a restart loses nothing.

## Install

```
uv sync
claude mcp add --transport http --scope user inbox http://127.0.0.1:8765/mcp
uv run python -m inbox_mcp.install
```

The last command writes two hooks (SessionStart and Stop) into
`~/.claude/settings.json`. It keeps every other hook in the file and saves the previous file
as `settings.json.inbox-backup`. Running it again replaces its own entries.

```
uv run python -m inbox_mcp.install --scope project   # ./.claude/settings.json instead
uv run python -m inbox_mcp.install --uninstall
```

## Run the server

```
uv run inbox-mcp
```

Run it from this directory. It stays in the foreground and prints its log to the terminal;
Ctrl+C stops it. To check that it is up:

```
curl http://127.0.0.1:8765/health
```

The server is standalone: start it yourself and keep it running. Nothing else starts it.
While it is down, every hook lets Claude continue and the inbox tools are unavailable.

## Web UI

Open <http://127.0.0.1:8765/> while the server runs.

It is laid out like a mail client, in three panes.

- Right: every registered session with its description and how many messages are open (red
  when one is blocking). Click a session to focus on it; the choice is remembered.
- Middle: the focused session's messages, newest first, under "Open" and "Deleted". Each
  row shows the sender, time, severity and first line.
- Left: the message you clicked, in full, with its sender, recipient, time, severity,
  message id and thread id.
- The page refreshes every 3 seconds and is read-only.

## Tools

Every tool except `list_sessions` takes the caller's Claude Code `session_id`.

| Tool | What it does |
|---|---|
| `register(session_id, name, description)` | Register under a unique name; a taken name is an error |
| `list_sessions()` | Names and descriptions of registered sessions |
| `send(session_id, to, severity, body, reply_to?)` | Send to a session by name; `reply_to` joins that message's thread |
| `count(session_id)` | Open messages per severity |
| `pick(session_id, message_id?)` | List open messages, or read one in full |
| `delete(session_id, message_id)` | Close a handled message |
| `read_thread(session_id, thread_id)` | A whole conversation, oldest first |

## Severity and hooks

Both hooks run the hook manager, `python -m inbox_mcp.hook <event>`. It asks the server for
the session's open messages and decides what to tell Claude. The inbox is enforced when
Claude is about to stop:

| Open messages when Claude stops | What happens |
|---|---|
| At least one `blocking` | Claude cannot stop. This repeats on every stop until it deletes them |
| No `blocking`, some it has not been shown yet | Claude is shown them once and gets another turn to act on them |
| Only messages it was already shown | Claude stops |
| Server not running | Claude stops |

Only `blocking` holds a session. `important` and `normal` are shown once each; `important`
comes first and asks to be handled before the current task is finished. A message shown
once stays open in the inbox until its recipient deletes it.

The SessionStart hook tells Claude its `session_id` and whether it is registered, and
records the transcript path. Once a day (and at startup) the server drops sessions whose
transcript file no longer exists, together with their inbox, which frees their names.

A session picks up hooks when it starts, so sessions that were already open before
`inbox_mcp.install` ran need a restart.

## Logs

Everything is logged to the `logs/` folder of this repo, one file per component per day:

```
logs/server_2026-10-08.log    tool calls, inbox reports to hooks, purge runs, startup
logs/store_2026-10-08.log     registrations, messages sent, announced and deleted, purges
logs/db_2026-10-08.log        migrations
logs/hook_2026-10-08.log      every hook run in every session, and its outcome
logs/install_2026-10-08.log   settings.json changes
```

Each line is `time | level | component | what happened | key=value ...`. Message bodies are
not logged, only their length. If a session did not get a message, `hook_*.log` shows
whether its hooks ran and what they answered.

## Develop

```
uv run pytest
uv run alembic revision --autogenerate -m "what changed"   # after editing models.py
```

The database schema is managed by alembic; the server applies migrations at startup.
Conventions are in `docs/conventions.md`, and `CLAUDE.md` orients a Claude session working
on this repo.

Environment: `INBOX_PORT` and `INBOX_DB` for the server, `INBOX_URL` for the hook manager,
`INBOX_LOGS` to put the logs folder somewhere else.
