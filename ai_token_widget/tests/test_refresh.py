from __future__ import annotations

import importlib.util
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


class StubRegistry:
    def __init__(self, snapshot=None, error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.error = error

    def refresh(self):
        if self.error is not None:
            raise self.error
        return self.snapshot


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class RefreshWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_emits_snapshot(self) -> None:
        from ai_token_widget.core.models import Snapshot
        from ai_token_widget.ui.refresh import RefreshWorker

        snapshot = Snapshot()
        worker = RefreshWorker(StubRegistry(snapshot))
        received = []
        worker.snapshot_ready.connect(received.append)
        worker.refresh()
        self.assertEqual(received, [snapshot])

    def test_emits_failure_without_raising(self) -> None:
        from ai_token_widget.ui.refresh import RefreshWorker

        worker = RefreshWorker(StubRegistry(error=RuntimeError("boom")))
        failed = []
        worker.failed.connect(failed.append)
        with self.assertLogs("ai_token_widget.refresh", level="ERROR"):
            worker.refresh()
        self.assertEqual(failed, ["RuntimeError"])


if __name__ == "__main__":
    unittest.main()
