from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_token_widget.core.alerts import AlertTracker
from ai_token_widget.core.models import (
    Confidence,
    Quota,
    QuotaWindow,
    Session,
    SessionState,
    Snapshot,
)

NOW = datetime.now(timezone.utc)


def _session(
    *,
    agent: str = "claude_code",
    session_id: str = "s1",
    project: str = "alpha",
    state: SessionState = SessionState.IDLE,
    remaining: float | None = None,
    label: str = "5h",
    resets_at: datetime | None = None,
    confidence: Confidence = Confidence.EXACT,
) -> Session:
    quota = None
    if remaining is not None:
        quota = Quota(
            confidence=confidence,
            windows=(
                QuotaWindow(
                    label=label,
                    used_percent=100.0 - remaining,
                    resets_at=resets_at or (NOW + timedelta(hours=1)),
                ),
            ),
        )
    return Session(
        id=session_id,
        agent=agent,
        model="model",
        project=project,
        state=state,
        quota=quota,
        updated_at=NOW,
    )


def _snapshot(*sessions: Session, errors: tuple[str, ...] = ()) -> Snapshot:
    return Snapshot(sessions=tuple(sessions), errors=errors)


class AlertTrackerTest(unittest.TestCase):
    def test_first_snapshot_only_seeds(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        self.assertEqual(tracker.update(_snapshot(_session(remaining=5))), [])
        self.assertEqual(tracker.update(_snapshot(_session(remaining=5))), [])

    def test_low_quota_fires_once_per_crossing(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        tracker.update(_snapshot(_session(remaining=60)))

        raised = tracker.update(_snapshot(_session(remaining=15)))
        self.assertEqual(len(raised), 1)
        self.assertIn("quota low", raised[0].title)
        self.assertIn("15%", raised[0].message)
        self.assertEqual(tracker.update(_snapshot(_session(remaining=14))), [])

        tracker.update(_snapshot(_session(remaining=60)))
        raised = tracker.update(_snapshot(_session(remaining=10)))
        self.assertEqual(len(raised), 1)

    def test_exhausted_supersedes_low(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        tracker.update(_snapshot(_session(remaining=60)))

        raised = tracker.update(_snapshot(_session(remaining=0)))
        self.assertEqual(len(raised), 1)
        self.assertIn("exhausted", raised[0].title)
        self.assertEqual(tracker.update(_snapshot(_session(remaining=0))), [])

    def test_shared_window_produces_one_alert(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        shared = dict(remaining=60)
        tracker.update(
            _snapshot(
                _session(session_id="a", **shared),
                _session(session_id="b", **shared),
            )
        )

        raised = tracker.update(
            _snapshot(
                _session(session_id="a", remaining=10),
                _session(session_id="b", remaining=5),
            )
        )
        self.assertEqual(len(raised), 1)
        self.assertIn("5%", raised[0].message)

    def test_estimated_quota_is_labelled(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        tracker.update(_snapshot(_session(remaining=60)))
        raised = tracker.update(
            _snapshot(
                _session(remaining=10, confidence=Confidence.ESTIMATED)
            )
        )
        self.assertEqual(len(raised), 1)
        self.assertIn("estimated", raised[0].message)

    def test_exhausted_quota_mutes_redundant_rate_limit_alert(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        tracker.update(_snapshot(_session(state=SessionState.WAITING, remaining=60)))

        raised = tracker.update(
            _snapshot(_session(state=SessionState.RATE_LIMITED, remaining=0))
        )
        self.assertEqual(len(raised), 1)
        self.assertIn("quota exhausted", raised[0].title)

    def test_rate_limited_state(self) -> None:
        tracker = AlertTracker()
        tracker.update(_snapshot(_session(state=SessionState.WAITING)))

        raised = tracker.update(_snapshot(_session(state=SessionState.RATE_LIMITED)))
        self.assertEqual(len(raised), 1)
        self.assertIn("rate limited", raised[0].title)
        self.assertEqual(
            tracker.update(_snapshot(_session(state=SessionState.RATE_LIMITED))),
            [],
        )

        tracker.update(_snapshot(_session(state=SessionState.WAITING)))
        raised = tracker.update(_snapshot(_session(state=SessionState.RATE_LIMITED)))
        self.assertEqual(len(raised), 1)

    def test_adapter_errors_are_deduplicated(self) -> None:
        tracker = AlertTracker()
        tracker.update(_snapshot(errors=()))

        raised = tracker.update(_snapshot(errors=("Codex: RuntimeError",)))
        self.assertEqual(len(raised), 1)
        self.assertEqual(raised[0].message, "Codex: RuntimeError")
        self.assertEqual(
            tracker.update(_snapshot(errors=("Codex: RuntimeError",))), []
        )

    def test_muted_agent_suppresses_quota_and_state_alerts(self) -> None:
        tracker = AlertTracker(20, muted_agents={"claude_code"})
        tracker.update(_snapshot(_session(remaining=60)))
        raised = tracker.update(
            _snapshot(
                _session(
                    remaining=5,
                    state=SessionState.RATE_LIMITED,
                )
            )
        )
        self.assertEqual(raised, [])

    def test_muted_agent_does_not_suppress_other_agents(self) -> None:
        tracker = AlertTracker(20, muted_agents={"claude_code"})
        tracker.update(
            _snapshot(
                _session(agent="claude_code", remaining=60),
                _session(agent="codex", session_id="s2", remaining=60),
            )
        )
        raised = tracker.update(
            _snapshot(
                _session(agent="claude_code", remaining=5),
                _session(agent="codex", session_id="s2", remaining=10),
            )
        )
        self.assertEqual(len(raised), 1)
        self.assertIn("Codex", raised[0].title)

    def test_adapter_errors_are_not_muted(self) -> None:
        tracker = AlertTracker(20, muted_agents={"codex"})
        tracker.update(_snapshot(errors=()))
        raised = tracker.update(_snapshot(errors=("Codex: RuntimeError",)))
        self.assertEqual(len(raised), 1)

    def test_set_muted_agents_ignores_empty_values(self) -> None:
        tracker = AlertTracker()
        tracker.set_muted_agents({"codex", ""})  # type: ignore[arg-type]
        self.assertEqual(tracker.muted_agents, {"codex"})

    def test_disabled_notifications_still_advance_state(self) -> None:
        tracker = AlertTracker(low_quota_percent=20)
        tracker.update(_snapshot(_session(remaining=60)), notify=False)
        self.assertEqual(
            tracker.update(_snapshot(_session(remaining=5)), notify=False), []
        )
        self.assertEqual(tracker.update(_snapshot(_session(remaining=5))), [])


if __name__ == "__main__":
    unittest.main()
