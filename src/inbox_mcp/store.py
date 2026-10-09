"""Inbox state: held in memory, every mutation written through to SQLite."""

import os
import socket
import threading
import time
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from . import consts
from .consts import GONE_SESSION_NAME, SEVERITIES
from .db import make_engine, migrate
from .errors import (
    AlreadyDeletedError,
    EmptyBodyError,
    InvalidSeverityError,
    MessageNotFoundError,
    MissingNameError,
    MissingSessionIdError,
    NameTakenError,
    NotRegisteredError,
    ReplyTargetNotFoundError,
    ThreadNotFoundError,
    UnknownRecipientError,
)
from .logs import get_logger
from .models import AgentSession, Message, Transcript

log = get_logger(consts.LOG_STORE)


class Store:
    def __init__(self, db_path: str | Path):
        self._engine = make_engine(db_path)
        migrate(self._engine)
        # Loaded objects stay usable after commit: they are the in-memory state.
        self._db = sessionmaker(self._engine, expire_on_commit=False)
        self._lock = threading.RLock()
        self.sessions: dict[str, AgentSession] = {}
        self.names: dict[str, str] = {}
        self.transcripts: dict[str, Transcript] = {}
        # This computer's name: sessions that report another one are remote.
        self.host = socket.gethostname()
        self.messages: dict[int, Message] = {}
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        with self._db() as db:
            for session in db.scalars(select(AgentSession)):
                self.sessions[session.session_id] = session
                self.names[session.name] = session.session_id
            for transcript in db.scalars(select(Transcript)):
                self.transcripts[transcript.session_id] = transcript
            for message in db.scalars(select(Message)):
                self.messages[message.id] = message
        self._next_id = max(self.messages, default=0) + 1
        log.info(
            "state loaded",
            sessions=len(self.sessions),
            transcripts=len(self.transcripts),
            messages=len(self.messages),
            next_message_id=self._next_id,
        )

    def _save(self, row) -> None:
        with self._db.begin() as db:
            db.merge(row)

    def close(self) -> None:
        self._engine.dispose()

    # --- sessions ---

    def register(self, session_id: str, name: str, description: str) -> AgentSession:
        name = name.strip()
        if not session_id:
            raise MissingSessionIdError()
        if not name:
            raise MissingNameError()
        with self._lock:
            owner = self.names.get(name)
            if owner is not None and owner != session_id:
                raise NameTakenError(name)
            old = self.sessions.get(session_id)
            if old is not None and old.name != name:
                del self.names[old.name]
            session = AgentSession(
                session_id=session_id, name=name, description=description.strip()
            )
            self.sessions[session_id] = session
            self.names[name] = session_id
            self._save(session)
            log.info(
                "session registered",
                session_id=session_id,
                name=name,
                previous_name=old.name if old else None,
            )
            return session

    def set_transcript(self, session_id: str, path: str, host: str | None = None) -> None:
        """Record where the session's transcript lives and that the session just called."""
        now = time.time()
        with self._lock:
            old = self.transcripts.get(session_id)
            moved = old is None or old.path != path or old.host != host
            if not moved and now - old.last_seen < consts.LAST_SEEN_WRITE_INTERVAL_SECONDS:
                return
            row = Transcript(session_id=session_id, path=path, host=host, last_seen=now)
            self.transcripts[session_id] = row
            self._save(row)
            if moved:
                log.info("transcript recorded", session_id=session_id, path=path, host=host)

    def host_of(self, session_id: str) -> str:
        """The computer a session runs on; this one when it never said otherwise."""
        transcript = self.transcripts.get(session_id)
        return (transcript.host if transcript else None) or self.host

    def _is_gone(self, transcript: Transcript, now: float) -> bool:
        if transcript.host in (None, self.host):
            return not os.path.exists(transcript.path)
        # Another computer's disk cannot be checked: go by how long it has been silent.
        return now - transcript.last_seen > consts.REMOTE_SESSION_TTL_SECONDS

    def list_sessions(self) -> list[AgentSession]:
        with self._lock:
            return sorted(self.sessions.values(), key=lambda s: s.name)

    def _require_session(self, session_id: str) -> AgentSession:
        session = self.sessions.get(session_id)
        if session is None:
            raise NotRegisteredError()
        return session

    # --- messages ---

    def send(
        self,
        session_id: str,
        to: str,
        severity: str,
        body: str,
        reply_to: int | None = None,
    ) -> Message:
        if severity not in SEVERITIES:
            raise InvalidSeverityError()
        if not body.strip():
            raise EmptyBodyError()
        with self._lock:
            sender = self._require_session(session_id)
            to_id = self.names.get(to.strip())
            if to_id is None:
                raise UnknownRecipientError(to)
            msg_id = self._next_id
            thread_id = msg_id
            if reply_to is not None:
                parent = self.messages.get(reply_to)
                if parent is None or session_id not in (parent.from_id, parent.to_id):
                    raise ReplyTargetNotFoundError(reply_to)
                thread_id = parent.thread_id
            msg = Message(
                id=msg_id,
                from_id=session_id,
                from_name=sender.name,
                to_id=to_id,
                severity=severity,
                body=body,
                thread_id=thread_id,
                created_at=time.time(),
                deleted=False,
                announced=False,
            )
            self._next_id += 1
            self.messages[msg_id] = msg
            self._save(msg)
            log.info(
                "message sent",
                message_id=msg.id,
                thread_id=thread_id,
                from_name=sender.name,
                to_name=to.strip(),
                to_id=to_id,
                severity=severity,
                body_chars=len(body),
                reply_to=reply_to,
            )
            return msg

    def open_messages(
        self, session_id: str, levels: Iterable[str] = SEVERITIES
    ) -> list[Message]:
        """Undeleted messages addressed to the session, most severe first."""
        levels = tuple(levels)
        with self._lock:
            found = [
                m
                for m in self.messages.values()
                if m.to_id == session_id and not m.deleted and m.severity in levels
            ]
        return sorted(found, key=lambda m: (-SEVERITIES.index(m.severity), m.id))

    def inbox(self, session_id: str) -> list[Message]:
        """Every message addressed to the session, handled ones included, newest first."""
        with self._lock:
            found = [m for m in self.messages.values() if m.to_id == session_id]
        return sorted(found, key=lambda m: -m.id)

    def count(self, session_id: str) -> dict[str, int]:
        counts = {level: 0 for level in SEVERITIES}
        for msg in self.open_messages(session_id):
            counts[msg.severity] += 1
        return counts

    def get(self, session_id: str, message_id: int) -> Message:
        with self._lock:
            msg = self.messages.get(message_id)
            if msg is None or msg.to_id != session_id:
                raise MessageNotFoundError(message_id)
            return msg

    def delete(self, session_id: str, message_id: int) -> Message:
        with self._lock:
            msg = self.get(session_id, message_id)
            if msg.deleted:
                raise AlreadyDeletedError(message_id)
            msg.deleted = True
            self._save(msg)
            log.info(
                "message deleted",
                message_id=message_id,
                session_id=session_id,
                severity=msg.severity,
                open_seconds=round(time.time() - msg.created_at, 1),
            )
            return msg

    def mark_announced(self, session_id: str, message_ids: Iterable[int]) -> list[int]:
        """Remember that these messages were shown to their recipient. Returns the new ones."""
        marked = []
        with self._lock:
            for message_id in message_ids:
                msg = self.messages.get(message_id)
                if msg is None or msg.to_id != session_id or msg.announced:
                    continue
                msg.announced = True
                self._save(msg)
                marked.append(message_id)
        if marked:
            log.info("messages announced", session_id=session_id, message_ids=marked)
        return marked

    def thread(self, session_id: str, thread_id: int) -> list[Message]:
        with self._lock:
            msgs = sorted(
                (m for m in self.messages.values() if m.thread_id == thread_id),
                key=lambda m: m.id,
            )
        if not any(session_id in (m.from_id, m.to_id) for m in msgs):
            raise ThreadNotFoundError(thread_id)
        return msgs

    def name_of(self, session_id: str) -> str:
        session = self.sessions.get(session_id)
        return session.name if session else GONE_SESSION_NAME

    # --- cleanup ---

    def purge_missing(self) -> list[str]:
        """Drop sessions that can no longer be resumed: on this computer, those whose
        transcript file was deleted; on other computers, those silent for too long."""
        purged = []
        now = time.time()
        with self._lock:
            gone = [sid for sid, t in self.transcripts.items() if self._is_gone(t, now)]
            for sid in gone:
                transcript = self.transcripts.pop(sid)
                session = self.sessions.pop(sid, None)
                if session is not None:
                    del self.names[session.name]
                    purged.append(session.name)
                dropped = [m.id for m in self.messages.values() if m.to_id == sid]
                for mid in dropped:
                    del self.messages[mid]
                log.info(
                    "session purged",
                    session_id=sid,
                    name=session.name if session else None,
                    host=transcript.host,
                    dropped_message_ids=dropped,
                )
                with self._db.begin() as db:
                    db.execute(delete(Transcript).where(Transcript.session_id == sid))
                    db.execute(delete(AgentSession).where(AgentSession.session_id == sid))
                    db.execute(delete(Message).where(Message.to_id == sid))
        return purged
