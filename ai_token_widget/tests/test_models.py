from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ai_token_widget.core.formatting import format_cost, format_tokens
from ai_token_widget.core.models import QuotaWindow, Session, SessionState, Usage


class UsageTest(unittest.TestCase):
    def test_total_uses_reported_value(self) -> None:
        usage = Usage(input_tokens=10, output_tokens=5, reported_total=100)
        self.assertEqual(usage.total, 100)
        self.assertEqual(usage.billed_input, 10)

    def test_total_sums_fields_without_reported_value(self) -> None:
        usage = Usage(
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=100,
            cache_write_tokens=20,
            reasoning_tokens=5,
        )
        self.assertEqual(usage.total, 140)

    def test_billed_input_override_avoids_double_counting_cache(self) -> None:
        usage = Usage(
            input_tokens=1_000,
            output_tokens=200,
            cache_read_tokens=800,
            billed_input_tokens=1_000,
        )
        self.assertEqual(usage.billed_input, 1_000)

    def test_add(self) -> None:
        combined = Usage(input_tokens=1, reported_total=10) + Usage(
            input_tokens=2, reported_total=20
        )
        self.assertEqual(combined.input_tokens, 3)
        self.assertEqual(combined.reported_total, 30)
        self.assertEqual(combined.billed_input, 3)


class QuotaWindowTest(unittest.TestCase):
    def test_remaining_is_clamped(self) -> None:
        self.assertEqual(QuotaWindow(label="5h", used_percent=110).remaining_percent, 0)
        self.assertEqual(QuotaWindow(label="5h", used_percent=-5).remaining_percent, 100)
        self.assertTrue(QuotaWindow(label="5h", used_percent=100).exhausted)


class SessionTest(unittest.TestCase):
    def test_context_remaining(self) -> None:
        session = Session(
            id="s",
            agent="codex",
            model="m",
            project="p",
            state=SessionState.IDLE,
            context_window=10_000,
            context_used=2_500,
            updated_at=datetime.now(timezone.utc),
        )
        self.assertEqual(session.context_used_percent, 25.0)
        self.assertEqual(session.context_remaining_percent, 75.0)
        self.assertEqual(session.context_remaining, 7_500)

    def test_context_missing(self) -> None:
        session = Session(
            id="s", agent="codex", model="m", project="p", state=SessionState.IDLE
        )
        self.assertIsNone(session.context_used_percent)
        self.assertIsNone(session.context_remaining)


class FormattingTest(unittest.TestCase):
    def test_tokens(self) -> None:
        self.assertEqual(format_tokens(999), "999")
        self.assertEqual(format_tokens(1_500), "1.5K")
        self.assertEqual(format_tokens(2_500_000), "2.5M")
        self.assertEqual(format_tokens(None), "—")

    def test_cost(self) -> None:
        self.assertEqual(format_cost(0), "$0.00")
        self.assertEqual(format_cost(1.234), "$1.23")
        self.assertEqual(format_cost(0.0004), "<$0.01")
        self.assertEqual(format_cost(None), "—")


if __name__ == "__main__":
    unittest.main()
