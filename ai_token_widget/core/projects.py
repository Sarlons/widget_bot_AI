"""Project aggregation, modified-file sizing and management-load summaries.

The widget only counts files that an agent actually wrote or edited through a
tool call. Folder scans, reads, searches and build artifacts are never included.
File contents are never opened: sizing uses ``os.stat`` on the deduplicated
paths reported by the adapters.
"""

from __future__ import annotations

import os
import stat as stat_module
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from .agents import AGENT_ORDER, agent_label
from .load import compute_load_score, load_index, load_label, model_weight
from .models import Session, SessionState

PROJECT_LIMIT = 6
UNKNOWN_KEY_PREFIX = "unknown:"

SizeResolver = Callable[[str], int | None]


@dataclass(frozen=True)
class ProjectSummary:
    key: str
    name: str
    cwd: str | None
    sessions: tuple[Session, ...]
    token_total: int
    prompt_count: int
    prompt_chars: int
    assistant_count: int
    modified_paths: tuple[str, ...]
    modified_files: int
    modified_bytes: int
    missing_files: int
    context_pressure: float
    model_factor: float
    load_score: float
    load_index: int
    load_label: str

    @property
    def session_count(self) -> int:
        return len(self.sessions)

    @property
    def average_prompt_chars(self) -> float | None:
        if self.prompt_count <= 0:
            return None
        return self.prompt_chars / self.prompt_count

    @property
    def running_count(self) -> int:
        return sum(
            1 for session in self.sessions if session.state is SessionState.RUNNING
        )

    @property
    def agent_names(self) -> tuple[str, ...]:
        present = {session.agent for session in self.sessions}
        known = [agent for agent in AGENT_ORDER if agent in present]
        unknown = sorted(present - set(known))
        return tuple((*known, *unknown))

    @property
    def agent_labels(self) -> tuple[str, ...]:
        return tuple(agent_label(agent) for agent in self.agent_names)

    @property
    def latest_activity(self) -> datetime | None:
        moments = [
            session.updated_at
            for session in self.sessions
            if session.updated_at is not None
        ]
        return max(moments) if moments else None


def _normalize_key(value: str) -> str:
    text = value
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.normpath(text))


def _clean_path(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().strip('"')
    if not text:
        return None
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normpath(text)


def _project_name(cwd: str | None, fallback: str) -> str:
    if not cwd:
        return fallback or "unknown"
    cleaned = cwd.rstrip("\\/")
    return os.path.basename(cleaned) or cleaned or fallback or "unknown"


def _resolve_path(path: str, cwd: str | None) -> str | None:
    cleaned = _clean_path(path)
    if not cleaned:
        return None
    if os.path.isabs(cleaned):
        return cleaned
    if not cwd:
        # A relative path without a known working directory cannot be sized
        # safely: resolving it against the widget process would be misleading.
        return None
    return os.path.normpath(os.path.join(cwd, cleaned))


def _stat_size(path: str) -> int | None:
    try:
        info = os.stat(path)
    except OSError:
        return None
    if not stat_module.S_ISREG(info.st_mode):
        return None
    return max(0, int(info.st_size))


def _context_pressure(sessions: Iterable[Session]) -> float:
    values = [
        session.context_used_percent / 100.0
        for session in sessions
        if session.context_used_percent is not None
    ]
    if not values:
        return 0.0
    return max(0.0, min(1.0, sum(values) / len(values)))


def _sort_key(project: ProjectSummary):
    activity = project.latest_activity
    timestamp = activity.timestamp() if activity is not None else 0.0
    return (-project.token_total, -timestamp, project.name.lower())


def aggregate_projects(
    sessions: Iterable[Session],
    *,
    limit: int = PROJECT_LIMIT,
    size_resolver: SizeResolver | None = None,
) -> tuple[ProjectSummary, ...]:
    """Group sessions by normalized working directory.

    ``size_resolver`` is injectable for tests. By default each unique path is
    measured once with :func:`os.stat`; unreadable or deleted files are counted
    as missing but do not contribute bytes.
    """
    buckets: dict[str, list[Session]] = {}
    cwd_by_key: dict[str, str | None] = {}
    fallback_by_key: dict[str, str] = {}

    for session in sessions:
        cwd = _clean_path(session.cwd)
        if cwd:
            key = _normalize_key(cwd)
        else:
            fallback = session.project or "unknown"
            key = f"{UNKNOWN_KEY_PREFIX}{fallback}"
        buckets.setdefault(key, []).append(session)
        cwd_by_key.setdefault(key, cwd)
        fallback_by_key.setdefault(key, session.project or "unknown")

    resolver = size_resolver or _stat_size
    summaries: list[ProjectSummary] = []
    for key, members in buckets.items():
        cwd = cwd_by_key.get(key)
        fallback = fallback_by_key.get(key, "unknown")
        name = _project_name(cwd, fallback)

        resolved: dict[str, str] = {}
        for session in members:
            for raw_path in session.modified_paths:
                cleaned = _clean_path(raw_path)
                if not cleaned:
                    continue
                absolute = _resolve_path(cleaned, session.cwd)
                display = absolute or cleaned
                dedupe_key = _normalize_key(absolute) if absolute else _normalize_key(cleaned)
                resolved.setdefault(dedupe_key, display)

        modified_bytes = 0
        missing = 0
        for path in resolved.values():
            try:
                size = resolver(path)
            except Exception:
                size = None
            if size is None:
                missing += 1
            else:
                modified_bytes += max(0, int(size))

        token_total = sum(session.usage_total.total for session in members)
        prompt_count = sum(max(0, session.prompt_count) for session in members)
        prompt_chars = sum(max(0, session.prompt_chars) for session in members)
        assistant_count = sum(max(0, session.assistant_count) for session in members)
        pressure = _context_pressure(members)
        model_factor = max(
            (model_weight(session.model_kind) for session in members),
            default=model_weight(None),
        )
        score = compute_load_score(
            prompt_count=prompt_count,
            assistant_count=assistant_count,
            context_pressure=pressure,
            model_factor=model_factor,
            prompt_chars=prompt_chars,
        )
        index = load_index(score)
        summaries.append(
            ProjectSummary(
                key=key,
                name=name,
                cwd=cwd,
                sessions=tuple(members),
                token_total=token_total,
                prompt_count=prompt_count,
                prompt_chars=prompt_chars,
                assistant_count=assistant_count,
                modified_paths=tuple(sorted(resolved.values(), key=os.path.normcase)),
                modified_files=len(resolved),
                modified_bytes=modified_bytes,
                missing_files=missing,
                context_pressure=pressure,
                model_factor=model_factor,
                load_score=score,
                load_index=index,
                load_label=load_label(index),
            )
        )

    summaries.sort(key=_sort_key)
    return tuple(summaries[: max(1, limit)])


__all__ = [
    "PROJECT_LIMIT",
    "ProjectSummary",
    "aggregate_projects",
]
