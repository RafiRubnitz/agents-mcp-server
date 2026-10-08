import pytest

from inbox_mcp.errors import (
    AlreadyDeletedError,
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
from inbox_mcp.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "inbox.db")
    s.register("sid-a", "alice", "builds the api")
    s.register("sid-b", "bob", "writes the tests")
    yield s
    s.close()


def test_register_name_conflict(store):
    with pytest.raises(NameTakenError):
        store.register("sid-c", "alice", "someone else")


def test_register_missing_fields_have_their_own_errors(store):
    with pytest.raises(MissingSessionIdError):
        store.register("", "carol", "x")
    with pytest.raises(MissingNameError):
        store.register("sid-c", "  ", "x")


def test_reregister_renames_and_frees_old_name(store):
    store.register("sid-a", "alice2", "new work")
    assert store.names == {"alice2": "sid-a", "bob": "sid-b"}
    store.register("sid-c", "alice", "takes the freed name")


def test_send_requires_registered_sender_and_known_recipient(store):
    with pytest.raises(NotRegisteredError):
        store.send("sid-x", "bob", "normal", "hi")
    with pytest.raises(UnknownRecipientError):
        store.send("sid-a", "carol", "normal", "hi")
    with pytest.raises(InvalidSeverityError):
        store.send("sid-a", "bob", "urgent", "hi")


def test_open_messages_filter_and_order(store):
    store.send("sid-a", "bob", "normal", "n")
    store.send("sid-a", "bob", "blocking", "b")
    store.send("sid-a", "bob", "important", "i")
    assert [m.body for m in store.open_messages("sid-b")] == ["b", "i", "n"]
    assert [m.body for m in store.open_messages("sid-b", ["blocking"])] == ["b"]
    assert store.count("sid-b") == {"normal": 1, "important": 1, "blocking": 1}
    assert store.open_messages("sid-a") == []


def test_reply_inherits_thread(store):
    first = store.send("sid-a", "bob", "normal", "question")
    reply = store.send("sid-b", "alice", "normal", "answer", reply_to=first.id)
    other = store.send("sid-a", "bob", "normal", "unrelated")
    assert reply.thread_id == first.thread_id
    assert other.thread_id != first.thread_id
    assert [m.body for m in store.thread("sid-a", first.thread_id)] == ["question", "answer"]
    store.register("sid-c", "carol", "outsider")
    with pytest.raises(ThreadNotFoundError):
        store.thread("sid-c", first.thread_id)
    with pytest.raises(ReplyTargetNotFoundError):
        store.send("sid-c", "bob", "normal", "butting in", reply_to=first.id)


def test_message_stays_open_until_deleted_by_recipient(store):
    msg = store.send("sid-a", "bob", "blocking", "stop")
    store.get("sid-b", msg.id)  # reading does not close it
    assert len(store.open_messages("sid-b")) == 1
    with pytest.raises(MessageNotFoundError):
        store.delete("sid-a", msg.id)
    store.delete("sid-b", msg.id)
    with pytest.raises(AlreadyDeletedError):
        store.delete("sid-b", msg.id)
    assert store.open_messages("sid-b") == []
    # still part of the thread
    assert len(store.thread("sid-b", msg.thread_id)) == 1


def test_state_survives_restart(tmp_path):
    path = tmp_path / "inbox.db"
    s = Store(path)
    s.register("sid-a", "alice", "a")
    s.register("sid-b", "bob", "b")
    kept = s.send("sid-a", "bob", "important", "keep")
    gone = s.send("sid-a", "bob", "normal", "handled")
    s.delete("sid-b", gone.id)
    s.set_transcript("sid-b", "/some/path.jsonl")
    s.close()

    s2 = Store(path)
    assert s2.names == {"alice": "sid-a", "bob": "sid-b"}
    assert [m.id for m in s2.open_messages("sid-b")] == [kept.id]
    assert s2.transcripts == {"sid-b": "/some/path.jsonl"}
    assert s2.send("sid-a", "bob", "normal", "next").id == gone.id + 1
    s2.close()


def test_purge_removes_sessions_with_deleted_transcript(store, tmp_path):
    alive = tmp_path / "a.jsonl"
    dead = tmp_path / "b.jsonl"
    alive.write_text("")
    dead.write_text("")
    store.set_transcript("sid-a", str(alive))
    store.set_transcript("sid-b", str(dead))
    store.send("sid-a", "bob", "normal", "to bob")
    store.send("sid-b", "alice", "normal", "to alice")

    assert store.purge_missing() == []
    dead.unlink()
    assert store.purge_missing() == ["bob"]
    assert store.names == {"alice": "sid-a"}
    assert [m.body for m in store.messages.values()] == ["to alice"]
    store.register("sid-c", "bob", "name is free again")


def test_database_created_before_alembic_is_adopted(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        """
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL);
        CREATE TABLE transcripts (session_id TEXT PRIMARY KEY, path TEXT NOT NULL);
        CREATE TABLE messages (id INTEGER PRIMARY KEY, from_id TEXT NOT NULL,
            from_name TEXT NOT NULL, to_id TEXT NOT NULL, severity TEXT NOT NULL,
            body TEXT NOT NULL, thread_id INTEGER NOT NULL, created_at REAL NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0);
        INSERT INTO sessions VALUES ('sid-a', 'alice', 'a'), ('sid-b', 'bob', 'b');
        INSERT INTO messages VALUES (7, 'sid-a', 'alice', 'sid-b', 'blocking', 'old', 7, 1.0, 0);
        """
    )
    old.commit()
    old.close()

    s = Store(path)
    assert [m.body for m in s.open_messages("sid-b")] == ["old"]
    assert s.mark_announced("sid-b", [7]) == [7]  # column added by a later migration
    assert s.send("sid-b", "alice", "normal", "new").id == 8
    s.close()
    Store(path).close()  # second start: already at head


def test_announced_survives_restart(tmp_path):
    path = tmp_path / "inbox.db"
    s = Store(path)
    s.register("sid-a", "alice", "a")
    s.register("sid-b", "bob", "b")
    first = s.send("sid-a", "bob", "normal", "one")
    second = s.send("sid-a", "bob", "normal", "two")
    assert s.mark_announced("sid-b", [first.id]) == [first.id]
    s.close()

    s2 = Store(path)
    assert {m.id: m.announced for m in s2.open_messages("sid-b")} == {
        first.id: True,
        second.id: False,
    }
    s2.close()
