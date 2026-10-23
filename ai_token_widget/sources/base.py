"""Adapter contract for an agent session source."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.models import Session


class SourceAdapter(ABC):
    """Read-only source of sessions for one agent."""

    name: str
    display_name: str

    @abstractmethod
    def sessions(self) -> list[Session]:
        """Return recent sessions, newest first.

        Implementations must never raise for a missing or malformed store:
        return an empty list instead. Unexpected failures are contained by the
        registry so one broken adapter cannot take down the widget.
        """

    def probe(self) -> str:
        """Short human-readable status used by diagnostics and the UI."""
        return "ok"

    def close(self) -> None:
        """Release any long-lived resources."""
