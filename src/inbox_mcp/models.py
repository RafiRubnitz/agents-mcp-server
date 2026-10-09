"""SQLAlchemy models. Any change here needs an alembic migration."""

from sqlalchemy import Text, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AgentSession(Base):
    """A registered Claude Code session."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str]


class Transcript(Base):
    """Where a session's transcript file lives; the session is purged once it is gone."""

    __tablename__ = "transcripts"

    session_id: Mapped[str] = mapped_column(primary_key=True)
    path: Mapped[str]
    # The computer the session runs on; None for rows older than this column.
    host: Mapped[str | None] = mapped_column(default=None)
    # When a hook of the session last called, as a timestamp.
    last_seen: Mapped[float] = mapped_column(default=0.0, server_default="0")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    from_id: Mapped[str]
    from_name: Mapped[str]
    to_id: Mapped[str]
    severity: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    thread_id: Mapped[int]
    created_at: Mapped[float]
    deleted: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Shown to its recipient by a hook at least once.
    announced: Mapped[bool] = mapped_column(default=False, server_default=false())
