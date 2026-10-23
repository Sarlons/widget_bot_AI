"""Codex adapter.

Two local sources, both read-only:

* ``state_5.sqlite`` -> ``threads``: inventory, model, cwd, timestamps and the
  cumulative ``tokens_used`` for each thread.
* ``sessions/**.jsonl`` rollout tail: the last ``token_count`` event carries
  exact rate-limit windows (5h / weekly), the context window and per-turn usage.

Rollouts are only read from the tail and cached by (mtime, size), so polling
stays cheap even though some threads contain tens of millions of tokens.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from ..core.models import Confidence, Quota, QuotaWindow, Session, SessionState, Usage
from .base import SourceAdapter

DEFAULT_ROOT = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
TAIL_BYTES = 1_500_000
THREAD_COLUMNS = (
    "id",
    "updated_at",
    "created_at",
    "model",
    "cwd",
    "tokens_used",
    "source",
    "rollout_path",
)
CACHE_LIMIT = 64


@dataclass(frozen=True)
class RolloutData:
    model: str | None = None
    cwd: str | None = None
    usage_total: Usage | None = None
    usage_last: Usage | None = None
    context_window: int | None = None
    quota: Quota | None = None
    rate_limit_reached: bool = False


def normalize_windows_path(value: str | None) -> str | None:
    """Strip the extended-length prefix and normalize separators."""
    if not value:
        return None
    text = value.strip().strip('"')
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normpath(text)


def _parse_epoch(value) -> datetime | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1e12:
        number /= 1000.0
    try:
        return datetime.fromtimestamp(number, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _usage_from(raw) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    input_tokens = int(raw.get("input_tokens") or 0)
    fields = {
        "input_tokens": input_tokens,
        "output_tokens": int(raw.get("output_tokens") or 0),
        # Codex reports cached input as a subset of input_tokens. Keep both
        # counters for context, but do not add the cache again to billed input.
        "cache_read_tokens": int(raw.get("cached_input_tokens") or 0),
        "cache_write_tokens": int(raw.get("cache_write_input_tokens") or 0),
        "reasoning_tokens": int(raw.get("reasoning_output_tokens") or 0),
        "billed_input_tokens": input_tokens,
    }
    total = raw.get("total_tokens")
    if isinstance(total, int):
        fields["reported_total"] = total
    if not any(fields.values()):
        return None
    return Usage(**fields)


def _window_label(minutes: int | None, fallback: str) -> str:
    if minutes == 300:
        return "5h"
    if minutes == 10080:
        return "weekly"
    if minutes and minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes and minutes % 60 == 0:
        return f"{minutes // 60}h"
    return fallback


def _quota_from(raw, captured_at: datetime) -> Quota | None:
    if not isinstance(raw, dict) or not raw:
        return None
    windows: list[QuotaWindow] = []
    for key, fallback in (("primary", "5h"), ("secondary", "weekly")):
        window = raw.get(key)
        if not isinstance(window, dict):
            continue
        try:
            percent = float(window.get("used_percent") or 0.0)
        except (TypeError, ValueError):
            continue
        minutes = window.get("window_minutes")
        minutes = int(minutes) if isinstance(minutes, (int, float)) else None
        windows.append(
            QuotaWindow(
                label=_window_label(minutes, fallback),
                used_percent=max(0.0, percent),
                window_minutes=minutes,
                resets_at=_parse_epoch(window.get("resets_at")),
            )
        )

    credits = raw.get("credits")
    credits_usd = None
    if isinstance(credits, dict) and credits.get("has_credits") is not False:
        try:
            credits_usd = float(credits.get("balance"))
        except (TypeError, ValueError):
            credits_usd = None

    if not windows and credits_usd is None:
        return None
    return Quota(
        confidence=Confidence.EXACT,
        windows=tuple(windows),
        plan=raw.get("plan_type"),
        credits_usd=credits_usd,
        source="codex-token-count",
        captured_at=captured_at,
    )


def select_shared_quota(rollouts: Iterable[RolloutData]) -> Quota | None:
    """Return the freshest rate-limit snapshot across Codex sessions.

    Codex rate limits are account-wide. Each rollout tail only contains the
    snapshot captured at its own last token-count event, so showing one value
    per session makes the same quota look different from card to card.
    """
    best_any: Quota | None = None
    best_any_time: datetime | None = None
    best_windows: Quota | None = None
    best_windows_time: datetime | None = None
    for rollout in rollouts:
        quota = rollout.quota
        if quota is None:
            continue
        captured = quota.captured_at or datetime.min.replace(tzinfo=timezone.utc)
        if best_any is None or best_any_time is None or captured > best_any_time:
            best_any = quota
            best_any_time = captured
        if not quota.windows:
            continue
        if (
            best_windows is None
            or best_windows_time is None
            or captured > best_windows_time
        ):
            best_windows = quota
            best_windows_time = captured
    # A credits-only snapshot is useful only when no session has windows.
    return best_windows or best_any


def apply_window_rollover(quota: Quota | None, now: datetime) -> Quota | None:
    """A window whose reset time has passed starts again at 0% used."""
    if quota is None or not quota.windows:
        return quota
    changed = False
    windows = []
    for window in quota.windows:
        if window.resets_at is not None and window.resets_at <= now:
            windows.append(
                QuotaWindow(
                    label=window.label,
                    used_percent=0.0,
                    window_minutes=window.window_minutes,
                    resets_at=None,
                )
            )
            changed = True
        else:
            windows.append(window)
    if not changed:
        return quota
    return Quota(
        confidence=quota.confidence,
        windows=tuple(windows),
        plan=quota.plan,
        credits_usd=quota.credits_usd,
        source=quota.source,
        captured_at=quota.captured_at,
    )


def _tail_records(path: Path, max_bytes: int = TAIL_BYTES) -> list[dict]:
    records: list[dict] = []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                handle.readline()  # drop the partial first line
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return records
    for line in text.splitlines():
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


def _project_name(cwd: str | None) -> str:
    if not cwd:
        return "unknown"
    cleaned = normalize_windows_path(cwd) or ""
    return Path(cleaned).name or cleaned or "unknown"


class CodexAdapter(SourceAdapter):
    name = "codex"
    display_name = "Codex"

    def __init__(
        self,
        root: Path | str | None = None,
        max_age_hours: float = 24.0,
        limit: int = 12,
        running_window_seconds: float = 90.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root) if root else DEFAULT_ROOT
        self.max_age_hours = max_age_hours
        self.limit = limit
        self.running_window_seconds = running_window_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._state_db: Path | None | bool = False
        self._cache: dict[str, tuple[int, int, RolloutData]] = {}

    # -- SQLite ---------------------------------------------------------

    def _find_state_db(self) -> Path | None:
        if self._state_db is not False:
            return self._state_db  # type: ignore[return-value]
        candidates = sorted(self.root.glob("state_*.sqlite"))
        candidates += sorted(self.root.glob("state.sqlite"))
        for candidate in candidates:
            connection = None
            try:
                connection = sqlite3.connect(
                    f"file:{candidate.as_posix()}?mode=ro", uri=True, timeout=1.0
                )
                row = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='threads'"
                ).fetchone()
                if row:
                    self._state_db = candidate
                    return candidate
            except sqlite3.Error:
                continue
            finally:
                if connection is not None:
                    connection.close()
        self._state_db = None
        return None

    def _thread_rows(self, cutoff: float) -> list[dict]:
        db = self._find_state_db()
        if db is None:
            return []
        for attempt in range(2):
            try:
                connection = sqlite3.connect(
                    f"file:{db.as_posix()}?mode=ro", uri=True, timeout=1.0
                )
                try:
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA query_only = 1")
                    connection.execute("PRAGMA busy_timeout = 500")
                    available = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(threads)")
                    }
                    selected = [column for column in THREAD_COLUMNS if column in available]
                    if not {"id", "updated_at"} <= set(selected):
                        return []
                    rows = connection.execute(
                        f'SELECT {", ".join(selected)} FROM threads '
                        "WHERE updated_at >= ? ORDER BY updated_at DESC LIMIT ?",
                        (cutoff, self.limit),
                    ).fetchall()
                    return [dict(row) for row in rows]
                finally:
                    connection.close()
            except sqlite3.OperationalError:
                if attempt == 0:
                    time.sleep(0.05)
                    continue
                return []
            except sqlite3.Error:
                return []
        return []

    # -- rollout --------------------------------------------------------

    def _read_rollout(self, path: Path) -> RolloutData:
        try:
            stat = path.stat()
        except OSError:
            return RolloutData()
        key = str(path)
        cached = self._cache.get(key)
        signature = (stat.st_mtime_ns, stat.st_size)
        if cached and cached[:2] == signature:
            return cached[2]

        model = None
        cwd = None
        usage_total = None
        usage_last = None
        context_window = None
        quota = None
        reached = False
        captured_at = self._now()

        for record in _tail_records(path):
            record_type = record.get("type")
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if record_type == "turn_context":
                candidate = payload.get("model")
                if isinstance(candidate, str):
                    model = candidate
            elif record_type == "session_meta":
                candidate = payload.get("cwd")
                if isinstance(candidate, str):
                    cwd = candidate
            elif record_type == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info")
                if isinstance(info, dict):
                    usage_total = _usage_from(info.get("total_token_usage")) or usage_total
                    usage_last = _usage_from(info.get("last_token_usage")) or usage_last
                    candidate = info.get("model_context_window")
                    if isinstance(candidate, int):
                        context_window = candidate
                limits = payload.get("rate_limits")
                event_time = _parse_iso(record.get("timestamp")) or captured_at
                candidate_quota = _quota_from(limits, event_time)
                if candidate_quota is not None:
                    quota = candidate_quota
                if isinstance(limits, dict) and limits.get("rate_limit_reached_type"):
                    reached = True

        data = RolloutData(
            model=model,
            cwd=cwd,
            usage_total=usage_total,
            usage_last=usage_last,
            context_window=context_window,
            quota=quota,
            rate_limit_reached=reached,
        )
        self._cache[key] = (signature[0], signature[1], data)
        if len(self._cache) > CACHE_LIMIT:
            self._cache.pop(next(iter(self._cache)))
        return data

    # -- adapter --------------------------------------------------------

    def sessions(self) -> list[Session]:
        now = self._now()
        cutoff = now.timestamp() - self.max_age_hours * 3600
        prepared: list[tuple[dict, datetime, datetime | None, RolloutData]] = []
        for row in self._thread_rows(cutoff):
            updated_at = _parse_epoch(row.get("updated_at"))
            created_at = _parse_epoch(row.get("created_at"))
            if updated_at is None:
                continue
            rollout_path = row.get("rollout_path")
            rollout = RolloutData()
            if isinstance(rollout_path, str) and rollout_path:
                path = Path(rollout_path)
                if not path.is_absolute():
                    path = self.root / path
                rollout = self._read_rollout(path)
            prepared.append((row, updated_at, created_at, rollout))

        shared_quota = apply_window_rollover(
            select_shared_quota(rollout for _, _, _, rollout in prepared),
            now,
        )

        sessions: list[Session] = []
        for row, updated_at, created_at, rollout in prepared:
            cwd = rollout.cwd or row.get("cwd")
            cwd = normalize_windows_path(cwd) if isinstance(cwd, str) else None
            model = rollout.model or (row.get("model") if isinstance(row.get("model"), str) else None)
            quota = shared_quota
            rate_limited = rollout.rate_limit_reached or bool(
                quota and quota.exhausted
            )
            age = (now - updated_at).total_seconds()
            if rate_limited:
                state = SessionState.RATE_LIMITED
            elif age <= self.running_window_seconds:
                state = SessionState.RUNNING
            else:
                state = SessionState.IDLE

            usage_total = rollout.usage_total
            if usage_total is None:
                reported = row.get("tokens_used")
                if isinstance(reported, (int, float)):
                    usage_total = Usage(reported_total=int(reported))
            usage_last = rollout.usage_last or Usage()

            sessions.append(
                Session(
                    id=str(row.get("id")),
                    agent=self.name,
                    model=model or "unknown",
                    project=_project_name(cwd),
                    state=state,
                    usage_total=usage_total or Usage(),
                    usage_last=usage_last,
                    context_window=rollout.context_window,
                    context_used=usage_last.total if usage_last.total else None,
                    quota=quota,
                    started_at=created_at,
                    updated_at=updated_at,
                    cwd=cwd,
                    source=str(row.get("source") or ""),
                )
            )
        return sessions

    def probe(self) -> str:
        db = self._find_state_db()
        if db is None:
            return "state database not found"
        return f"threads db: {db.name}"
