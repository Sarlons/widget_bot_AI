from __future__ import annotations

import importlib.util
import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class CardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_card_shows_context_and_quota(self) -> None:
        from PySide6.QtWidgets import QLabel

        from ai_token_widget.core.models import (
            Confidence,
            Quota,
            QuotaWindow,
            Session,
            SessionState,
            Usage,
        )
        from ai_token_widget.ui.cards import SessionCard

        session = Session(
            id="s",
            agent="codex",
            model="gpt-test",
            project="alpha",
            state=SessionState.RUNNING,
            usage_total=Usage(input_tokens=1000, output_tokens=200),
            context_window=10_000,
            context_used=2_500,
            context_estimated=True,
            cost_usd=0.0,
            quota=Quota(
                confidence=Confidence.EXACT,
                windows=(QuotaWindow(label="5h", used_percent=40),),
            ),
            updated_at=datetime.now(timezone.utc),
        )
        card = SessionCard(session)
        texts = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn("Codex", texts)
        self.assertIn("alpha", texts)
        self.assertIn("75% left", texts)
        self.assertIn("60% left", texts)
        self.assertIn("Context (est.)", texts)
        self.assertIn("cost $0.00", texts)
        self.assertIn("EXACT", texts)

    def test_card_without_quota(self) -> None:
        from PySide6.QtWidgets import QLabel

        from ai_token_widget.core.models import Session, SessionState
        from ai_token_widget.ui.cards import SessionCard

        session = Session(
            id="s",
            agent="claude_code",
            model="claude-test",
            project="p",
            state=SessionState.IDLE,
        )
        card = SessionCard(session)
        texts = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn("quota", texts.lower())
        self.assertIn("unavailable", texts.lower())


if __name__ == "__main__":
    unittest.main()
