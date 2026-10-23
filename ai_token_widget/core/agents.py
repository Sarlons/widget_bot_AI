"""Canonical agent identifiers and display labels."""

from __future__ import annotations

AGENT_ORDER = ("claude_code", "codex", "opencode")

AGENT_LABELS = {
    "claude_code": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
}


def agent_label(agent: str) -> str:
    return AGENT_LABELS.get(agent, agent)


__all__ = ["AGENT_LABELS", "AGENT_ORDER", "agent_label"]
