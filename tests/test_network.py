"""Using the inbox from other computers: the access token and sessions that are not local."""

import io
import json
import time

import pytest
from starlette.testclient import TestClient

from inbox_mcp import consts, hook
from inbox_mcp.errors import NetworkWithoutTokenError
from inbox_mcp.server import check_exposure, create_app

TOKEN = "s3cret"
AUTH = {consts.HEADER_AUTHORIZATION: consts.TOKEN_SCHEME + TOKEN}
LAN_URL = "http://192.168.1.20:8765"


@pytest.fixture
def lan(store):
    """The server as another computer sees it: on the network, guarded by a token."""
    return TestClient(create_app(store, host="0.0.0.0", token=TOKEN), base_url=LAN_URL)


def test_server_opens_to_the_network_only_with_a_token():
    with pytest.raises(NetworkWithoutTokenError):
        check_exposure("0.0.0.0", None)
    check_exposure("0.0.0.0", TOKEN)
    check_exposure(consts.HOST, None)


def test_routes_with_inbox_data_need_the_token(lan):
    body = {"session_id": "sid-b"}
    for wrong in ({}, {consts.HEADER_AUTHORIZATION: consts.TOKEN_SCHEME + "guess"}):
        assert lan.get(consts.ROUTE_STATE, headers=wrong).status_code == 401
        assert lan.post(consts.ROUTE_HOOK_MESSAGES, json=body, headers=wrong).status_code == 401
        assert lan.post(consts.ROUTE_HOOK_ANNOUNCED, json=body, headers=wrong).status_code == 401
        assert lan.post(consts.MCP_PATH, json={}, headers=wrong).status_code == 401

    assert lan.get(consts.ROUTE_STATE, headers=AUTH).status_code == 200
    assert lan.post(consts.ROUTE_HOOK_MESSAGES, json=body, headers=AUTH).json()["name"] == "bob"


def test_health_and_the_ui_page_answer_without_the_token(lan):
    assert lan.get(consts.ROUTE_HEALTH).text == consts.HEALTH_BODY
    assert lan.get(consts.ROUTE_UI).status_code == 200


def test_mcp_answers_on_the_lan_address_with_the_token(store):
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_sessions", "arguments": {}},
    }
    headers = {**AUTH, "Accept": "application/json, text/event-stream"}
    with TestClient(create_app(store, host="0.0.0.0", token=TOKEN), base_url=LAN_URL) as lan:
        answer = lan.post(consts.MCP_PATH, json=call, headers=headers)
    assert answer.status_code == 200
    assert "alice" in answer.text and "bob" in answer.text


def test_without_a_token_nothing_is_asked_for(client):
    assert client.get(consts.ROUTE_STATE).status_code == 200


def test_session_on_another_computer_is_kept_until_it_goes_silent(store, tmp_path):
    store.set_transcript("sid-a", "C:/Users/other/.claude/a.jsonl", host="LAPTOP-2")
    assert store.host_of("sid-a") == "LAPTOP-2"
    assert store.host_of("sid-b") == store.host

    assert store.purge_missing() == []  # its file is not on this disk, and that is fine

    store.transcripts["sid-a"].last_seen = time.time() - consts.REMOTE_SESSION_TTL_SECONDS - 1
    assert store.purge_missing() == ["alice"]


def test_session_on_this_computer_still_follows_its_transcript_file(store, tmp_path):
    transcript = tmp_path / "b.jsonl"
    transcript.write_text("{}")
    store.set_transcript("sid-b", str(transcript), host=store.host)
    store.transcripts["sid-b"].last_seen = 0  # silence does not matter for a local session
    assert store.purge_missing() == []

    transcript.unlink()
    assert store.purge_missing() == ["bob"]


def test_last_contact_is_written_at_most_once_an_hour(store):
    store.set_transcript("sid-a", "/t/a.jsonl", host="LAPTOP-2")
    first = store.transcripts["sid-a"].last_seen
    store.set_transcript("sid-a", "/t/a.jsonl", host="LAPTOP-2")
    assert store.transcripts["sid-a"].last_seen == first

    store.transcripts["sid-a"].last_seen = first - consts.LAST_SEEN_WRITE_INTERVAL_SECONDS - 1
    store.set_transcript("sid-a", "/t/a.jsonl", host="LAPTOP-2")
    assert store.transcripts["sid-a"].last_seen >= first


def test_computer_is_recorded_from_the_hook_and_shown_when_there_are_several(lan, client, store):
    assert "(on " not in call_list_sessions(store)

    lan.post(
        consts.ROUTE_HOOK_MESSAGES,
        json={"session_id": "sid-a", "transcript_path": "/t/a.jsonl"},
        headers={**AUTH, consts.HEADER_CLIENT_HOST: "LAPTOP-2"},
    )

    state = client.get(consts.ROUTE_STATE).json()
    assert {s["name"]: s["host"] for s in state["sessions"]} == {
        "alice": "LAPTOP-2",
        "bob": store.host,
    }
    assert "alice (on LAPTOP-2): builds the api" in call_list_sessions(store)


def call_list_sessions(store) -> str:
    call = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_sessions", "arguments": {}},
    }
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(create_app(store), base_url=consts.BASE_URL) as local:
        return local.post(consts.MCP_PATH, json=call, headers=headers).json()["result"][
            "content"
        ][0]["text"]


def test_hook_manager_sends_the_token_and_its_computer_name(monkeypatch):
    monkeypatch.delenv(consts.ENV_TOKEN, raising=False)
    assert consts.HEADER_AUTHORIZATION not in hook.request_headers()
    assert hook.request_headers()[consts.HEADER_CLIENT_HOST]

    monkeypatch.setenv(consts.ENV_TOKEN, TOKEN)
    assert hook.request_headers()[consts.HEADER_AUTHORIZATION] == consts.TOKEN_SCHEME + TOKEN


def test_hook_stays_silent_when_the_server_refuses_its_token(monkeypatch, capsys):
    def refuse(path, body):
        raise hook.urllib.error.HTTPError(path, 401, "Unauthorized", None, None)

    monkeypatch.setattr(hook, "post", refuse)
    monkeypatch.setattr("sys.argv", ["hook", consts.EVENT_STOP])
    payload = json.dumps({"session_id": "sid-z"}).encode()
    monkeypatch.setattr("sys.stdin", type("Stdin", (), {"buffer": io.BytesIO(payload)}))

    assert hook.main() == consts.EXIT_OK
    assert capsys.readouterr().out == ""
