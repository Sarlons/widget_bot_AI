from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class NotificationHistoryDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_empty_state_and_clear(self) -> None:
        from ai_token_widget.core.alerts import Alert
        from ai_token_widget.core.notifications import NotificationHistory
        from ai_token_widget.ui.history import NotificationHistoryDialog

        with tempfile.TemporaryDirectory() as temporary:
            history = NotificationHistory(
                Path(temporary) / "notifications.json"
            )
            dialog = NotificationHistoryDialog(history)
            try:
                self.assertFalse(dialog._clear.isEnabled())
                self.assertIn("No notifications", dialog._count.text())

                history.append(
                    Alert(
                        "SECRET-KEY",
                        "Codex quota low",
                        "5h quota at 10% remaining",
                    ),
                    now=datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc),
                )
                dialog._rebuild()
                self.assertTrue(dialog._clear.isEnabled())
                self.assertIn("1 saved alert", dialog._count.text())

                dialog._clear_history()
                self.assertEqual(len(history), 0)
                self.assertFalse(dialog._clear.isEnabled())
                self.assertIn("No notifications", dialog._count.text())
            finally:
                dialog.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
