"""Small formatting helpers shared by the UI and tests."""

from __future__ import annotations

from datetime import datetime, timezone


def format_tokens(value: int | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def format_percent(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}%"


def format_cost(value: float | None) -> str:
    if value is None:
        return "—"
    if 0 < value < 0.01:
        return "<$0.01"
    return f"${value:.2f}"


def format_reset(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone()
    now = datetime.now().astimezone()
    if local.date() == now.date():
        return local.strftime("%H:%M")
    return local.strftime("%a %H:%M")


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"
