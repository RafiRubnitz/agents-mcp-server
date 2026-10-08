"""Alembic environment. The server passes its own connection; the alembic CLI opens one."""

from alembic import context

from inbox_mcp.db import get_db_path, make_engine
from inbox_mcp.models import Base

target_metadata = Base.metadata


def run_migrations(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    with make_engine(get_db_path()).begin() as cli_connection:
        run_migrations(cli_connection)
