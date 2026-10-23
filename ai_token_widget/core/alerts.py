"""Tray alerts derived from snapshots, with transition tracking.

Alerts are intentionally coarse: they describe quota windows, session states
and adapter errors, never prompts or transcript content. The tracker keeps only
the keys of the conditions that were active on the previous poll, so a stable
problem produces one notification instead of one every few seconds.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .agents import agent_label
from .formatting import format_reset
from .models import Confidence, SessionState, Snapshot


@dataclass(frozen=True)
class Alert:
    key: str
    title: str
    message: str


def _reset_key(moment: datetime | None) -> str:
    return moment.isoformat() if moment is not None else ""


def _quota_alerts(
    snapshot: Snapshot, low_percent: int, muted_agents: set[str]
) -> tuple[dict[str, Alert], set[str]]:
    """Collapse per-session copies of the same provider window.

    Several sessions can share one account quota. Keep the most constrained
    copy of each ``(agent, window label)`` pair so a shared window produces one
    notification.
    """

    candidates: dict[tuple[str, str], tuple] = {}
    for session in snapshot.sessions:
        if session.agent in muted_agents:
            continue
        quota = session.quota
        if quota is None or quota.confidence == Confidence.UNAVAILABLE:
            continue
        for window in quota.windows:
            key = (session.agent, window.label)
            previous = candidates.get(key)
            if previous is None or window.remaining_percent < previous[0]:
                candidates[key] = (
                    window.remaining_percent,
                    window.resets_at,
                    quota.plan,
                    quota.confidence,
                )

    alerts: dict[str, Alert] = {}
    exhausted_agents: set[str] = set()
    for (agent, label), (remaining, resets_at, plan, confidence) in candidates.items():
        agent_name = agent_label(agent)
        reset = format_reset(resets_at) if resets_at else None
        estimate = " · estimated" if confidence == Confidence.ESTIMATED else ""
        if remaining <= 0:
            exhausted_agents.add(agent)
            key = f"quota-exhausted:{agent}:{label}:{_reset_key(resets_at)}"
            message = f"{label} quota exhausted"
            if reset:
                message += f" · resets {reset}"
            if plan:
                message += f" · {plan}"
            message += estimate
            alerts[key] = Alert(key, f"{agent_name} quota exhausted", message)
        elif remaining <= low_percent:
            key = f"quota-low:{agent}:{label}"
            message = f"{label} quota at {remaining:.0f}% remaining"
            if reset:
                message += f" · resets {reset}"
            message += estimate
            alerts[key] = Alert(key, f"{agent_name} quota low", message)
    return alerts, exhausted_agents


def _state_alerts(
    snapshot: Snapshot, exhausted_agents: set[str], muted_agents: set[str]
) -> dict[str, Alert]:
    alerts: dict[str, Alert] = {}
    for session in snapshot.sessions:
        if session.agent in muted_agents:
            continue
        if session.state is SessionState.RATE_LIMITED:
            if session.agent in exhausted_agents:
                # The exhausted quota alert already explains this state.
                continue
            key = f"state:{session.agent}:{session.id}:rate_limited"
            alerts[key] = Alert(
                key,
                f"{agent_label(session.agent)} rate limited",
                f"{session.project} · {session.model}",
            )
        elif session.state is SessionState.ERROR:
            key = f"state:{session.agent}:{session.id}:error"
            alerts[key] = Alert(
                key,
                f"{agent_label(session.agent)} session error",
                f"{session.project} · {session.model}",
            )
    return alerts


def _error_alerts(snapshot: Snapshot) -> dict[str, Alert]:
    alerts: dict[str, Alert] = {}
    for error in snapshot.errors:
        key = f"adapter-error:{error}"
        alerts[key] = Alert(key, "Adapter error", error)
    return alerts


class AlertTracker:
    """Return only alerts whose condition was not active on the previous poll."""

    def __init__(
        self,
        low_quota_percent: int = 20,
        muted_agents: Iterable[str] | None = None,
    ) -> None:
        self.low_quota_percent = max(1, min(50, int(low_quota_percent)))
        self.muted_agents: set[str] = set()
        self.set_muted_agents(muted_agents)
        self._active: set[str] = set()
        self._seeded = False

    def set_muted_agents(self, agents: Iterable[str] | None) -> None:
        self.muted_agents = {
            agent for agent in (agents or ()) if isinstance(agent, str) and agent
        }

    def update(self, snapshot: Snapshot, notify: bool = True) -> list[Alert]:
        current, exhausted_agents = _quota_alerts(
            snapshot, self.low_quota_percent, self.muted_agents
        )
        # Adapter errors come before per-session state so a burst of
        # rate-limited cards cannot hide a broken data source.
        current.update(_error_alerts(snapshot))
        current.update(
            _state_alerts(snapshot, exhausted_agents, self.muted_agents)
        )

        if not self._seeded:
            # Never notify for conditions that already existed at startup.
            self._active = set(current)
            self._seeded = True
            return []

        raised = [
            alert for key, alert in current.items() if key not in self._active
        ]
        self._active = set(current)
        return raised if notify else []

    def reset(self) -> None:
        self._active.clear()
        self._seeded = False


__all__ = ["Alert", "AlertTracker"]
