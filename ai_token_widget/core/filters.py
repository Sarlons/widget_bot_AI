"""Session filtering rules shared by the widget and its tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .agents import agent_label
from .models import Session, SessionState

ATTENTION_CONTEXT_PERCENT = 10.0


class FilterMode(str, Enum):
    ALL = "all"
    RUNNING = "running"
    ATTENTION = "attention"


def needs_attention(
    session: Session,
    low_quota_percent: int = 20,
    context_percent: float = ATTENTION_CONTEXT_PERCENT,
) -> bool:
    """Whether a session deserves a second look.

    This intentionally mirrors the conditions the tray notifies about, plus a
    nearly-full context window. It is only used when the user selects the
    ``Issues`` filter; it never changes the provider running state.
    """

    if session.state in (SessionState.RATE_LIMITED, SessionState.ERROR):
        return True
    if session.quota is not None:
        if any(
            window.remaining_percent <= low_quota_percent
            for window in session.quota.windows
        ):
            return True
    remaining = session.context_remaining_percent
    return remaining is not None and remaining <= context_percent


@dataclass(frozen=True)
class SessionFilter:
    mode: FilterMode = FilterMode.ALL
    query: str = ""

    def matches(self, session: Session, low_quota_percent: int = 20) -> bool:
        if self.mode is FilterMode.RUNNING:
            if session.state is not SessionState.RUNNING:
                return False
        elif self.mode is FilterMode.ATTENTION:
            if not needs_attention(session, low_quota_percent):
                return False

        terms = self.query.casefold().split()
        if not terms:
            return True
        haystack = " ".join(
            (session.project, session.model, agent_label(session.agent))
        ).casefold()
        return all(term in haystack for term in terms)


def filter_sessions(
    sessions: Iterable[Session],
    session_filter: SessionFilter,
    low_quota_percent: int = 20,
) -> tuple[Session, ...]:
    return tuple(
        session
        for session in sessions
        if session_filter.matches(session, low_quota_percent)
    )


__all__ = [
    "ATTENTION_CONTEXT_PERCENT",
    "FilterMode",
    "SessionFilter",
    "filter_sessions",
    "needs_attention",
]
