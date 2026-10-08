"""Every text a Claude session reads: server instructions, tool descriptions, tool results,
hook feedback and error messages. Templates are filled with str.format."""

# --- server instructions ---
INSTRUCTIONS = (
    "Inbox between Claude Code sessions. Pass your own Claude Code session_id to every tool"
    " (it is given to you at session start). Call register once with a unique name and a short"
    " description of what you are working on, list_sessions to see who you can write to, and"
    " send to message them. A message stays open in your inbox until you delete it, so delete"
    " each message once you have handled it. Severity: normal, important (handle before"
    " you finish your current task), blocking (the recipient cannot stop until it is deleted)."
)

# --- tool descriptions ---
TOOL_REGISTER = (
    "Register this session under a unique name with a short description of its work."
    " Call again with the same session_id to change the name or description."
)
TOOL_LIST_SESSIONS = "List registered sessions (name and description) so you know who to send to."
TOOL_SEND = (
    "Send a message to another session by its registered name."
    " severity: 'normal', 'important' (recipient should handle it before finishing its"
    " current task) or 'blocking' (recipient cannot stop until it is handled)."
    " reply_to: id of a message you are answering; the reply joins its thread."
)
TOOL_COUNT = "Count the open messages in your inbox, per severity."
TOOL_PICK = (
    "Read your inbox. Without message_id: one line per open message."
    " With message_id: that message in full."
)
TOOL_DELETE = "Delete a message from your inbox once you have handled it."
TOOL_READ_THREAD = "Read a whole conversation you take part in, oldest message first."

# --- tool results ---
REGISTERED = "Registered as '{name}'."
NO_SESSIONS = "No sessions registered."
SESSION_LINE = "{name}: {description}"
SENT = "Sent message #{id} to '{to}' (thread {thread_id})."
COUNT = "{total} open message(s): {detail}."
COUNT_PART = "{count} {severity}"
INBOX_EMPTY = "Inbox is empty."
ALREADY_DELETED_NOTE = "(already deleted)"
DELETED = "Deleted message #{id}."
MESSAGE_LINE = '[#{id}] {severity} from "{sender}" (thread {thread_id}): {body}'
THREAD_LINE = '[#{id}] "{sender}" -> "{recipient}" ({severity}): {body}'

# --- hook feedback ---
STOP_BLOCK_HEADER = "Inbox: {count} blocking message(s). You cannot stop until they are handled."
STOP_ALSO_WAITING = "Also waiting, not blocking: {count} new message(s)."
STOP_ANNOUNCE_HEADER = "Inbox: {count} new message(s) for you, none blocking."
STOP_FOOTER = (
    "Handle important messages before you finish your current task and normal ones when it"
    " fits your work. Once a message is handled, call the inbox `delete` tool with its"
    " message_id (your session_id: {session_id})."
)
START_RUNNING = "Inbox MCP server is running. Your session_id for inbox tools: {session_id}"
START_NOT_REGISTERED = (
    "You are not registered in the inbox. To exchange messages with other Claude sessions,"
    " call the inbox `register` tool with a unique name and a short description of your work."
)
START_REGISTERED = "You are registered as '{name}' with {total} open message(s)."
START_READ_HINT = " Call the inbox `pick` tool to read them."
UNKNOWN_HOOK_EVENT = "inbox hook: unknown event '{event}'"

# --- errors ---
ERROR_MISSING_SESSION_ID = "session_id is required"
ERROR_MISSING_NAME = "name is required"
ERROR_NAME_TAKEN = "name '{name}' is already taken by another session; try a different name"
ERROR_NOT_REGISTERED = "this session_id is not registered; call register first"
ERROR_INVALID_SEVERITY = "severity must be one of: {allowed}"
ERROR_EMPTY_BODY = "body is empty"
ERROR_UNKNOWN_RECIPIENT = (
    "no session named '{name}'; call list_sessions to see who is registered"
)
ERROR_REPLY_TARGET = "cannot reply to message {id}: not found"
ERROR_MESSAGE_NOT_FOUND = "no message {id} in your inbox"
ERROR_ALREADY_DELETED = "message {id} is already deleted"
ERROR_THREAD_NOT_FOUND = "no thread {id} that you take part in"
