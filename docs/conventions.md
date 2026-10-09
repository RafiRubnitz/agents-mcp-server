# Conventions

Rules this project follows. Add a rule here when a review settles one.

## One home for each kind of thing

- **Prompts and instructions** live in `src/inbox_mcp/prompts.py`. That means every text a
  Claude session reads: server instructions, tool descriptions, tool results, hook feedback
  and error messages. Other modules fill the templates with `str.format`; they do not
  contain model-facing strings of their own.
- **Constants** live in `src/inbox_mcp/consts.py`: ports, paths, route paths, event names,
  severities, timeouts, exit codes, environment variable names. No literal of that kind
  elsewhere in the code.
- **Errors** live in `src/inbox_mcp/errors.py`.
- **Database models** live in `src/inbox_mcp/models.py`.
- **Logging setup** lives in `src/inbox_mcp/logs.py`.

## Errors

- Each failure has its own error type. Two different failures never share a type, even in
  the same function.
- All of them inherit `InboxError`, so callers can still catch the family.
- An error builds its own message from `prompts.py`; the raise site passes only the data
  (`raise NameTakenError(name)`).
- Tests assert the error type, not the message text.

## Database

- All database access goes through SQLAlchemy. No raw SQL strings.
- Every schema change is an alembic migration in `src/inbox_mcp/migrations/versions/`,
  made together with the change to `models.py`. Create one with
  `uv run alembic revision --autogenerate -m "what changed"` and review it.
- The server applies migrations itself at startup (`db.migrate`).

## Logs

- Logging is done with loguru, through `logs.get_logger`. No `print` for diagnostics and no
  standard `logging` module.
- Each component writes its own logs. A module gets its logger once, at import, with its
  component constant: `log = get_logger(consts.LOG_STORE)`. A component logs what it does
  itself; it does not log on behalf of another component.
- All logs go to the `logs/` folder, one file per component per day:
  `logs/<component>_<YYYY-MM-DD>.log`. A new file starts at midnight. A copy that is not a
  git checkout (the plugin, a `uvx` run) has no lasting folder of its own and uses
  `~/.claude/inbox/logs` instead.
- Every log carries meaningful parameters, mostly runtime values: ids, names, counts,
  paths, durations, outcomes. Pass them as keyword arguments, never formatted into the text:
  `log.info("message sent", message_id=msg.id, to_name=to, severity=severity)`. The text
  is a fixed phrase, so the same event can be searched for across days.
- Do not log message bodies or other long free text. Log its size (`body_chars=...`).
- `INFO` for things that happened, `WARNING` for a request that was refused or a dependency
  that was unreachable, `ERROR` for a failure of our own.
- Nothing is logged to stderr or stdout by the hook manager: Claude Code reads both.

## Naming

- A name says what the thing does. A function that reads an environment variable and falls
  back to a constant is `get_db_path`, not `default_db_path`; the constant is the default.
- Environment variable names are constants prefixed `ENV_`.

## Processes

- The server is standalone. Nothing starts it implicitly: not the hooks, not the installer.
- The hook manager (`hook.py`) imports only the standard library, loguru, and our
  `consts.py`, `prompts.py` and `logs.py`, so it starts fast. Those three modules must not
  import anything heavier.
- A hook never blocks Claude because the server is unreachable or refuses its token. It
  exits 0 and says nothing.
- The server never listens beyond loopback without a token; it refuses to start instead.
  Every route that carries inbox data is behind the token. A route is left open only if it
  carries none, by adding it to `consts.OPEN_ROUTES`.
- Event policy lives in the hook manager. What an event does about the inbox (block, show,
  stay silent) and the Claude Code hook JSON it answers with are decided in `hook.py`, in a
  pure function per event so it can be tested without a server. The server exposes inbox
  state only (`/hooks/messages`, `/hooks/announced`) and knows nothing about hook events.

## Commits

- Claude is not added as a co-author. No `Co-Authored-By: Claude ...` line in commit
  messages and no "Generated with Claude Code" line in pull request descriptions.
- Work goes to a branch and is merged through a pull request, never pushed straight to the
  main branch.

## Tests

- Every behaviour change comes with a test in `tests/`. Run `uv run pytest` before finishing.
- Tests use a database file under `tmp_path`, never the real one.
