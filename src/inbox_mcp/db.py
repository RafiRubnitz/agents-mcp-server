"""Database location, engine and migrations."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import URL, Engine, create_engine, inspect

from . import consts
from .consts import (
    ALEMBIC_VERSION_TABLE,
    DB_FILE,
    ENV_DB,
    INITIAL_REVISION,
    MIGRATIONS_DIR,
    PRE_ALEMBIC_TABLE,
)
from .logs import get_logger

log = get_logger(consts.LOG_DB)


def get_db_path() -> Path:
    """The database file: the INBOX_DB environment variable, else the standard location."""
    env = os.environ.get(ENV_DB)
    return Path(env) if env else DB_FILE


def make_engine(db_path: str | Path) -> Engine:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(URL.create("sqlite", database=str(db_path)))


def migrate(engine: Engine) -> None:
    """Bring the database to the latest alembic revision."""
    config = Config()
    config.set_main_option("script_location", MIGRATIONS_DIR.as_posix())
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        tables = inspect(connection).get_table_names()
        if PRE_ALEMBIC_TABLE in tables and ALEMBIC_VERSION_TABLE not in tables:
            # Created before alembic was introduced, with the schema of the first revision.
            command.stamp(config, INITIAL_REVISION)
            log.info(
                "adopted database created before alembic",
                db=str(engine.url.database),
                stamped_revision=INITIAL_REVISION,
            )
        before = MigrationContext.configure(connection).get_current_revision()
        command.upgrade(config, "head")
        after = MigrationContext.configure(connection).get_current_revision()
    log.info(
        "database migrated",
        db=str(engine.url.database),
        revision_before=before,
        revision_after=after,
    )
