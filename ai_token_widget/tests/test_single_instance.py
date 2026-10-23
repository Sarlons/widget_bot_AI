from __future__ import annotations

import importlib.util
import os
import time
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class SingleInstanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _name(self) -> str:
        return f"AITokenWidget-test-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def test_second_instance_notifies_first(self) -> None:
        from ai_token_widget.single_instance import SingleInstance

        first = SingleInstance(self._name())
        second = None
        try:
            self.assertTrue(first.acquire())
            hits: list[bool] = []
            first.activated.connect(lambda: hits.append(True))

            second = SingleInstance(first.name)
            self.assertFalse(second.acquire())
            # Releasing the losing instance must not tear down the owner.
            second.close()
            second = SingleInstance(first.name)
            self.assertFalse(second.acquire())

            for _ in range(20):
                self.app.processEvents()
                if hits:
                    break
                time.sleep(0.01)
            self.assertGreaterEqual(len(hits), 1)
        finally:
            if second is not None:
                second.close()
            first.close()

    def test_quit_request_notifies_first(self) -> None:
        from ai_token_widget.single_instance import SingleInstance, request_quit

        first = SingleInstance(self._name())
        try:
            self.assertTrue(first.acquire())
            activated: list[bool] = []
            quit_hits: list[bool] = []
            first.activated.connect(lambda: activated.append(True))
            first.quit_requested.connect(lambda: quit_hits.append(True))

            self.assertTrue(request_quit(first.name))

            for _ in range(20):
                self.app.processEvents()
                if quit_hits:
                    break
                time.sleep(0.01)
            self.assertEqual(len(quit_hits), 1)
            self.assertEqual(activated, [])
        finally:
            first.close()

    def test_name_can_be_reacquired_after_close(self) -> None:
        from ai_token_widget.single_instance import SingleInstance

        name = self._name()
        first = SingleInstance(name)
        self.assertTrue(first.acquire())
        first.close()

        replacement = SingleInstance(name)
        try:
            self.assertTrue(replacement.acquire())
        finally:
            replacement.close()


if __name__ == "__main__":
    unittest.main()
