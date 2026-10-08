import copy

from inbox_mcp.consts import INSTALL_EVENTS
from inbox_mcp.install import add_hooks, remove_hooks

OTHER = {"type": "command", "command": "node other.js", "timeout": 5}


def existing():
    return {
        "model": "opus",
        "hooks": {
            "Stop": [{"matcher": "", "hooks": [dict(OTHER)]}],
            "PreToolUse": [{"hooks": [dict(OTHER)]}],
        },
    }


def test_add_keeps_other_hooks_and_points_at_manager():
    settings = existing()
    add_hooks(settings, "C:/venv/python.exe")
    assert set(INSTALL_EVENTS) <= set(settings["hooks"])
    assert settings["hooks"]["Stop"][0]["hooks"] == [OTHER]
    ours = settings["hooks"]["Stop"][1]["hooks"][0]
    assert ours["command"] == "C:/venv/python.exe"
    assert ours["args"] == ["-m", "inbox_mcp.hook", "stop"]
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["args"][-1] == "session-start"
    assert "TaskCompleted" not in settings["hooks"] and "TeammateIdle" not in settings["hooks"]


def test_reinstall_does_not_duplicate_and_uninstall_restores():
    original = existing()
    settings = copy.deepcopy(original)
    add_hooks(settings, "old-python")
    remove_hooks(settings)
    add_hooks(settings, "new-python")
    assert len(settings["hooks"]["Stop"]) == 2
    assert settings["hooks"]["Stop"][1]["hooks"][0]["command"] == "new-python"
    remove_hooks(settings)
    assert settings == original


def test_uninstall_drops_empty_hooks_key():
    settings = {}
    add_hooks(settings, "python")
    remove_hooks(settings)
    assert settings == {}
