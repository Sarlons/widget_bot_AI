"""Session registry: collects adapters, attaches processes, orders results."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable, Iterable

from ..processes import AgentProcess, scan_processes
from .models import Session, SessionState, Snapshot
from ..sources.base import SourceAdapter

STATE_ORDER = {
    SessionState.RUNNING: 0,
    SessionState.RATE_LIMITED: 1,
    SessionState.WAITING: 2,
    SessionState.IDLE: 3,
    SessionState.ERROR: 4,
}


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    text = value
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.normpath(text))


class Registry:
    def __init__(
        self,
        adapters: Iterable[SourceAdapter],
        process_scanner: Callable[[], list[AgentProcess]] = scan_processes,
    ) -> None:
        self.adapters = list(adapters)
        self._scan = process_scanner

    def refresh(self) -> Snapshot:
        errors: list[str] = []
        sessions: list[Session] = []

        for adapter in self.adapters:
            try:
                sessions.extend(adapter.sessions())
            except Exception as exc:  # one adapter must not break the widget
                errors.append(f"{adapter.display_name}: {type(exc).__name__}")

        try:
            processes = self._scan()
        except Exception as exc:
            processes = []
            errors.append(f"Process scan: {type(exc).__name__}")

        self._attach_processes(sessions, processes)
        sessions = self._dedupe(sessions)

        sessions.sort(
            key=lambda session: (
                STATE_ORDER.get(session.state, 9),
                -(session.updated_at.timestamp() if session.updated_at else 0),
            )
        )
        return Snapshot(
            sessions=tuple(sessions),
            generated_at=datetime.now(timezone.utc),
            errors=tuple(errors),
        )

    def _attach_processes(
        self, sessions: list[Session], processes: list[AgentProcess]
    ) -> None:
        by_location: dict[tuple[str, str], list[Session]] = {}
        for session in sessions:
            key = (session.agent, _normalize(session.cwd) or "")
            if key[1]:
                by_location.setdefault(key, []).append(session)

        matched: set[int] = set()
        for process in processes:
            key = (process.agent, _normalize(process.cwd) or "")
            candidates = by_location.get(key)
            if not candidates:
                continue
            # Several threads can share one workspace. Attach the process to the
            # most recently updated one; the others stay idle.
            session = max(
                candidates,
                key=lambda item: item.updated_at.timestamp() if item.updated_at else 0,
            )
            if session.pid is None:
                session.pid = process.pid
                matched.add(process.pid)
            # Process presence alone is not proof that the model is generating:
            # an open Claude Code or OpenCode process can sit idle. Activity
            # timestamps and turn state from the adapter remain authoritative.

        # Some agents (Codex MSIX, Codex/OpenCode services) run with their
        # install directory as cwd, so workspace matching cannot work. Fall back
        # to the most recent running session per agent. This only labels a PID;
        # it never turns an idle session into a running one.
        for process in processes:
            if process.pid in matched:
                continue
            candidates = [
                session
                for session in sessions
                if session.agent == process.agent
                and session.pid is None
                and session.state is SessionState.RUNNING
            ]
            if not candidates:
                continue
            session = max(
                candidates,
                key=lambda item: item.updated_at.timestamp() if item.updated_at else 0,
            )
            session.pid = process.pid
            matched.add(process.pid)

    @staticmethod
    def _dedupe(sessions: list[Session]) -> list[Session]:
        unique: dict[tuple[str, str], Session] = {}
        for session in sessions:
            unique[(session.agent, session.id)] = session
        return list(unique.values())

    def close(self) -> None:
        for adapter in self.adapters:
            try:
                adapter.close()
            except Exception:
                pass
