from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_token_widget.core.models import Quota, QuotaWindow, Session, SessionState
from ai_token_widget.core.registry import Registry
from ai_token_widget.processes import AgentProcess
from ai_token_widget.sources.base import SourceAdapter

NOW = datetime.now(timezone.utc)


def _session(**overrides) -> Session:
    values = dict(
        id="s1",
        agent="codex",
        model="gpt-test",
        project="alpha",
        state=SessionState.IDLE,
        cwd="C:\\work\\alpha",
        updated_at=NOW - timedelta(minutes=10),
    )
    values.update(overrides)
    return Session(**values)


class FakeAdapter(SourceAdapter):
    name = "codex"
    display_name = "Codex"

    def __init__(self, sessions: list[Session], error: Exception | None = None) -> None:
        self._sessions = sessions
        self._error = error

    def sessions(self) -> list[Session]:
        if self._error:
            raise self._error
        return self._sessions


class RegistryTest(unittest.TestCase):
    def test_process_is_attached_without_changing_activity_state(self) -> None:
        registry = Registry(
            [FakeAdapter([_session()])],
            process_scanner=lambda: [
                AgentProcess(pid=42, agent="codex", cwd="c:\\WORK\\alpha")
            ],
        )
        snapshot = registry.refresh()
        self.assertEqual(snapshot.sessions[0].pid, 42)
        self.assertEqual(snapshot.sessions[0].state, SessionState.IDLE)

    def test_process_does_not_override_rate_limit(self) -> None:
        quota = Quota(
            confidence="exact",
            windows=(QuotaWindow(label="5h", used_percent=100.0),),
        )
        registry = Registry(
            [FakeAdapter([_session(state=SessionState.RATE_LIMITED, quota=quota)])],
            process_scanner=lambda: [
                AgentProcess(pid=42, agent="codex", cwd="C:\\work\\alpha")
            ],
        )
        session = registry.refresh().sessions[0]
        self.assertEqual(session.state, SessionState.RATE_LIMITED)

    def test_wrong_workspace_is_not_attached(self) -> None:
        registry = Registry(
            [FakeAdapter([_session()])],
            process_scanner=lambda: [
                AgentProcess(pid=42, agent="codex", cwd="C:\\work\\beta")
            ],
        )
        self.assertIsNone(registry.refresh().sessions[0].pid)

    def test_unmatched_process_attaches_only_to_running_session(self) -> None:
        registry = Registry(
            [
                FakeAdapter(
                    [
                        _session(id="run", state=SessionState.RUNNING),
                        _session(id="idle", state=SessionState.IDLE),
                    ]
                )
            ],
            process_scanner=lambda: [
                AgentProcess(pid=7, agent="codex", cwd="C:\\Program Files\\Codex")
            ],
        )
        sessions = {session.id: session for session in registry.refresh().sessions}
        self.assertEqual(sessions["run"].pid, 7)
        self.assertIsNone(sessions["idle"].pid)
        self.assertEqual(sessions["idle"].state, SessionState.IDLE)

    def test_adapter_failure_is_contained(self) -> None:
        class Boom(FakeAdapter):
            def sessions(self):
                raise RuntimeError("boom")

        registry = Registry(
            [FakeAdapter([_session()]), Boom([])],
            process_scanner=lambda: [],
        )
        snapshot = registry.refresh()
        self.assertEqual(len(snapshot.sessions), 1)
        self.assertEqual(snapshot.errors, ("Codex: RuntimeError",))

    def test_duplicate_sessions_are_collapsed(self) -> None:
        registry = Registry(
            [FakeAdapter([_session(), _session(model="newer")])],
            process_scanner=lambda: [],
        )
        self.assertEqual(len(registry.refresh().sessions), 1)

    def test_running_sessions_sort_first(self) -> None:
        registry = Registry(
            [
                FakeAdapter(
                    [
                        _session(id="idle", state=SessionState.IDLE),
                        _session(id="run", state=SessionState.RUNNING),
                    ]
                )
            ],
            process_scanner=lambda: [],
        )
        self.assertEqual(registry.refresh().sessions[0].id, "run")


if __name__ == "__main__":
    unittest.main()
