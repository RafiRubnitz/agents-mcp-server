import pytest
from starlette.testclient import TestClient

from inbox_mcp.server import create_app
from inbox_mcp.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "inbox.db")
    s.register("sid-a", "alice", "builds the api")
    s.register("sid-b", "bob", "writes the tests")
    yield s
    s.close()


@pytest.fixture
def client(store):
    return TestClient(create_app(store))


def test_health(client):
    assert client.get("/health").text == "ok"


def test_messages_route_reports_open_messages_and_records_transcript(client, store):
    new = client.post(
        "/hooks/messages", json={"session_id": "sid-new", "transcript_path": "/t/new.jsonl"}
    ).json()
    assert new == {"session_id": "sid-new", "registered": False, "name": None, "messages": []}
    assert store.transcripts["sid-new"] == "/t/new.jsonl"

    normal = store.send("sid-a", "bob", "normal", "fyi")
    blocking = store.send("sid-a", "bob", "blocking", "fix the build")
    handled = store.send("sid-a", "bob", "normal", "done already")
    store.delete("sid-b", handled.id)

    bob = client.post("/hooks/messages", json={"session_id": "sid-b"}).json()
    assert bob["registered"] and bob["name"] == "bob"
    assert [m["id"] for m in bob["messages"]] == [blocking.id, normal.id]
    assert bob["messages"][0] == {
        "id": blocking.id,
        "from": "alice",
        "severity": "blocking",
        "body": "fix the build",
        "thread_id": blocking.thread_id,
        "announced": False,
    }


def test_announced_route_marks_only_the_sessions_own_messages(client, store):
    to_bob = store.send("sid-a", "bob", "normal", "for bob")
    to_alice = store.send("sid-b", "alice", "normal", "for alice")

    body = {"session_id": "sid-b", "message_ids": [to_bob.id, to_alice.id, 999]}
    assert client.post("/hooks/announced", json=body).json() == {"marked": [to_bob.id]}
    assert client.post("/hooks/announced", json=body).json() == {"marked": []}

    bob = client.post("/hooks/messages", json={"session_id": "sid-b"}).json()
    alice = client.post("/hooks/messages", json={"session_id": "sid-a"}).json()
    assert bob["messages"][0]["announced"] is True
    assert alice["messages"][0]["announced"] is False


def test_ui_and_state(client, store):
    kept = store.send("sid-a", "bob", "blocking", "open one")
    done = store.send("sid-a", "bob", "normal", "handled one")
    store.delete("sid-b", done.id)

    assert "<title>Inbox</title>" in client.get("/").text
    sessions = {s["name"]: s for s in client.get("/api/state").json()["sessions"]}
    assert sessions["alice"]["messages"] == []
    bob = sessions["bob"]["messages"]
    assert [(m["id"], m["deleted"]) for m in bob] == [(done.id, True), (kept.id, False)]
    assert bob[1]["from"] == "alice" and bob[1]["severity"] == "blocking"
