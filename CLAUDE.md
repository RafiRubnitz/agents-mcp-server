# inbox-mcp

An inbox between Claude Code sessions: an HTTP MCP server, a hook manager that Claude Code
hooks call, and a read-only web UI. See `README.md` for what it does from a user's side.

Read `docs/conventions.md` before changing code. Its rules are enforced in review.

## Commands

```
uv sync                                   # install
uv run pytest                             # tests
uv run inbox-mcp                          # run the server (127.0.0.1:8765)
uv run alembic revision --autogenerate -m "..."   # new migration after editing models.py
```

## Layout

```
src/inbox_mcp/
  consts.py     every constant
  prompts.py    every text a Claude session reads
  errors.py     one error type per failure, all inherit InboxError
  logs.py       loguru setup: one logger and one daily file per component
  models.py     SQLAlchemy models
  db.py         database path, engine, migrations at startup
  store.py      in-memory state, written through to SQLite on every change
  server.py     MCP tools, hook routes, UI routes
  hook.py       hook manager: python -m inbox_mcp.hook <event>
  install.py    writes the hooks into a Claude Code settings.json
  ui.html       the web UI, served at /
  migrations/   alembic environment and versions
tests/
docs/conventions.md
logs/           <component>_<date>.log, not committed
```

## How the pieces talk

- Claude sessions call the MCP tools at `/mcp`.
- Claude Code hooks (SessionStart and Stop) run `hook.py`. It POSTs the hook input to
  `/hooks/messages`, gets the session's open messages back, and decides itself what to
  answer Claude Code (`decide_stop`, `start_context`). After showing messages it POSTs
  their ids to `/hooks/announced`, so a non-blocking message continues a turn only once.
- The server knows nothing about hook events: it reports inbox state and records what was
  announced.
- The UI polls `/api/state`.

## Things that are easy to get wrong

- The `mcp` package is 2.x: the server class is `MCPServer` from `mcp.server.mcpserver`,
  not `FastMCP`. Transport options go to `streamable_http_app()`.
- A tool only shows its error text to the model if it raises a `ToolError`. `InboxError`
  inherits it; anything else becomes a bare "Error executing tool".
- A Stop hook answers with JSON on stdout and exit 0; with valid JSON the exit code is
  ignored. `decision: block` holds Claude, `hookSpecificOutput.additionalContext` shows it
  text and continues the turn. Anything that continues the turn must stop doing so on its
  own (the `announced` flag), or the session loops on Stop forever.
- Only SessionStart and Stop are handled. TaskCompleted and TeammateIdle were dropped for
  the MVP; they take feedback only through exit code 2, not JSON. SessionStart cannot be an
  `http` hook.
- `store.py` keeps detached SQLAlchemy objects as its in-memory state and writes each change
  with `merge`. Change the dicts and the database in the same method, under `self._lock`.
- When something misbehaves, read `logs/` first: `server`, `store`, `db`, `hook` and
  `install` each have a file per day. The hook manager must never write to stdout or stderr
  except what the hook protocol needs, so its diagnostics exist only there.
- A running server does not reload code. Restart it after changing anything it imports.
- The real database is `~/.claude/inbox/inbox.db` and other sessions may be using it. Use
  `INBOX_DB` and `INBOX_PORT` for manual experiments.
- `python -m inbox_mcp.install` edits the user's `~/.claude/settings.json`. Do not run it
  without being asked; test with `--settings <copy>`.
