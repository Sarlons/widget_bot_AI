"""Claude Code adapter.

Claude Code writes one JSONL transcript per session under
``~/.claude/projects/<encoded-cwd>/<session>.jsonl``. Each assistant message
carries ``message.usage`` with exact input/output/cache token counts. The
transcripts do not contain account rate limits, so quota comes from the opt-in
status-line bridge (``claude_statusline.py``) when it is installed.

Files are parsed once and cached by ``(mtime, size)``. No message content is
retained: only usage numbers, model id, cwd and timestamps.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import claude_statusline
from ..core.model_limits import claude_context_window
from ..core.models import Confidence, Quota, QuotaWindow, Session, SessionState, Usage
from .base import SourceAdapter

DEFAULT_ROOT = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
CACHE_LIMIT = 64
SNAPSHOT_MAX_AGE_HOURS = 24.0


@dataclass(frozen=True)
class ClaudeFileData:
    session_id: str
    cwd: str | None = None
    model: str | None = None
    version: str | None = None
    usage_total: Usage = Usage()
    usage_last: Usage = Usage()
    started_at: datetime | None = None
    last_activity: datetime | None = None
    last_role: str | None = None
    last_role_at: datetime | None = None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_path(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().strip('"')
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normpath(text)


def _usage_from(raw: dict) -> Usage:
    return Usage(
        input_tokens=int(raw.get("input_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
        cache_read_tokens=int(raw.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(raw.get("cache_creation_input_tokens") or 0),
    )


def _quota_from_snapshot(
    snapshot: dict | None, now: datetime
) -> Quota | None:
    if not isinstance(snapshot, dict):
        return None
    captured_at = parse_iso(snapshot.get("captured_at"))
    if captured_at is None:
        return None
    if (now - captured_at).total_seconds() > SNAPSHOT_MAX_AGE_HOURS * 3600:
        return None

    windows: list[QuotaWindow] = []
    raw_windows = snapshot.get("windows")
    if not isinstance(raw_windows, list):
        return None
    for raw in raw_windows:
        if not isinstance(raw, dict):
            continue
        try:
            used = float(raw.get("used_percent"))
        except (TypeError, ValueError):
            continue
        resets = parse_iso(raw.get("resets_at"))
        if resets is not None and resets <= now:
            used = 0.0
            resets = None
        label = raw.get("label")
        windows.append(
            QuotaWindow(
                label=str(label) if label else "quota",
                used_percent=max(0.0, min(100.0, used)),
                resets_at=resets,
            )
        )
    if not windows:
        return None
    return Quota(
        confidence=Confidence.EXACT,
        windows=tuple(windows),
        source="claude-statusline",
        captured_at=captured_at,
    )


class ClaudeAdapter(SourceAdapter):
    name = "claude_code"
    display_name = "Claude Code"

    def __init__(
        self,
        root: Path | str | None = None,
        max_age_hours: float = 24.0,
        limit: int = 12,
        running_window_seconds: float = 90.0,
        now: Callable[[], datetime] | None = None,
        data_dir: Path | str | None = None,
    ) -> None:
        self.root = Path(root) if root else DEFAULT_ROOT
        self.projects_dir = self.root / "projects"
        self.max_age_hours = max_age_hours
        self.limit = limit
        self.running_window_seconds = running_window_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._data_dir = Path(data_dir) if data_dir else None
        self._cache: dict[str, tuple[int, int, ClaudeFileData]] = {}

    # -- parsing --------------------------------------------------------

    def _transcript_paths(self, cutoff: float) -> list[Path]:
        if not self.projects_dir.exists():
            return []
        entries: list[tuple[float, Path]] = []
        for path in self.projects_dir.rglob("*.jsonl"):
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified >= cutoff:
                entries.append((modified, path))
        entries.sort(key=lambda item: item[0], reverse=True)
        return [path for _, path in entries[: max(self.limit * 4, 32)]]

    def _parse_file(self, path: Path) -> ClaudeFileData:
        try:
            stat = path.stat()
        except OSError:
            return ClaudeFileData(session_id=path.stem)
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(str(path))
        if cached and cached[:2] == signature:
            return cached[2]

        session_id = path.stem
        cwd = None
        model = None
        version = None
        unkeyed_usage = Usage()
        usage_by_id: dict[str, Usage] = {}
        usage_last = Usage()
        started_at = None
        last_activity = None
        last_role = None
        last_role_at = None

        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue

                    timestamp = parse_iso(record.get("timestamp"))
                    if timestamp is not None:
                        if started_at is None or timestamp < started_at:
                            started_at = timestamp
                        if last_activity is None or timestamp > last_activity:
                            last_activity = timestamp

                    candidate_id = record.get("sessionId")
                    if isinstance(candidate_id, str) and candidate_id:
                        session_id = candidate_id
                    candidate_cwd = record.get("cwd")
                    if isinstance(candidate_cwd, str) and candidate_cwd:
                        cwd = candidate_cwd
                    candidate_version = record.get("version")
                    if isinstance(candidate_version, str):
                        version = candidate_version

                    record_type = record.get("type")
                    message = record.get("message")
                    if not isinstance(message, dict):
                        continue

                    role = message.get("role")
                    if role not in ("user", "assistant"):
                        role = record_type if record_type in ("user", "assistant") else None
                    if role is not None and timestamp is not None:
                        if last_role_at is None or timestamp >= last_role_at:
                            last_role = role
                            last_role_at = timestamp

                    usage = message.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    candidate_model = message.get("model")
                    if isinstance(candidate_model, str) and candidate_model != "<synthetic>":
                        model = candidate_model
                    if candidate_model == "<synthetic>":
                        continue

                    parsed_usage = _usage_from(usage)
                    message_id = message.get("id")
                    if isinstance(message_id, str) and message_id:
                        # Claude Code can write one record per content block
                        # with the same message id and the same usage. Count
                        # each API response once, keeping its latest values.
                        usage_by_id[message_id] = parsed_usage
                    else:
                        unkeyed_usage = unkeyed_usage + parsed_usage
                    if not record.get("isSidechain"):
                        usage_last = parsed_usage

        except OSError:
            pass

        if last_activity is None:
            last_activity = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        usage_total = unkeyed_usage
        for unique_usage in usage_by_id.values():
            usage_total = usage_total + unique_usage
        data = ClaudeFileData(
            session_id=session_id,
            cwd=cwd,
            model=model,
            version=version,
            usage_total=usage_total,
            usage_last=usage_last,
            started_at=started_at,
            last_activity=last_activity,
            last_role=last_role,
            last_role_at=last_role_at,
        )
        self._cache[str(path)] = (signature[0], signature[1], data)
        if len(self._cache) > CACHE_LIMIT:
            self._cache.pop(next(iter(self._cache)))
        return data

    def _load_quota(self, now: datetime) -> Quota | None:
        path = (
            self._data_dir / claude_statusline.SNAPSHOT_NAME
            if self._data_dir is not None
            else claude_statusline.snapshot_path()
        )
        return _quota_from_snapshot(claude_statusline.read_snapshot(path), now)

    # -- adapter --------------------------------------------------------

    def sessions(self) -> list[Session]:
        now = self._now()
        cutoff = now.timestamp() - self.max_age_hours * 3600
        quota = self._load_quota(now)
        rate_limited = bool(quota and quota.exhausted)

        by_id: dict[str, ClaudeFileData] = {}
        for path in self._transcript_paths(cutoff):
            data = self._parse_file(path)
            if data.last_activity is None or data.last_activity < datetime.fromtimestamp(
                cutoff, timezone.utc
            ):
                continue
            existing = by_id.get(data.session_id)
            if existing is None or (
                data.last_activity
                and existing.last_activity
                and data.last_activity > existing.last_activity
            ):
                by_id[data.session_id] = data

        sessions: list[Session] = []
        for data in sorted(
            by_id.values(),
            key=lambda item: item.last_activity or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[: self.limit]:
            activity = data.last_activity
            if activity is None:
                continue
            age = (now - activity).total_seconds()
            if rate_limited:
                state = SessionState.RATE_LIMITED
            elif age <= self.running_window_seconds:
                state = (
                    SessionState.WAITING
                    if data.last_role == "assistant"
                    else SessionState.RUNNING
                )
            elif data.last_role == "assistant" and age <= 300:
                state = SessionState.WAITING
            else:
                state = SessionState.IDLE

            # Files with only a prompt and no assistant usage yet are useful
            # while fresh, but old empty transcripts are noise.
            if data.usage_total.total == 0 and data.model is None and age > 600:
                continue

            cwd = normalize_path(data.cwd)
            project = Path(cwd).name if cwd else "unknown"
            context_window, estimated = claude_context_window(data.model)
            context_used = data.usage_last.total or None

            sessions.append(
                Session(
                    id=data.session_id,
                    agent=self.name,
                    model=data.model or "unknown",
                    project=project or "unknown",
                    state=state,
                    usage_total=data.usage_total,
                    usage_last=data.usage_last,
                    context_window=context_window,
                    context_used=context_used,
                    context_estimated=estimated,
                    quota=quota,
                    started_at=data.started_at,
                    updated_at=activity,
                    cwd=cwd,
                    source="cli",
                )
            )
        return sessions

    def probe(self) -> str:
        if not self.projects_dir.exists():
            return "projects directory not found"
        return f"{len(list(self.projects_dir.rglob('*.jsonl')))} session logs"
