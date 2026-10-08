"""Write the inbox hooks into a Claude Code settings.json.

    python -m inbox_mcp.install [--scope user|project] [--uninstall]

Every hook points at the hook manager (`inbox_mcp.hook`) with the event name as its argument.
Other hooks in the file are left alone; running it again replaces the inbox entries.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import consts
from .consts import HOOK_MODULE, INSTALL_EVENTS, SETTINGS_BACKUP_SUFFIX
from .logs import get_logger

log = get_logger(consts.LOG_INSTALL)


def settings_path(scope: str) -> Path:
    base = Path.home() if scope == "user" else Path.cwd()
    return base / ".claude" / "settings.json"


def is_ours(hook: dict) -> bool:
    return HOOK_MODULE in hook.get("args", []) or HOOK_MODULE in hook.get("command", "")


def remove_hooks(settings: dict) -> None:
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        groups = []
        for group in hooks[event]:
            kept = [h for h in group.get("hooks", []) if not is_ours(h)]
            if kept:
                groups.append({**group, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)


def add_hooks(settings: dict, python: str) -> None:
    hooks = settings.setdefault("hooks", {})
    for event, (name, timeout) in INSTALL_EVENTS.items():
        hooks.setdefault(event, []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": python,
                        "args": ["-m", HOOK_MODULE, name],
                        "timeout": timeout,
                    }
                ]
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the inbox hooks into settings.json")
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--settings", type=Path, help="explicit settings.json path")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    path = args.settings or settings_path(args.scope)
    settings = {}
    backup = None
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
        backup = path.with_name(path.name + SETTINGS_BACKUP_SUFFIX)
        shutil.copyfile(path, backup)

    remove_hooks(settings)
    if not args.uninstall:
        add_hooks(settings, sys.executable)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log.info(
        "settings written",
        action="uninstall" if args.uninstall else "install",
        settings=str(path),
        backup=str(backup) if backup else None,
        python=sys.executable,
        events=list(INSTALL_EVENTS),
    )
    action = "Removed inbox hooks from" if args.uninstall else "Installed inbox hooks into"
    print(f"{action} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
