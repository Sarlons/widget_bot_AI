#!/usr/bin/env python3
"""Phase 0 diagnostic for the AI Token Widget.

Read-only inventory of the local agent session stores used by the widget:
Claude Code, Codex and OpenCode.

Hard rules (see .claude_project.md):
  * never read or print secret values (API keys, OAuth tokens, credentials);
  * never read .env or the credential tables of the OpenCode database;
  * never write to an agent store: SQLite is opened read-only;
  * only whitelisted tables/columns and usage metadata are reported.

Usage:
    python diagnose.py
    python diagnose.py --json phase0.json
    python diagnose.py --fixtures
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

HOME = Path.home()
ENV_AGENT_RE = re.compile(r"(ANTHROPIC|OPENAI|OPENROUTER|GEMINI|CLAUDE|CODEX|OPENCODE)", re.I)
PROCESS_NAMES = ("claude.exe", "codex.exe", "opencode.exe", "node.exe")
CLAUDE_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)

CLAUDE_DIR = HOME / ".claude"
CODEX_DIR = HOME / ".codex"
OPENCODE_DIR = HOME / ".local" / "share" / "opencode"
OPENCODE_DB = OPENCODE_DIR / "opencode.db"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def short_path(path: Path) -> str:
    try:
        return "~" + str(path.relative_to(HOME)).replace("\\", "/")
    except ValueError:
        return str(path)


def epoch_to_iso(value: int | float | None) -> str | None:
    """Accept seconds or milliseconds and render UTC ISO-8601."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value > 1e12:  # milliseconds
        value /= 1000.0
    try:
        return dt.datetime.fromtimestamp(value, dt.timezone.utc).replace(microsecond=0).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def age_minutes(path: Path) -> float | None:
    try:
        return round((dt.datetime.now().timestamp() - path.stat().st_mtime) / 60, 1)
    except OSError:
        return None


def newest_file(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda p: p.stat().st_mtime, default=None)


def dir_info(path: Path, max_files: int = 5000) -> dict:
    info = {
        "path": short_path(path),
        "exists": path.exists(),
        "files": 0,
        "bytes": 0,
        "newest_age_min": None,
        "truncated": False,
    }
    if not path.exists():
        return info
    newest_mtime = 0.0
    try:
        for root, _dirs, names in os.walk(path):
            for name in names:
                if info["files"] >= max_files:
                    break
                try:
                    stat = os.stat(os.path.join(root, name))
                except OSError:
                    continue
                info["files"] += 1
                info["bytes"] += stat.st_size
                newest_mtime = max(newest_mtime, stat.st_mtime)
            if info["files"] >= max_files:
                break
    except OSError:
        pass
    if newest_mtime:
        age = (dt.datetime.now().timestamp() - newest_mtime) / 60
        info["newest_age_min"] = round(age, 1)
    info["truncated"] = info["files"] >= max_files
    return info


def read_jsonl(path: Path, max_lines: int = 5000) -> list[dict]:
    records: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
    except OSError:
        pass
    return records


def read_jsonl_tail(path: Path, max_bytes: int = 1_500_000) -> list[dict]:
    """Parse the last chunk of a JSONL file.

    Agent logs grow without bound; the newest quota snapshot is always at the
    end, so reading the tail keeps the widget (and this probe) fast.
    """
    records: list[dict] = []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                handle.readline()  # discard the partial first line
            payload = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return records
    for line in payload.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def sqlite_ro(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = 1")
    return connection


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows}


def columns_of(connection: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
    except sqlite3.Error:
        return []


def env_inventory() -> dict:
    """Report variable names and whether they are set. Never values."""
    result = {}
    for name in sorted(os.environ):
        if ENV_AGENT_RE.search(name):
            result[name] = "SET" if os.environ.get(name) else "EMPTY"
    return result


# --------------------------------------------------------------------------
# Claude Code
# --------------------------------------------------------------------------


def scan_claude() -> dict:
    projects = CLAUDE_DIR / "projects"
    files = sorted(projects.rglob("*.jsonl")) if projects.exists() else []
    newest = newest_file(files)

    usage_messages = 0
    tokens: Counter[str] = Counter()
    models: set[str] = set()
    has_rate_limits = False
    message_types: Counter[str] = Counter()

    if newest:
        for record in read_jsonl(newest, max_lines=800):
            message_types[str(record.get("type"))] += 1
            if "rate_limits" in record:
                has_rate_limits = True
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            model = message.get("model")
            if isinstance(model, str):
                models.add(model)
            usage = message.get("usage")
            if isinstance(usage, dict):
                usage_messages += 1
                for field in CLAUDE_USAGE_FIELDS:
                    value = usage.get(field)
                    if isinstance(value, (int, float)):
                        tokens[field] += int(value)
                cache_creation = usage.get("cache_creation")
                if isinstance(cache_creation, dict):
                    for key, value in cache_creation.items():
                        if key.endswith("_tokens") and isinstance(value, (int, float)):
                            tokens[key] += int(value)

    status_line = False
    settings_keys: list[str] = []
    settings_path = CLAUDE_DIR / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(settings, dict):
                settings_keys = sorted(settings)
                status_line = bool(settings.get("statusLine"))
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "root": short_path(CLAUDE_DIR),
        "root_exists": CLAUDE_DIR.exists(),
        "projects_dir": short_path(projects),
        "session_files": len(files),
        "newest_session": newest.name if newest else None,
        "newest_age_min": age_minutes(newest) if newest else None,
        "newest_messages": message_types.most_common(6),
        "messages_with_usage": usage_messages,
        "token_totals": dict(tokens),
        "models": sorted(models),
        "rate_limits_in_logs": has_rate_limits,
        "statusline_configured": status_line,
        "settings_keys": settings_keys,
        "credentials_present": (CLAUDE_DIR / ".credentials.json").exists(),
        "capabilities": {
            "sessions": bool(files),
            "tokens": usage_messages > 0,
            "context_window": False,
            "quota": "bridge" if status_line else "not_configured",
        },
    }


# --------------------------------------------------------------------------
# Codex
# --------------------------------------------------------------------------


def scan_codex() -> dict:
    sessions_dir = CODEX_DIR / "sessions"
    files = sorted(sessions_dir.rglob("*.jsonl")) if sessions_dir.exists() else []
    newest = newest_file(files)

    event_types: Counter[str] = Counter()
    last_token_count: dict | None = None
    last_model: str | None = None
    cli_version: str | None = None
    context_window: int | None = None

    if newest:
        for record in read_jsonl_tail(newest):
            event_type = str(record.get("type"))
            event_types[event_type] += 1
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if event_type == "session_meta":
                version = payload.get("cli_version")
                if isinstance(version, str):
                    cli_version = version
            elif event_type == "turn_context":
                model = payload.get("model")
                if isinstance(model, str):
                    last_model = model
            elif event_type == "event_msg" and payload.get("type") == "token_count":
                last_token_count = payload
                candidate = (payload.get("info") or {}).get("model_context_window")
                if isinstance(candidate, int):
                    context_window = candidate

    rate_limits = (last_token_count or {}).get("rate_limits") or {}
    info = (last_token_count or {}).get("info") or {}
    if context_window is not None:
        info = {**info, "model_context_window": context_window}
    windows = {}
    for name in ("primary", "secondary"):
        window = rate_limits.get(name)
        if isinstance(window, dict):
            windows[name] = {
                "used_percent": window.get("used_percent"),
                "window_minutes": window.get("window_minutes"),
                "resets_at": epoch_to_iso(window.get("resets_at")),
            }
    credits = rate_limits.get("credits")
    if isinstance(credits, dict):
        credits = {
            "has_credits": credits.get("has_credits"),
            "unlimited": credits.get("unlimited"),
            "balance": credits.get("balance"),
        }

    threads: dict = {"available": False}
    db_path = CODEX_DIR / "state_5.sqlite"
    if db_path.exists():
        try:
            with sqlite_ro(db_path) as connection:
                if "threads" in table_names(connection):
                    columns = set(columns_of(connection, "threads"))
                    if {"updated_at", "model", "tokens_used"} <= columns:
                        now = dt.datetime.now(dt.timezone.utc).timestamp()
                        rows = connection.execute(
                            "SELECT updated_at, model, tokens_used, source "
                            "FROM threads ORDER BY updated_at DESC LIMIT 3"
                        ).fetchall()
                        total = connection.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
                        active_24h = connection.execute(
                            "SELECT COUNT(*) FROM threads WHERE updated_at > ?",
                            (now - 86400,),
                        ).fetchone()[0]
                        threads = {
                            "available": True,
                            "total": total,
                            "active_24h": active_24h,
                            "recent": [
                                {
                                    "updated_at": epoch_to_iso(row["updated_at"]),
                                    "model": row["model"],
                                    "tokens_used": row["tokens_used"],
                                    "source": row["source"],
                                }
                                for row in rows
                            ],
                        }
        except sqlite3.Error as exc:
            threads = {"available": False, "error": type(exc).__name__}

    return {
        "root": short_path(CODEX_DIR),
        "root_exists": CODEX_DIR.exists(),
        "session_files": len(files),
        "newest_session": newest.name if newest else None,
        "newest_age_min": age_minutes(newest) if newest else None,
        "cli_version": cli_version,
        "event_types": event_types.most_common(8),
        "last_model": last_model,
        "model_context_window": info.get("model_context_window"),
        "total_token_usage": {
            key: value for key, value in (info.get("total_token_usage") or {}).items()
            if key in TOKEN_FIELDS
        },
        "rate_limits": {"available": bool(rate_limits), "windows": windows, "credits": credits},
        "threads_db": threads,
        "auth_present": (CODEX_DIR / "auth.json").exists(),
        "capabilities": {
            "sessions": bool(files) or bool(threads.get("available")),
            "tokens": bool(last_token_count),
            "context_window": info.get("model_context_window") is not None,
            "quota": "exact" if rate_limits else "unavailable",
        },
    }


# --------------------------------------------------------------------------
# OpenCode
# --------------------------------------------------------------------------


OPENCODE_SESSION_COLUMNS = (
    "model",
    "agent",
    "version",
    "cost",
    "tokens_input",
    "tokens_output",
    "tokens_reasoning",
    "tokens_cache_read",
    "tokens_cache_write",
    "time_created",
    "time_updated",
)


def scan_opencode() -> dict:
    result: dict = {
        "root": short_path(OPENCODE_DIR),
        "root_exists": OPENCODE_DIR.exists(),
        "db": short_path(OPENCODE_DB),
        "db_exists": OPENCODE_DB.exists(),
        "sensitive_tables_skipped": ["account", "account_state", "control_account", "credential"],
    }
    if not OPENCODE_DB.exists():
        result["capabilities"] = {
            "sessions": False,
            "tokens": False,
            "context_window": False,
            "quota": "unavailable",
        }
        return result

    try:
        with sqlite_ro(OPENCODE_DB) as connection:
            tables = table_names(connection)
            result["tables"] = sorted(tables)
            table = "session_v2" if "session_v2" in tables else "session" if "session" in tables else None
            if table is None:
                result["error"] = "no session table"
            else:
                columns = set(columns_of(connection, table))
                selected = [column for column in OPENCODE_SESSION_COLUMNS if column in columns]
                total = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000
                active_10m = (
                    connection.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE time_updated > ?', (now_ms - 600000,)
                    ).fetchone()[0]
                    if "time_updated" in columns
                    else None
                )
                rows = connection.execute(
                    f'SELECT {", ".join(selected)} FROM "{table}" '
                    f'ORDER BY time_updated DESC LIMIT 3'
                    if "time_updated" in columns
                    else f'SELECT {", ".join(selected)} FROM "{table}" LIMIT 3'
                ).fetchall()
                result["session_table"] = table
                result["session_count"] = total
                result["active_10m"] = active_10m
                result["recent"] = [
                    {
                        column: epoch_to_iso(row[column])
                        if column.startswith("time_") and row[column]
                        else row[column]
                        for column in selected
                    }
                    for row in rows
                ]
                result["capabilities"] = {
                    "sessions": True,
                    "tokens": "tokens_input" in columns,
                    "context_window": False,
                    "quota": "provider_dependent",
                }
            result["log_age_min"] = age_minutes(OPENCODE_DIR / "log" / "opencode.log") if (
                OPENCODE_DIR / "log" / "opencode.log"
            ).exists() else None
    except sqlite3.Error as exc:
        result["error"] = type(exc).__name__
        result["capabilities"] = {
            "sessions": False,
            "tokens": False,
            "context_window": False,
            "quota": "unavailable",
        }
    return result


# --------------------------------------------------------------------------
# Processes (names only: command lines can contain secrets)
# --------------------------------------------------------------------------


def scan_processes() -> dict:
    counts: Counter[str] = Counter()
    try:
        completed = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
        for row in csv.reader(io.StringIO(completed.stdout)):
            if len(row) >= 1:
                name = row[0].strip().lower()
                if name in PROCESS_NAMES:
                    counts[name] += 1
    except (OSError, subprocess.SubprocessError):
        return {"available": False}
    return {
        "available": True,
        "counts": dict(counts),
        "note": "claude.exe may be the Claude desktop app, not Claude Code CLI",
        "psutil_installed": _has_module("psutil"),
    }


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------
# Sanitized fixtures
# --------------------------------------------------------------------------


def _zero_identifier(value: str) -> str:
    if len(value) >= 32:
        return "00000000-0000-4000-8000-000000000000"
    return "<id>"


def sanitize_tree(node, key: str = ""):
    """Recursively remove identifiers, paths and content from a record."""
    if isinstance(node, dict):
        cleaned = {}
        for name, value in node.items():
            lower = name.lower()
            if any(word in lower for word in ("content", "prompt", "text", "title", "message_body")):
                continue
            if lower in ("cwd", "directory", "path", "rollout_path", "first_user_message"):
                cleaned[name] = "<redacted>"
            elif lower in ("id", "session_id", "thread_id", "turn_id", "response_id", "uuid"):
                cleaned[name] = _zero_identifier(value) if isinstance(value, str) else value
            elif lower in ("base_instructions", "history_base", "instructions", "developer_instructions"):
                continue
            else:
                cleaned[name] = sanitize_tree(value, name)
        return cleaned
    if isinstance(node, list):
        return [sanitize_tree(item, key) for item in node]
    return node


def build_fixtures(destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    manifest = {
        "schema": 1,
        "generated_at": iso_now(),
        "note": (
            "Numeric token counts preserved; identifiers, paths, prompts and "
            "message content removed. Never regenerate from a store containing "
            "unreviewed secrets without re-running this sanitizer."
        ),
        "sources": {},
    }

    # Claude Code: up to three assistant turns with usage.
    projects = CLAUDE_DIR / "projects"
    claude_files = sorted(projects.rglob("*.jsonl")) if projects.exists() else []
    newest_claude = newest_file(claude_files)
    if newest_claude:
        kept = []
        for record in read_jsonl(newest_claude, max_lines=800):
            message = record.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
            if not isinstance(usage, dict):
                continue
            cleaned_usage = {
                field: usage[field] for field in CLAUDE_USAGE_FIELDS if field in usage
            }
            cache_creation = usage.get("cache_creation")
            if isinstance(cache_creation, dict):
                cleaned_usage["cache_creation"] = {
                    key: value
                    for key, value in cache_creation.items()
                    if key.endswith("_tokens") and isinstance(value, (int, float))
                }
            kept.append(
                {
                    "type": record.get("type"),
                    "timestamp": record.get("timestamp"),
                    "sessionId": "00000000-0000-4000-8000-000000000000",
                    "version": record.get("version"),
                    "cwd": "<redacted>",
                    "message": {
                        "role": message.get("role"),
                        "model": message.get("model"),
                        "usage": cleaned_usage,
                    },
                }
            )
            if len(kept) >= 3:
                break
        path = destination / "claude_code_usage.jsonl"
        path.write_text(
            "\n".join(json.dumps(item, sort_keys=True) for item in kept) + "\n",
            encoding="utf-8",
        )
        written.append(path.name)
        manifest["sources"]["claude_code"] = {"format": "jsonl", "records": len(kept)}

    # Codex: latest token_count event plus the latest thread rows.
    sessions = CODEX_DIR / "sessions"
    codex_files = sorted(sessions.rglob("*.jsonl")) if sessions.exists() else []
    newest_codex = newest_file(codex_files)
    if newest_codex:
        latest = None
        model = None
        context_window = None
        for record in read_jsonl_tail(newest_codex):
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if record.get("type") == "turn_context" and isinstance(payload.get("model"), str):
                model = payload["model"]
            if record.get("type") == "event_msg" and payload.get("type") == "token_count":
                latest = {"type": "event_msg", "payload": payload}
                candidate = (payload.get("info") or {}).get("model_context_window")
                if isinstance(candidate, int):
                    context_window = candidate
        if latest:
            latest["payload"].pop("response_id", None)
            fixture = sanitize_tree(latest)
            if context_window is not None:
                fixture["payload"]["info"].setdefault("model_context_window", context_window)
            fixture["payload"]["info"]["total_token_usage"] = {
                key: value
                for key, value in fixture["payload"]["info"]["total_token_usage"].items()
                if key in TOKEN_FIELDS
            }
            fixture["model"] = model
            path = destination / "codex_token_count.json"
            path.write_text(json.dumps(fixture, indent=2, sort_keys=True), encoding="utf-8")
            written.append(path.name)
            manifest["sources"]["codex_token_count"] = {"format": "json", "records": 1}

    db_path = CODEX_DIR / "state_5.sqlite"
    if db_path.exists():
        try:
            with sqlite_ro(db_path) as connection:
                if "threads" in table_names(connection):
                    rows = connection.execute(
                        "SELECT updated_at, model, tokens_used, source, cli_version "
                        "FROM threads ORDER BY updated_at DESC LIMIT 2"
                    ).fetchall()
                    payload = [
                        {
                            "updated_at": epoch_to_iso(row["updated_at"]),
                            "model": row["model"],
                            "tokens_used": row["tokens_used"],
                            "source": row["source"],
                            "cli_version": row["cli_version"],
                        }
                        for row in rows
                    ]
                    path = destination / "codex_threads.json"
                    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                    written.append(path.name)
                    manifest["sources"]["codex_threads"] = {"format": "json", "records": len(payload)}
        except sqlite3.Error:
            pass

    # OpenCode: whitelisted columns from the newest session.
    if OPENCODE_DB.exists():
        try:
            with sqlite_ro(OPENCODE_DB) as connection:
                tables = table_names(connection)
                table = "session_v2" if "session_v2" in tables else "session" if "session" in tables else None
                if table:
                    columns = set(columns_of(connection, table))
                    selected = [column for column in OPENCODE_SESSION_COLUMNS if column in columns]
                    row = connection.execute(
                        f'SELECT {", ".join(selected)} FROM "{table}" '
                        + ('ORDER BY time_updated DESC LIMIT 1' if "time_updated" in columns else "LIMIT 1")
                    ).fetchone()
                    if row:
                        payload = {
                            column: row[column] for column in selected
                        }
                        for key, value in list(payload.items()):
                            if key.startswith("time_") and value:
                                payload[key] = epoch_to_iso(value)
                        path = destination / "opencode_session.json"
                        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
                        written.append(path.name)
                        manifest["sources"]["opencode_session"] = {"format": "json", "records": 1}
        except sqlite3.Error:
            pass

    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written.append(manifest_path.name)
    return written


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------


def build_report() -> dict:
    claude = scan_claude()
    codex = scan_codex()
    opencode = scan_opencode()
    processes = scan_processes()
    return {
        "tool": "ai-token-widget-diagnose",
        "schema": 1,
        "generated_at": iso_now(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "env_vars": env_inventory(),
            "psutil": _has_module("psutil"),
        },
        "stores": {
            "claude_code": dir_info(CLAUDE_DIR),
            "codex": dir_info(CODEX_DIR),
            "opencode": dir_info(OPENCODE_DIR),
        },
        "providers": {
            "claude_code": claude,
            "codex": codex,
            "opencode": opencode,
        },
        "processes": processes,
        "summary": {
            name: provider["capabilities"]
            for name, provider in (
                ("claude_code", claude),
                ("codex", codex),
                ("opencode", opencode),
            )
        },
    }


def print_report(report: dict) -> None:
    print("AI TOKEN WIDGET - PHASE 0 DIAGNOSTIC")
    print(f"generated: {report['generated_at']}")
    print(f"python: {report['environment']['python']} | platform: {report['environment']['platform']}")
    print()

    print("[1] ENVIRONMENT (names only, never values)")
    env_vars = report["environment"]["env_vars"]
    if env_vars:
        for name, state in env_vars.items():
            print(f"  {name}: {state}")
    else:
        print("  no agent-related variables")
    print(f"  psutil installed: {report['environment']['psutil']}")
    print()

    print("[2] STORES")
    for name, info in report["stores"].items():
        suffix = "+" if info.get("truncated") else ""
        print(
            f"  {name:<12} {info['path']} exists={info['exists']} "
            f"files={info['files']}{suffix} newest_age_min={info['newest_age_min']}"
        )
    print()

    claude = report["providers"]["claude_code"]
    print("[3] CLAUDE CODE")
    print(f"  session files: {claude['session_files']} | newest: {claude['newest_session']}")
    print(f"  messages with usage: {claude['messages_with_usage']} | models: {claude['models']}")
    print(f"  token totals: {claude['token_totals']}")
    print(
        f"  rate limits in logs: {claude['rate_limits_in_logs']} | "
        f"statusLine configured: {claude['statusline_configured']}"
    )
    print(f"  credentials present: {claude['credentials_present']} (not read)")
    print(f"  capabilities: {claude['capabilities']}")
    print()

    codex = report["providers"]["codex"]
    print("[4] CODEX")
    print(
        f"  session files: {codex['session_files']} | cli: {codex['cli_version']} | "
        f"model: {codex['last_model']}"
    )
    print(f"  context window: {codex['model_context_window']}")
    print(f"  last total usage: {codex['total_token_usage']}")
    limits = codex["rate_limits"]
    print(f"  rate limits available: {limits['available']}")
    for window_name, window in (limits.get("windows") or {}).items():
        print(
            f"    {window_name}: {window.get('used_percent')}% used / "
            f"{window.get('window_minutes')} min, resets {window.get('resets_at')}"
        )
    print(f"  credits: {limits.get('credits')}")
    threads = codex["threads_db"]
    print(
        f"  threads db: available={threads.get('available')} "
        f"total={threads.get('total')} active_24h={threads.get('active_24h')}"
    )
    print(f"  capabilities: {codex['capabilities']}")
    print()

    opencode = report["providers"]["opencode"]
    print("[5] OPENCODE")
    print(f"  db: {opencode['db']} exists={opencode['db_exists']}")
    if "session_table" in opencode:
        print(
            f"  table: {opencode['session_table']} | sessions: {opencode.get('session_count')} | "
            f"active(10m): {opencode.get('active_10m')}"
        )
        for row in opencode.get("recent", []):
            print(
                f"    model={row.get('model')} in={row.get('tokens_input')} "
                f"out={row.get('tokens_output')} updated={row.get('time_updated')}"
            )
    if "error" in opencode:
        print(f"  error: {opencode['error']}")
    print(f"  sensitive tables skipped: {', '.join(opencode['sensitive_tables_skipped'])}")
    print(f"  capabilities: {opencode['capabilities']}")
    print()

    print("[6] PROCESSES (image names only)")
    processes = report["processes"]
    if processes.get("available"):
        print(f"  counts: {processes['counts']}")
        print(f"  note: {processes['note']}")
    else:
        print("  tasklist unavailable")
    print()

    print("[7] SUMMARY")
    for name, caps in report["summary"].items():
        print(
            f"  {name:<12} sessions={caps['sessions']} tokens={caps['tokens']} "
            f"context={caps['context_window']} quota={caps['quota']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Phase 0 inventory for the AI Token Widget.")
    parser.add_argument("--json", metavar="PATH", help="also write the report as JSON")
    parser.add_argument(
        "--fixtures",
        nargs="?",
        const=str(Path(__file__).parent / "tests" / "fixtures"),
        metavar="DIR",
        help="write sanitized fixtures (default: tests/fixtures)",
    )
    args = parser.parse_args(argv)

    report = build_report()
    print_report(report)

    if args.json:
        target = Path(args.json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport written: {target}")

    if args.fixtures:
        destination = Path(args.fixtures)
        written = build_fixtures(destination)
        print(f"\nfixtures written: {destination}")
        for name in written:
            print(f"  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
