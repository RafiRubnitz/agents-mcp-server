import datetime
import io
import json

import pytest
from starlette.testclient import TestClient

from inbox_mcp import consts, hook
from inbox_mcp.logs import get_logger, get_logs_dir
from inbox_mcp.server import create_app
from inbox_mcp.store import Store


def read_log(component: str) -> str:
    today = datetime.date.today().isoformat()
    return (get_logs_dir() / f"{component}_{today}.log").read_text(encoding="utf-8")


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "inbox.db")
    s.register("sid-a", "alice", "a")
    s.register("sid-b", "bob", "b")
    yield s
    s.close()


def test_each_component_has_its_own_daily_file_with_params():
    get_logger("alpha").info("first thing", item_id=7, owner="alice")
    get_logger("beta").warning("second thing", attempts=3)

    alpha = read_log("alpha")
    assert "| alpha | first thing | item_id=7 owner='alice'" in alpha
    assert "second thing" not in alpha
    assert "WARNING | beta | second thing | attempts=3" in read_log("beta")


def test_store_logs_runtime_params_without_message_bodies(store):
    msg = store.send("sid-a", "bob", "blocking", "the secret body text")
    store.delete("sid-b", msg.id)

    text = read_log(consts.LOG_STORE)
    assert f"message sent | message_id={msg.id}" in text
    assert "to_name='bob'" in text and "severity='blocking'" in text and "body_chars=20" in text
    assert f"message deleted | message_id={msg.id} session_id='sid-b'" in text
    assert "the secret body text" not in text


def test_server_logs_tool_calls_rejections_and_hooks(store):
    # The MCP endpoint only accepts local Host headers.
    client = TestClient(create_app(store), base_url=consts.BASE_URL)

    def call(tool, arguments):
        return client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            },
            headers={"Accept": "application/json, text/event-stream"},
        ).json()["result"]

    with client:
        long_body = "x" * 200
        sent = call(
            "send", {"session_id": "sid-a", "to": "bob", "severity": "blocking", "body": long_body}
        )
        assert not sent["isError"]
        taken = call("register", {"session_id": "sid-c", "name": "bob", "description": "d"})
        assert taken["isError"]
        client.post("/hooks/messages", json={"session_id": "sid-b", "hook_event_name": "Stop"})

    text = read_log(consts.LOG_SERVER)
    assert "tool called | tool='send' session_id='sid-a' to='bob'" in text
    assert "body='<200 chars>'" in text and long_body not in text
    assert "tool rejected | tool='register' error='NameTakenError' session_id='sid-c'" in text
    assert "inbox reported | hook_event='Stop' session_id='sid-b' session_name='bob'" in text
    assert "unannounced=1" in text


def test_hook_logs_outcome_when_server_is_unreachable(monkeypatch):
    monkeypatch.setenv(consts.ENV_URL, "http://127.0.0.1:9")
    monkeypatch.setattr("sys.argv", ["hook", consts.EVENT_STOP])
    payload = json.dumps({"session_id": "sid-z"}).encode()
    monkeypatch.setattr("sys.stdin", type("Stdin", (), {"buffer": io.BytesIO(payload)}))

    assert hook.main() == consts.EXIT_OK

    text = read_log(consts.LOG_HOOK)
    assert "WARNING | hook | server unreachable | event='stop' session_id='sid-z'" in text
    assert "hook ran | event='stop' session_id='sid-z' outcome='server unreachable'" in text
    assert "exit_code=0" in text
