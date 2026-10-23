"""Sanitized runtime diagnostics for support and troubleshooting.

The report must stay safe to paste into an issue: it contains counts, timing,
configuration values and adapter error labels, but never prompts, transcript
text, session ids, project paths or credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .agents import AGENT_ORDER, agent_label
from .config import Config
from .formatting import format_age
from .models import SessionState, Snapshot


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def build_diagnostics(
    *,
    version: str,
    config: Config,
    snapshot: Snapshot,
    last_snapshot_at: datetime | None,
    refresh_busy: bool,
    refresh_seconds: float | None = None,
    refresh_error: str | None = None,
    history_count: int | None = None,
    now: datetime | None = None,
) -> str:
    """Return a compact, sanitized report of the widget's current state."""
    moment = _aware(now) or datetime.now(timezone.utc)
    snapshot_at = _aware(last_snapshot_at)

    if snapshot_at is None:
        snapshot_line = "Snapshot: none"
        age_line = "Snapshot age: none"
    else:
        snapshot_line = f"Snapshot: {snapshot_at.isoformat(timespec='seconds')}"
        age_line = f"Snapshot age: {format_age((moment - snapshot_at).total_seconds())}"

    if refresh_busy:
        if refresh_seconds is None:
            refresh_line = "Refresh: running"
        else:
            refresh_line = f"Refresh: running for {refresh_seconds:.0f}s"
    else:
        refresh_line = "Refresh: idle"

    lines = [
        f"AI Token Widget {version}",
        f"Generated: {moment.isoformat(timespec='seconds')}",
        snapshot_line,
        age_line,
        refresh_line,
        f"Last refresh error: {refresh_error or 'none'}",
        (
            f"Sessions: {len(snapshot.sessions)} total · "
            f"{snapshot.running_count} running · "
            f"{snapshot.rate_limited_count} limited"
        ),
    ]

    agents = list(AGENT_ORDER)
    agents.extend(
        sorted(
            {
                session.agent
                for session in snapshot.sessions
                if session.agent not in agents
            }
        )
    )
    lines.append("Providers:")
    for agent in agents:
        sessions = [
            session for session in snapshot.sessions if session.agent == agent
        ]
        running = sum(
            1 for session in sessions if session.state is SessionState.RUNNING
        )
        lines.append(
            f"  {agent_label(agent)}: {len(sessions)} sessions, {running} running"
        )

    muted = ", ".join(config.muted_agents) or "none"
    lines.extend(
        [
            (
                "Settings: "
                f"poll={config.poll_seconds}s, "
                f"low_quota={config.low_quota_percent}%, "
                f"notifications={'on' if config.notifications_enabled else 'off'}, "
                f"sound={'on' if config.notification_sound else 'off'}, "
                f"muted={muted}"
            ),
            (
                "Window: "
                f"{config.window_width}x{config.window_height}, "
                f"opacity={config.opacity:.2f}, "
                f"always_on_top={config.always_on_top}"
            ),
            (
                "Age windows: "
                f"sessions={config.max_session_age_hours:g}h, "
                f"running={config.running_window_seconds}s"
            ),
        ]
    )
    if history_count is not None:
        lines.append(f"Notification history: {history_count} saved alerts")
    lines.append("Adapter errors:")
    if snapshot.errors:
        lines.extend(f"  - {error}" for error in snapshot.errors)
    else:
        lines.append("  none")
    lines.append("Log: %APPDATA%\\AITokenWidget\\widget.log")
    return "\n".join(lines)


__all__ = ["build_diagnostics"]
