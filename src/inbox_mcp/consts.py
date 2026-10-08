"""Every constant of the project. No third-party imports: the hook manager imports this."""

from pathlib import Path

# --- server ---
SERVER_NAME = "inbox"
HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
PURGE_INTERVAL_SECONDS = 24 * 60 * 60

# --- environment variables that override the values above ---
ENV_PORT = "INBOX_PORT"
ENV_DB = "INBOX_DB"
ENV_URL = "INBOX_URL"
ENV_LOGS = "INBOX_LOGS"

# --- database ---
DB_FILE = Path.home() / ".claude" / "inbox" / "inbox.db"
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
INITIAL_REVISION = "0001"
# Table that marks a database created before alembic was introduced.
PRE_ALEMBIC_TABLE = "sessions"
ALEMBIC_VERSION_TABLE = "alembic_version"

# --- severities, least severe first ---
SEVERITY_NORMAL = "normal"
SEVERITY_IMPORTANT = "important"
SEVERITY_BLOCKING = "blocking"
SEVERITIES = (SEVERITY_NORMAL, SEVERITY_IMPORTANT, SEVERITY_BLOCKING)

# --- hook manager ---
HOOK_MODULE = "inbox_mcp.hook"
EVENT_SESSION_START = "session-start"
EVENT_STOP = "stop"

# Claude Code's own names, as its hook JSON expects them.
CLAUDE_EVENT_SESSION_START = "SessionStart"
CLAUDE_EVENT_STOP = "Stop"
STOP_DECISION_BLOCK = "block"

HOOK_REQUEST_TIMEOUT_SECONDS = 5
EXIT_OK = 0
EXIT_UNKNOWN_EVENT = 1

# --- HTTP routes ---
ROUTE_UI = "/"
ROUTE_STATE = "/api/state"
ROUTE_HEALTH = "/health"
ROUTE_HOOK_MESSAGES = "/hooks/messages"
ROUTE_HOOK_ANNOUNCED = "/hooks/announced"
HEALTH_BODY = "ok"

# --- installer: Claude Code event -> (hook manager event, timeout in seconds) ---
INSTALL_EVENTS = {
    CLAUDE_EVENT_SESSION_START: (EVENT_SESSION_START, 10),
    CLAUDE_EVENT_STOP: (EVENT_STOP, 10),
}
SETTINGS_BACKUP_SUFFIX = ".inbox-backup"

# --- logs: one file per component per day ---
LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_SERVER = "server"
LOG_STORE = "store"
LOG_DB = "db"
LOG_HOOK = "hook"
LOG_INSTALL = "install"
LOG_FILE_SUFFIX = "_{time:YYYY-MM-DD}.log"
LOG_ROTATION = "00:00"
LOG_LEVEL = "INFO"
LOG_COMPONENT_KEY = "component"
LOG_PARAMS_KEY = "params"
LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {extra[component]} | {message}"
    " | {extra[params]}"
)
# Longer string arguments are logged as their length, not their content.
LOG_MAX_VALUE_CHARS = 80

# --- presentation ---
UI_FILE = Path(__file__).with_name("ui.html")
PREVIEW_CHARS = 100
GONE_SESSION_NAME = "(gone)"
