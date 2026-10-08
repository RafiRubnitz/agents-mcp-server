"""One error type per failure. All inherit InboxError, a ToolError, so the message reaches
the calling model."""

from mcp.server.mcpserver.exceptions import ToolError

from . import prompts
from .consts import SEVERITIES


class InboxError(ToolError):
    """A request the caller can fix."""


class MissingSessionIdError(InboxError):
    def __init__(self) -> None:
        super().__init__(prompts.ERROR_MISSING_SESSION_ID)


class MissingNameError(InboxError):
    def __init__(self) -> None:
        super().__init__(prompts.ERROR_MISSING_NAME)


class NameTakenError(InboxError):
    def __init__(self, name: str) -> None:
        super().__init__(prompts.ERROR_NAME_TAKEN.format(name=name))


class NotRegisteredError(InboxError):
    def __init__(self) -> None:
        super().__init__(prompts.ERROR_NOT_REGISTERED)


class InvalidSeverityError(InboxError):
    def __init__(self) -> None:
        super().__init__(prompts.ERROR_INVALID_SEVERITY.format(allowed=", ".join(SEVERITIES)))


class EmptyBodyError(InboxError):
    def __init__(self) -> None:
        super().__init__(prompts.ERROR_EMPTY_BODY)


class UnknownRecipientError(InboxError):
    def __init__(self, name: str) -> None:
        super().__init__(prompts.ERROR_UNKNOWN_RECIPIENT.format(name=name))


class ReplyTargetNotFoundError(InboxError):
    def __init__(self, message_id: int) -> None:
        super().__init__(prompts.ERROR_REPLY_TARGET.format(id=message_id))


class MessageNotFoundError(InboxError):
    def __init__(self, message_id: int) -> None:
        super().__init__(prompts.ERROR_MESSAGE_NOT_FOUND.format(id=message_id))


class AlreadyDeletedError(InboxError):
    def __init__(self, message_id: int) -> None:
        super().__init__(prompts.ERROR_ALREADY_DELETED.format(id=message_id))


class ThreadNotFoundError(InboxError):
    def __init__(self, thread_id: int) -> None:
        super().__init__(prompts.ERROR_THREAD_NOT_FOUND.format(id=thread_id))
