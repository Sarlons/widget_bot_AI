from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ai_token_widget.core.filters import (
    FilterMode,
    SessionFilter,
    filter_sessions,
    needs_attention,
)
from ai_token_widget.core.grouping import group_sessions
from ai_token_widget.core.models import (
    Confidence,
    Quota,
    QuotaWindow,
    Session,
    SessionState,
)

NOW = datetime.now(timezone.utc)


def _session(
    session_id: str,
    *,
    agent: str = "codex",
    project: str = "alpha",
    model: str = "gpt-test",
    state: SessionState = SessionState.IDLE,
    remaining: float | None = None,
    context_used: int | None = None,
) -> Session:
    quota = None
    if remaining is not None:
        quota = Quota(
            confidence=Confidence.EXACT,
            windows=(QuotaWindow(label="5h", used_percent=100 - remaining),),
        )
    return Session(
        id=session_id,
        agent=agent,
        model=model,
        project=project,
        state=state,
        quota=quota,
        context_window=100 if context_used is not None else None,
        context_used=context_used,
        updated_at=NOW,
    )


class FilterTest(unittest.TestCase):
    def test_running_filter(self) -> None:
        sessions = (
            _session("a", state=SessionState.RUNNING),
            _session("b", state=SessionState.IDLE),
            _session("c", state=SessionState.RUNNING),
        )
        result = filter_sessions(sessions, SessionFilter(FilterMode.RUNNING))
        self.assertEqual([session.id for session in result], ["a", "c"])

    def test_attention_filter_covers_quota_state_and_context(self) -> None:
        sessions = (
            _session("normal"),
            _session("limited", state=SessionState.RATE_LIMITED),
            _session("quota", remaining=15),
            _session("context", context_used=95),
        )
        result = filter_sessions(sessions, SessionFilter(FilterMode.ATTENTION))
        self.assertEqual(
            [session.id for session in result], ["limited", "quota", "context"]
        )

    def test_attention_respects_custom_quota_threshold(self) -> None:
        session = _session("quota", remaining=24)
        self.assertFalse(needs_attention(session, low_quota_percent=20))
        self.assertTrue(needs_attention(session, low_quota_percent=25))

    def test_query_matches_project_model_and_agent(self) -> None:
        sessions = (
            _session("alpha", project="Alpha Project", model="gpt-test"),
            _session(
                "claude",
                agent="claude_code",
                project="other",
                model="claude-opus",
            ),
        )
        result = filter_sessions(sessions, SessionFilter(query="ALPHA gpt"))
        self.assertEqual([session.id for session in result], ["alpha"])
        result = filter_sessions(sessions, SessionFilter(query="claude"))
        self.assertEqual([session.id for session in result], ["claude"])

    def test_empty_query_does_not_filter(self) -> None:
        sessions = (_session("a"), _session("b"))
        self.assertEqual(
            len(filter_sessions(sessions, SessionFilter(query="   "))), 2
        )


class GroupingTest(unittest.TestCase):
    def test_groups_follow_provider_priority_and_keep_order(self) -> None:
        sessions = (
            _session("codex-1", agent="codex"),
            _session("other", agent="unknown"),
            _session("claude", agent="claude_code"),
            _session("codex-2", agent="codex"),
            _session("opencode", agent="opencode"),
        )
        groups = group_sessions(sessions)
        self.assertEqual(
            [group.agent for group in groups],
            ["claude_code", "codex", "opencode", "unknown"],
        )
        codex = groups[1]
        self.assertEqual([session.id for session in codex.sessions], ["codex-1", "codex-2"])
        self.assertEqual(codex.running_count, 0)
        self.assertEqual(codex.issue_count, 0)

    def test_group_counts(self) -> None:
        sessions = (
            _session("a", agent="codex", state=SessionState.RUNNING),
            _session("b", agent="codex", state=SessionState.RATE_LIMITED),
            _session("c", agent="codex", state=SessionState.ERROR),
        )
        group = group_sessions(sessions)[0]
        self.assertEqual(len(group.sessions), 3)
        self.assertEqual(group.running_count, 1)
        self.assertEqual(group.issue_count, 2)


if __name__ == "__main__":
    unittest.main()
