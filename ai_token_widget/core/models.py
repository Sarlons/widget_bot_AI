"""Shared data model for the widget.

All timestamps are timezone-aware UTC unless stated otherwise. The UI is the
only layer allowed to convert them to local time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SessionState(str, Enum):
    RUNNING = "running"
    WAITING = "waiting"
    RATE_LIMITED = "rate_limited"
    IDLE = "idle"
    ERROR = "error"


class Confidence(str, Enum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    reported_total: int | None = None
    # Some providers report input tokens that already include cache reads.
    # Keep the raw counter here so the display does not add the cache twice.
    billed_input_tokens: int | None = None

    @property
    def total(self) -> int:
        if self.reported_total is not None:
            return self.reported_total
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.reasoning_tokens
        )

    @property
    def billed_input(self) -> int:
        if self.billed_input_tokens is not None:
            return self.billed_input_tokens
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    def __add__(self, other: "Usage") -> "Usage":
        if not isinstance(other, Usage):
            return NotImplemented
        reported = None
        if self.reported_total is not None and other.reported_total is not None:
            reported = self.reported_total + other.reported_total
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            reported_total=reported,
            billed_input_tokens=self.billed_input + other.billed_input,
        )


@dataclass(frozen=True)
class QuotaWindow:
    label: str
    used_percent: float
    window_minutes: int | None = None
    resets_at: datetime | None = None

    @property
    def remaining_percent(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))

    @property
    def exhausted(self) -> bool:
        return self.used_percent >= 100.0


@dataclass(frozen=True)
class Quota:
    confidence: Confidence
    windows: tuple[QuotaWindow, ...] = ()
    plan: str | None = None
    credits_usd: float | None = None
    source: str = ""
    captured_at: datetime | None = None

    @property
    def exhausted(self) -> bool:
        return any(window.exhausted for window in self.windows)


@dataclass
class Session:
    id: str
    agent: str
    model: str
    project: str
    state: SessionState
    usage_total: Usage = field(default_factory=Usage)
    usage_last: Usage = field(default_factory=Usage)
    context_window: int | None = None
    context_used: int | None = None
    context_estimated: bool = False
    cost_usd: float | None = None
    quota: Quota | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    cwd: str | None = None
    pid: int | None = None
    source: str = ""

    @property
    def context_used_percent(self) -> float | None:
        if not self.context_window or self.context_used is None:
            return None
        return max(0.0, min(100.0, 100.0 * self.context_used / self.context_window))

    @property
    def context_remaining_percent(self) -> float | None:
        used = self.context_used_percent
        return None if used is None else 100.0 - used

    @property
    def context_remaining(self) -> int | None:
        if self.context_window is None or self.context_used is None:
            return None
        return max(0, self.context_window - self.context_used)

    @property
    def age_seconds(self) -> float | None:
        if self.updated_at is None:
            return None
        base = self.updated_at
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - base).total_seconds())


@dataclass(frozen=True)
class Snapshot:
    sessions: tuple[Session, ...] = ()
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    errors: tuple[str, ...] = ()

    @property
    def running_count(self) -> int:
        return sum(1 for session in self.sessions if session.state is SessionState.RUNNING)

    @property
    def rate_limited_count(self) -> int:
        return sum(
            1 for session in self.sessions if session.state is SessionState.RATE_LIMITED
        )
