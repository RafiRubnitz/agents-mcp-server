"""The Claude Code plugin files at the repo root must agree with the code."""

import json
import os
import subprocess
import sys
from pathlib import Path

from inbox_mcp import consts
from inbox_mcp.logs import get_logs_dir

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_plugin_hooks_cover_the_same_events_as_the_installer():
    hooks = read_json("hooks/hooks.json")["hooks"]
    assert set(hooks) == set(consts.INSTALL_EVENTS)
    for claude_event, (manager_event, _timeout) in consts.INSTALL_EVENTS.items():
        args = hooks[claude_event][0]["hooks"][0]["args"]
        assert args[-1] == manager_event
        assert args[-2].endswith("/hooks/run_hook.py")


def test_plugin_points_at_the_server_address():
    server = read_json(".mcp.json")["mcpServers"][consts.SERVER_NAME]
    # Claude Code fills ${VAR:-default}: another computer's server and the token come from
    # the same environment variables the hook manager reads.
    assert server == {
        "type": "http",
        "url": "${%s:-%s}%s" % (consts.ENV_URL, consts.BASE_URL, consts.MCP_PATH),
        "headers": {
            consts.HEADER_AUTHORIZATION: "%s${%s:-}" % (consts.TOKEN_SCHEME, consts.ENV_TOKEN)
        },
    }


def test_marketplace_lists_the_plugin():
    plugin = read_json(".claude-plugin/plugin.json")
    marketplace = read_json(".claude-plugin/marketplace.json")
    assert [p["name"] for p in marketplace["plugins"]] == [plugin["name"]]


def test_plugin_launcher_runs_the_hook_manager_without_an_install(tmp_path):
    env = {**os.environ, consts.ENV_URL: "http://127.0.0.1:9", consts.ENV_LOGS: str(tmp_path)}
    env.pop("PYTHONPATH", None)
    done = subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "run_hook.py"), consts.EVENT_STOP],
        input=json.dumps({"session_id": "sid-p"}).encode(),
        capture_output=True,
        cwd=tmp_path,
        env=env,
    )
    assert done.returncode == consts.EXIT_OK
    assert done.stdout == b"" and done.stderr == b""
    assert "session_id='sid-p' outcome='server unreachable'" in next(
        tmp_path.glob("hook_*.log")
    ).read_text(encoding="utf-8")


def test_logs_go_to_the_checkout_or_next_to_the_database(monkeypatch, tmp_path):
    monkeypatch.delenv(consts.ENV_LOGS)
    monkeypatch.setattr(consts, "REPO_DIR", tmp_path)
    assert get_logs_dir() == consts.INSTALLED_LOGS_DIR

    (tmp_path / consts.REPO_MARKER).mkdir()
    assert get_logs_dir() == consts.LOGS_DIR
