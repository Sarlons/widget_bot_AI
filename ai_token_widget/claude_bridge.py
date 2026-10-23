"""Opt-in installer for the Claude Code status-line bridge.

Claude Code exposes account rate limits only to its status-line command. This
module edits ``~/.claude/settings.json`` to point ``statusLine`` at
``claude_statusline.py`` (source checkout) or at the packaged bridge executable
(installed build).

Safety choices:

* only the ``statusLine`` field is backed up (as an undo record), so secrets
  that may live elsewhere in ``settings.json`` are not copied around;
* install refuses to replace an existing custom status line unless ``--force``;
* uninstall restores the previous field, leaving all other settings untouched.

Usage::

    python -m ai_token_widget.claude_bridge install
    python -m ai_token_widget.claude_bridge status
    python -m ai_token_widget.claude_bridge uninstall
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import claude_statusline

UNDO_NAME = "claude_statusline_undo.json"
BRIDGE_EXE_NAME = "AITokenWidgetBridge.exe"


class BridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallResult:
    changed: bool
    settings_path: Path
    undo_path: Path
    command: str


@dataclass(frozen=True)
class UninstallResult:
    changed: bool
    settings_path: Path
    restored_custom_status_line: bool


def default_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def command_for(
    python_exe: str | None = None, data_dir: Path | str | None = None
) -> str:
    if getattr(sys, "frozen", False):
        if python_exe:
            raise BridgeError("--python is not supported by the packaged bridge")
        executable = _bridge_executable()
        command = f'"{executable}"'
    else:
        executable = Path(python_exe) if python_exe else Path(sys.executable)
        script = Path(claude_statusline.__file__).resolve()
        command = f'"{executable}" "{script}"'
    if data_dir is not None:
        command += f' --data-dir "{Path(data_dir)}"'
    return command


def _bridge_executable() -> Path:
    executable = Path(sys.executable)
    candidates = (
        executable.with_name(BRIDGE_EXE_NAME),
        executable.parent / "AITokenWidgetBridge" / BRIDGE_EXE_NAME,
        executable,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return executable


def _read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        # utf-8-sig tolerates a BOM written by some Windows editors.
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise BridgeError(f"cannot read {path}: {type(exc).__name__}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(f"settings file is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise BridgeError(f"settings file is not a JSON object: {path}")
    return raw


def _write_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix="claude_settings.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def _current_command(settings: dict) -> str | None:
    status = settings.get("statusLine")
    if isinstance(status, dict):
        command = status.get("command")
        return command if isinstance(command, str) else None
    if isinstance(status, str):
        return status
    return None


def _is_ours(command: str | None) -> bool:
    if not command:
        return False
    normalized = command.replace("\\", "/").casefold()
    return (
        "claude_statusline.py" in normalized
        or BRIDGE_EXE_NAME.casefold() in normalized
    )


def _undo_path(data_dir: Path) -> Path:
    return data_dir / UNDO_NAME


def install(
    settings_path: Path | str | None = None,
    data_dir: Path | str | None = None,
    python_exe: str | None = None,
    force: bool = False,
) -> InstallResult:
    settings = Path(settings_path) if settings_path else default_settings_path()
    target_data_dir = Path(data_dir) if data_dir else claude_statusline.data_dir()
    command = command_for(python_exe, data_dir)
    raw = _read_settings(settings)
    current = _current_command(raw)
    previous_status_line = raw.get("statusLine")

    if _is_ours(current) and current == command:
        return InstallResult(
            changed=False,
            settings_path=settings,
            undo_path=_undo_path(target_data_dir),
            command=command,
        )
    if _is_ours(current):
        # The folder or interpreter moved: refresh our command, but keep the
        # original undo record so uninstall still restores what the user had
        # before the first install.
        try:
            existing_undo = _read_undo(_undo_path(target_data_dir))
        except BridgeError:
            existing_undo = {}
        previous_status_line = existing_undo.get("previous_status_line")
    if current and not force and not _is_ours(current):
        raise BridgeError(
            "a different statusLine command is already configured; "
            "re-run with --force to replace it (the previous value is kept for undo)"
        )

    undo_path = _undo_path(target_data_dir)
    undo_path.parent.mkdir(parents=True, exist_ok=True)
    undo = {
        "version": 1,
        "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "settings_path": str(settings),
        "previous_status_line": previous_status_line,
        "installed_command": command,
    }
    undo_path.write_text(json.dumps(undo, indent=2), encoding="utf-8")

    raw["statusLine"] = {"type": "command", "command": command, "padding": 0}
    _write_settings(settings, raw)
    return InstallResult(
        changed=True,
        settings_path=settings,
        undo_path=undo_path,
        command=command,
    )


def _read_undo(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise BridgeError("no undo record; install the bridge first") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError("undo record is damaged") from exc
    if not isinstance(raw, dict):
        raise BridgeError("undo record is damaged")
    return raw


def uninstall(
    settings_path: Path | str | None = None,
    data_dir: Path | str | None = None,
    force: bool = False,
) -> UninstallResult:
    settings = Path(settings_path) if settings_path else default_settings_path()
    target_data_dir = Path(data_dir) if data_dir else claude_statusline.data_dir()
    undo_path = _undo_path(target_data_dir)
    undo = _read_undo(undo_path)
    raw = _read_settings(settings)
    current = _current_command(raw)

    if current and not _is_ours(current) and not force:
        raise BridgeError(
            "statusLine was changed after installation; refusing to overwrite it "
            "(use --force to restore the recorded value)"
        )

    previous = undo.get("previous_status_line")
    if previous is None:
        raw.pop("statusLine", None)
    else:
        raw["statusLine"] = previous
    _write_settings(settings, raw)
    try:
        undo_path.unlink()
    except OSError:
        pass
    return UninstallResult(
        changed=True,
        settings_path=settings,
        restored_custom_status_line=previous is not None,
    )


def status(
    settings_path: Path | str | None = None,
    data_dir: Path | str | None = None,
) -> dict:
    settings = Path(settings_path) if settings_path else default_settings_path()
    target_data_dir = Path(data_dir) if data_dir else claude_statusline.data_dir()
    raw = _read_settings(settings)
    command = _current_command(raw)
    snapshot = claude_statusline.read_snapshot(
        target_data_dir / claude_statusline.SNAPSHOT_NAME
    )
    return {
        "installed": _is_ours(command),
        "settings_path": str(settings),
        "command": command,
        "snapshot": snapshot,
    }


def _print_status(result: dict) -> None:
    print(f"settings: {result['settings_path']}")
    print("bridge installed:", "yes" if result["installed"] else "no")
    if result["installed"]:
        print(f"command: {result['command']}")
    snapshot = result.get("snapshot")
    if not isinstance(snapshot, dict):
        print("quota snapshot: not captured yet")
        return
    print("quota captured:", snapshot.get("captured_at", "unknown"))
    for window in snapshot.get("windows", []):
        if not isinstance(window, dict):
            continue
        print(
            f"  {window.get('label', '?')}: {window.get('used_percent')}% used"
            f" (resets {window.get('resets_at') or 'unknown'})"
        )


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install or remove the Claude Code status-line quota bridge."
    )
    parser.add_argument("action", choices=("install", "uninstall", "status"))
    parser.add_argument("--settings", metavar="PATH", help="override settings.json")
    parser.add_argument(
        "--data-dir", metavar="PATH", help="override widget data directory"
    )
    if getattr(sys, "frozen", False):
        parser.add_argument("--python", dest="python_exe", help=argparse.SUPPRESS)
    else:
        parser.add_argument(
            "--python", dest="python_exe", help="Python executable for the bridge"
        )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.action == "install":
            result = install(
                settings_path=args.settings,
                data_dir=args.data_dir,
                python_exe=args.python_exe,
                force=args.force,
            )
            print(
                "bridge installed" if result.changed else "bridge already installed",
                f"({result.settings_path})",
            )
            print(f"undo record: {result.undo_path}")
            print(f"command: {result.command}")
        elif args.action == "uninstall":
            result = uninstall(
                settings_path=args.settings,
                data_dir=args.data_dir,
                force=args.force,
            )
            print(
                "bridge removed"
                if result.changed
                else "bridge was not installed"
            )
            print(
                "previous custom statusLine restored"
                if result.restored_custom_status_line
                else "no previous statusLine to restore"
            )
        else:
            _print_status(
                status(settings_path=args.settings, data_dir=args.data_dir)
            )
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
