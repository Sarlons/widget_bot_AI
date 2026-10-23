"""Group sessions by provider while preserving registry ordering."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .agents import AGENT_ORDER, agent_label
from .models import Session, SessionState


@dataclass(frozen=True)
class SessionGroup:
    agent: str
    label: str
    sessions: tuple[Session, ...]

    @property
    def running_count(self) -> int:
        return sum(
            1 for session in self.sessions if session.state is SessionState.RUNNING
        )

    @property
    def issue_count(self) -> int:
        return sum(
            1
            for session in self.sessions
            if session.state in (SessionState.RATE_LIMITED, SessionState.ERROR)
        )


def group_sessions(sessions: Iterable[Session]) -> tuple[SessionGroup, ...]:
    buckets: dict[str, list[Session]] = {}
    for session in sessions:
        buckets.setdefault(session.agent, []).append(session)

    known = [agent for agent in AGENT_ORDER if agent in buckets]
    unknown = sorted(agent for agent in buckets if agent not in AGENT_ORDER)
    return tuple(
        SessionGroup(
            agent=agent,
            label=agent_label(agent),
            sessions=tuple(buckets[agent]),
        )
        for agent in (*known, *unknown)
    )


__all__ = ["SessionGroup", "group_sessions"]
