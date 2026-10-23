"""OpenCode adapter.

OpenCode keeps everything in ``opencode.db`` (SQLite):

* ``session_v2`` (fallback: ``session``) has the session inventory and
  cumulative token totals;
* ``session_message`` has per-message token usage, which gives the current
  context size and whether the last turn is still streaming;
* the ``models-dev:catalog`` row in ``kv`` provides the context window for the
  selected model.

The database is opened read-only and only whitelisted tables/columns are
queried. Credential tables (``account``, ``control_account``, ``credential``)
are never touched.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..core.models import Session, SessionState, Usage
from .base import SourceAdapter

DEFAULT_ROOT = Path(
    os.environ.get("OPENCODE_DATA")
    or (Path.home() / ".local" / "share" / "opencode")
)

SESSION_COLUMNS = (
    "id",
    "project_id",
    "directory",
    "version",
    "cost",
    "tokens_input",
    "tokens_output",
    "tokens_reasoning",
    "tokens_cache_read",
    "tokens_cache_write",
    "agent",
    "model",
    "time_created",
    "time_updated",
    "time_archived",
    "parent_id",
)
SENSITIVE_TABLES = frozenset(
    {"account", "account_state", "control_account", "credential"}
)
CATALOG_KEY = "models-dev:catalog"


@dataclass(frozen=True)
class MessageData:
    kind: str
    data: dict
    time_created: datetime | None


def normalize_path(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().strip('"')
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normpath(text)


def parse_millis(value) -> datetime | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 1e12:  # tolerate a seconds-based store
        number *= 1000.0
    try:
        return datetime.fromtimestamp(number / 1000.0, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _usage_from_message(data: dict) -> Usage | None:
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None
    cache = tokens.get("cache")
    if not isinstance(cache, dict):
        cache = {}
    usage = Usage(
        input_tokens=int(tokens.get("input") or 0),
        output_tokens=int(tokens.get("output") or 0),
        reasoning_tokens=int(tokens.get("reasoning") or 0),
        cache_read_tokens=int(cache.get("read") or 0),
        cache_write_tokens=int(cache.get("write") or 0),
    )
    return usage if usage.total else None


def _model_parts(raw) -> tuple[str, str]:
    """OpenCode stores the model as a JSON string: {id, providerID}."""
    if not isinstance(raw, str) or not raw:
        return "unknown", ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw, ""
    if not isinstance(parsed, dict):
        return raw, ""
    model_id = parsed.get("id")
    provider = parsed.get("providerID")
    return (
        model_id if isinstance(model_id, str) and model_id else "unknown",
        provider if isinstance(provider, str) else "",
    )


class OpenCodeAdapter(SourceAdapter):
    name = "opencode"
    display_name = "OpenCode"

    def __init__(
        self,
        root: Path | str | None = None,
        max_age_hours: float = 24.0,
        limit: int = 12,
        running_window_seconds: float = 90.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root) if root else DEFAULT_ROOT
        self.db_path = self.root / "opencode.db"
        self.max_age_hours = max_age_hours
        self.limit = limit
        self.running_window_seconds = running_window_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._catalog: dict[tuple[str, str], int] | None = None

    # -- SQLite helpers -------------------------------------------------

    def _connect(self) -> sqlite3.Connection | None:
        if not self.db_path.exists():
            return None
        try:
            connection = sqlite3.connect(
                f"file:{self.db_path.as_posix()}?mode=ro", uri=True, timeout=1.0
            )
        except sqlite3.Error:
            return None
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = 1")
            connection.execute("PRAGMA busy_timeout = 500")
        except sqlite3.Error:
            connection.close()
            return None
        return connection

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
        try:
            return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        except sqlite3.Error:
            return []

    # -- model metadata -------------------------------------------------

    def _catalog_lookup(self, connection: sqlite3.Connection) -> dict[tuple[str, str], int]:
        if self._catalog is not None:
            return self._catalog
        lookup: dict[tuple[str, str], int] = {}
        if "kv" not in self._tables(connection):
            self._catalog = lookup
            return lookup
        try:
            row = connection.execute(
                "SELECT value FROM kv WHERE key = ?", (CATALOG_KEY,)
            ).fetchone()
        except sqlite3.Error:
            row = None
        if row and row[0]:
            try:
                catalog = json.loads(row[0])
                body = catalog.get("body")
                if isinstance(body, str):
                    body = json.loads(body)
                if isinstance(body, dict):
                    for provider_id, provider in body.items():
                        models = provider.get("models") if isinstance(provider, dict) else None
                        if not isinstance(models, dict):
                            continue
                        for model_id, meta in models.items():
                            if not isinstance(meta, dict):
                                continue
                            limit = meta.get("limit")
                            context = limit.get("context") if isinstance(limit, dict) else None
                            if isinstance(context, int) and context > 0:
                                lookup[(str(provider_id), str(model_id))] = context
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        self._catalog = lookup
        return lookup

    # -- session messages ----------------------------------------------

    def _latest_message(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        kind: str | None = None,
        require_tokens: bool = False,
    ) -> MessageData | None:
        if "session_message" not in self._tables(connection):
            return None
        columns = self._columns(connection, "session_message")
        if not {"session_id", "data"} <= set(columns):
            return None
        order = "seq DESC" if "seq" in columns else "time_created DESC"
        where = "session_id = ?"
        parameters: list[str] = [session_id]
        if kind:
            where += " AND type = ?"
            parameters.append(kind)
        try:
            rows = connection.execute(
                f"SELECT type, data, time_created FROM session_message "
                f"WHERE {where} ORDER BY {order} LIMIT 20",
                parameters,
            ).fetchall()
        except sqlite3.Error:
            return None
        for row in rows:
            try:
                data = json.loads(row["data"]) if row["data"] else {}
            except (TypeError, json.JSONDecodeError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            if require_tokens and _usage_from_message(data) is None:
                continue
            return MessageData(
                kind=str(row["type"] or data.get("role") or ""),
                data=data,
                time_created=parse_millis(row["time_created"]),
            )
        return None

    # -- adapter --------------------------------------------------------

    def sessions(self) -> list[Session]:
        connection = self._connect()
        if connection is None:
            return []
        try:
            tables = self._tables(connection)
            if tables & SENSITIVE_TABLES and not (tables & {"session_v2", "session"}):
                return []
            table = "session_v2" if "session_v2" in tables else "session"
            if table not in tables:
                return []
            columns = set(self._columns(connection, table))
            if not {"id", "time_updated"} <= columns:
                return []
            selected = [column for column in SESSION_COLUMNS if column in columns]
            clauses = ["time_updated >= ?"]
            now = self._now()
            cutoff_ms = (now.timestamp() - self.max_age_hours * 3600) * 1000
            if "time_archived" in columns:
                clauses.append("(time_archived IS NULL OR time_archived = 0)")
            rows = connection.execute(
                f'SELECT {", ".join(selected)} FROM "{table}" '
                f"WHERE {' AND '.join(clauses)} "
                f"ORDER BY time_updated DESC LIMIT ?",
                (cutoff_ms, self.limit),
            ).fetchall()

            projects: dict[str, dict] = {}
            if "project" in tables:
                project_columns = set(self._columns(connection, "project"))
                wanted = [name for name in ("id", "name", "worktree") if name in project_columns]
                if "id" in wanted:
                    for row in connection.execute(
                        f'SELECT {", ".join(wanted)} FROM project'
                    ):
                        projects[str(row["id"])] = dict(row)

            catalog = self._catalog_lookup(connection)
            sessions: list[Session] = []
            for row in rows:
                session_id = str(row["id"])
                updated_at = parse_millis(row["time_updated"])
                started_at = parse_millis(row["time_created"]) if "time_created" in columns else None
                if updated_at is None:
                    continue

                last_message = self._latest_message(connection, session_id)
                last_assistant = self._latest_message(
                    connection, session_id, "assistant", require_tokens=True
                )
                usage_last = (
                    _usage_from_message(last_assistant.data) if last_assistant else None
                )
                model, provider = _model_parts(row["model"] if "model" in columns else None)
                context_window = catalog.get((provider, model))
                if context_window is None and provider:
                    context_window = catalog.get(("", model))

                directory = row["directory"] if "directory" in columns else None
                directory = normalize_path(directory) if isinstance(directory, str) else None
                project = "unknown"
                if directory:
                    project = Path(directory).name or directory
                else:
                    project_row = projects.get(str(row["project_id"]), {}) if "project_id" in columns else {}
                    worktree = project_row.get("worktree")
                    if isinstance(worktree, str) and worktree:
                        project = Path(normalize_path(worktree) or worktree).name
                    elif project_row.get("name"):
                        project = str(project_row["name"])

                activity_at = updated_at
                if last_message and last_message.time_created and last_message.time_created > activity_at:
                    activity_at = last_message.time_created
                age = (now - activity_at).total_seconds()
                last_kind = last_message.kind if last_message else ""
                completed = bool(
                    ((last_message.data.get("time") or {}).get("completed"))
                    if last_message
                    else False
                )
                if (
                    age <= self.running_window_seconds
                    and last_kind == "assistant"
                    and not completed
                ):
                    state = SessionState.RUNNING
                elif age <= self.running_window_seconds and last_kind == "user":
                    state = SessionState.RUNNING
                elif last_kind == "assistant" and completed and age <= 300:
                    state = SessionState.WAITING
                elif age <= self.running_window_seconds:
                    state = SessionState.RUNNING
                else:
                    state = SessionState.IDLE

                usage_total = Usage(
                    input_tokens=int(row["tokens_input"] or 0) if "tokens_input" in columns else 0,
                    output_tokens=int(row["tokens_output"] or 0) if "tokens_output" in columns else 0,
                    reasoning_tokens=int(row["tokens_reasoning"] or 0)
                    if "tokens_reasoning" in columns
                    else 0,
                    cache_read_tokens=int(row["tokens_cache_read"] or 0)
                    if "tokens_cache_read" in columns
                    else 0,
                    cache_write_tokens=int(row["tokens_cache_write"] or 0)
                    if "tokens_cache_write" in columns
                    else 0,
                )
                cost = row["cost"] if "cost" in columns else None
                try:
                    cost_usd = float(cost) if cost is not None else None
                except (TypeError, ValueError):
                    cost_usd = None

                sessions.append(
                    Session(
                        id=session_id,
                        agent=self.name,
                        model=model,
                        project=project or "unknown",
                        state=state,
                        usage_total=usage_total,
                        usage_last=usage_last or Usage(),
                        context_window=context_window,
                        context_used=usage_last.total if usage_last else None,
                        context_estimated=False,
                        cost_usd=cost_usd,
                        started_at=started_at,
                        updated_at=activity_at,
                        cwd=directory,
                        source=provider or "opencode",
                    )
                )
            return sessions
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def probe(self) -> str:
        if not self.db_path.exists():
            return "database not found"
        return "opencode.db"
