"""Logging: every component gets its own loguru logger and its own file per day.

    log = get_logger(consts.LOG_STORE)
    log.info("message sent", message_id=7, to_name="bob", severity="blocking")

Keyword arguments are the log's parameters; they are written as key=value after the text.
"""

import os
from pathlib import Path

from loguru import logger

from . import consts

# Files only. stderr is part of the hook protocol and must stay clean.
logger.remove()

_configured: set[str] = set()


def _render_params(record) -> None:
    record["extra"][consts.LOG_PARAMS_KEY] = " ".join(
        f"{key}={value!r}"
        for key, value in record["extra"].items()
        if key not in (consts.LOG_COMPONENT_KEY, consts.LOG_PARAMS_KEY)
    )


logger.configure(patcher=_render_params)


def get_logs_dir() -> Path:
    """The logs folder: the INBOX_LOGS environment variable, else the project's logs/."""
    env = os.environ.get(consts.ENV_LOGS)
    return Path(env) if env else consts.LOGS_DIR


def _only(component: str):
    return lambda record: record["extra"].get(consts.LOG_COMPONENT_KEY) == component


def get_logger(component: str):
    """The component's logger. Its records go to logs/<component>_<date>.log."""
    if component not in _configured:
        _configured.add(component)
        logger.add(
            str(get_logs_dir() / (component + consts.LOG_FILE_SUFFIX)),
            filter=_only(component),
            format=consts.LOG_FORMAT,
            level=consts.LOG_LEVEL,
            rotation=consts.LOG_ROTATION,
            encoding="utf-8",
        )
    return logger.bind(**{consts.LOG_COMPONENT_KEY: component})


def add_console(component: str, stream) -> None:
    """Also show the component's records on a stream (the server's own terminal)."""
    logger.add(
        stream, filter=_only(component), format=consts.LOG_FORMAT, level=consts.LOG_LEVEL
    )
