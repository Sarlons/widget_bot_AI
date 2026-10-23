#!/usr/bin/env python3
"""Claude Code status-line bridge.

Claude Code only exposes account rate limits to its status-line command, not
to the transcript files. This script is intended to be configured as that
command. It:

* reads the status-line JSON from stdin;
* keeps only the rate-limit numbers, reset times and session id;
* writes them atomically to ``%APPDATA%\\AITokenWidget\\claude_rate_limits.json``;
* prints a short status line so the user still sees something useful.

It must stay dependency-free and importable as a plain file: Claude Code runs
it directly with the configured Python interpreter.

This module never writes prompts, transcript paths, cwd, model output or
credentials. Only rate-limit metadata is persisted.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_STDIN_BYTES = 2_000_000
SNAPSHOT_NAME = "claude_rate_limits.json"
WINDOW_ALIASES = (
    ("five_hour", "5h"),
    ("5h", "5h"),
    ("primary", "5h"),
    ("seven_day", "weekly"),
    ("7d", "weekly"),
    ("weekly", "weekly"),
    ("secondary", "weekly"),
)
PERCENT_KEYS = ("used_percentage", "used_percent", "utilization", "percent")
RESET_KEYS = ("resets_at", "reset_at", "resetsAt")


def data_dir() -> Path:
    override = os.environ.get("AITOKENWIDGET_DATA_DIR")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AITokenWidget"
    return Path.home() / ".config" / "ai-token-widget"


def snapshot_path() -> Path:
    return data_dir() / SNAPSHOT_NAME


def _parse_moment(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 1e11:
            number /= 1000.0
        try:
            return datetime.fromtimestamp(number, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return _parse_moment(int(text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _percent(entry: dict):
    for key in PERCENT_KEYS:
        value = entry.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        return max(0.0, min(100.0, float(value)))
    return None


def normalize(payload, captured_at: datetime | None = None) -> dict:
    """Convert a status-line payload into the small snapshot we persist."""
    if not isinstance(payload, dict):
        return {"version": 1, "windows": []}
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        limits = {}

    windows = []
    seen_labels: set[str] = set()
    for key, label in WINDOW_ALIASES:
        if label in seen_labels:
            continue
        entry = limits.get(key)
        if not isinstance(entry, dict):
            continue
        percent = _percent(entry)
        if percent is None:
            continue
        reset = None
        for reset_key in RESET_KEYS:
            reset = _parse_moment(entry.get(reset_key))
            if reset is not None:
                break
        windows.append(
            {
                "label": label,
                "used_percent": percent,
                "resets_at": _iso(reset),
            }
        )
        seen_labels.add(label)

    session_id = payload.get("session_id") or payload.get("sessionId")
    snapshot = {
        "version": 1,
        "captured_at": _iso(captured_at or datetime.now(timezone.utc)),
        "windows": windows,
    }
    if isinstance(session_id, str) and session_id:
        snapshot["session_id"] = session_id
    return snapshot


def write_snapshot(snapshot: dict, path: Path | None = None) -> Path:
    target = path or snapshot_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix="claude_rate_limits.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    return target


def read_snapshot(path: Path | None = None) -> dict | None:
    target = path or snapshot_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def status_text(snapshot: dict) -> str:
    parts = []
    for window in snapshot.get("windows", []):
        if not isinstance(window, dict):
            continue
        try:
            used = float(window.get("used_percent"))
        except (TypeError, ValueError):
            continue
        parts.append(f"{window.get('label', 'quota')} {max(0.0, 100.0 - used):.0f}% left")
    return " · ".join(parts) if parts else "Claude"


def main(argv: list[str] | None = None) -> int:
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--data-dir", default=None)
        arguments, _unknown = parser.parse_known_args(argv)
        target = (
            Path(arguments.data_dir) / SNAPSHOT_NAME
            if arguments.data_dir
            else None
        )

        raw = sys.stdin.read(MAX_STDIN_BYTES)
        payload = json.loads(raw) if raw.strip() else {}
        snapshot = normalize(payload)
        if snapshot.get("windows"):
            write_snapshot(snapshot, target)
        print(status_text(snapshot))
    except Exception:
        # Never break the user's status line because of a parser change.
        print("Claude")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
