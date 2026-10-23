from __future__ import annotations

import importlib.util
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


class FakeRegistry:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot
        self.closed = False

    def refresh(self):
        return self.snapshot

    def close(self) -> None:
        self.closed = True


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class WindowRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_background_snapshot_reaches_the_window(self) -> None:
        from ai_token_widget.core.config import Config
        from ai_token_widget.core.models import Session, SessionState, Snapshot
        from ai_token_widget.ui.window import WidgetWindow

        session = Session(
            id="s",
            agent="codex",
            model="gpt-test",
            project="alpha",
            state=SessionState.RUNNING,
            updated_at=datetime.now(timezone.utc),
        )
        registry = FakeRegistry(Snapshot(sessions=(session,)))
        window = WidgetWindow(
            registry,
            Config(poll_seconds=60, window_x=0, window_y=0),
        )
        try:
            self._wait_for(window, lambda: bool(window._snapshot.sessions))
            self.assertEqual(len(window._snapshot.sessions), 1)
            self.assertEqual(window._summary.text(), "1 running")
        finally:
            window.shutdown()
            window.deleteLater()
            self.app.processEvents()

    def test_settings_apply_live_and_save_once(self) -> None:
        from unittest import mock

        from PySide6.QtCore import Qt

        from ai_token_widget.core.config import Config
        from ai_token_widget.core.models import Snapshot
        from ai_token_widget.ui.settings import SettingsDialog
        from ai_token_widget.ui.window import WidgetWindow

        config = Config(
            poll_seconds=60,
            low_quota_percent=20,
            muted_agents=[],
            window_x=0,
            window_y=0,
        )
        window = WidgetWindow(FakeRegistry(Snapshot()), config)
        dialog = SettingsDialog(config)
        try:
            dialog._notifications.setChecked(False)
            dialog._low_quota.setValue(30)
            dialog._poll.setValue(15)
            dialog._mutes["codex"].setChecked(True)
            dialog._always_on_top.setChecked(False)
            dialog._start_collapsed.setChecked(True)
            dialog._opacity.setValue(70)
            dialog._reset_position.click()

            with mock.patch.object(config, "save", return_value=True) as save:
                window._apply_settings(dialog)

            self.assertTrue(save.called)
            self.assertFalse(config.notifications_enabled)
            self.assertEqual(config.low_quota_percent, 30)
            self.assertEqual(config.poll_seconds, 15)
            self.assertEqual(config.muted_agents, ["codex"])
            self.assertFalse(config.always_on_top)
            self.assertTrue(config.collapsed)
            self.assertIsNone(config.window_x)
            self.assertIsNone(config.window_y)
            self.assertAlmostEqual(config.opacity, 0.7)
            self.assertAlmostEqual(window.windowOpacity(), 0.7, places=2)
            self.assertFalse(
                bool(
                    window.windowFlags()
                    & Qt.WindowType.WindowStaysOnTopHint
                )
            )
            self.assertEqual(window.height(), 74)
            self.assertTrue(window._body.isHidden())
            self.assertEqual(window._timer.interval(), 15_000)
            self.assertEqual(window._alerts.low_quota_percent, 30)
            self.assertEqual(window._alerts.muted_agents, {"codex"})
            if window._notifications_action is not None:
                self.assertFalse(window._notifications_action.isChecked())
        finally:
            dialog.deleteLater()
            window.shutdown()
            window.deleteLater()
            self.app.processEvents()

    def test_open_settings_applies_dialog(self) -> None:
        from unittest import mock

        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from ai_token_widget.core.config import Config
        from ai_token_widget.core.models import Snapshot
        from ai_token_widget.ui.settings import SettingsDialog
        from ai_token_widget.ui.window import WidgetWindow

        config = Config(poll_seconds=60, window_x=0, window_y=0)
        window = WidgetWindow(FakeRegistry(Snapshot()), config)

        def accept_dialog() -> None:
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, SettingsDialog):
                    widget._low_quota.setValue(25)
                    widget._poll.setValue(10)
                    widget.accept()
                    return
            QTimer.singleShot(20, accept_dialog)

        try:
            QTimer.singleShot(20, accept_dialog)
            with mock.patch.object(config, "save", return_value=True):
                window._open_settings()

            self.assertEqual(config.low_quota_percent, 25)
            self.assertEqual(config.poll_seconds, 10)
            self.assertEqual(window._timer.interval(), 10_000)
        finally:
            window.shutdown()
            window.deleteLater()
            self.app.processEvents()

    def test_footer_marks_stale_and_slow_refreshes(self) -> None:
        from ai_token_widget.core.config import Config
        from ai_token_widget.core.models import Session, SessionState, Snapshot
        from ai_token_widget.ui.window import WidgetWindow

        now = datetime.now(timezone.utc)
        session = Session(
            id="s",
            agent="codex",
            model="gpt-test",
            project="alpha",
            state=SessionState.IDLE,
            updated_at=now,
        )
        window = WidgetWindow(
            FakeRegistry(Snapshot(sessions=(session,))),
            Config(poll_seconds=5, window_x=0, window_y=0),
        )
        try:
            self._wait_for(window, lambda: window._last_snapshot_at is not None)
            window._last_snapshot_at = now - timedelta(seconds=45)
            window._update_footer()
            self.assertIn("stale", window._footer.text())
            self.assertIn("45s ago", window._footer.text())

            window._refresh_busy = True
            window._refresh_started_monotonic = time.monotonic() - 20
            window._update_footer()
            self.assertIn("refresh slow (20s)", window._footer.text())
        finally:
            window.shutdown()
            window.deleteLater()
            self.app.processEvents()

    def test_alerts_are_persisted_and_sound_plays_once(self) -> None:
        from unittest import mock

        from ai_token_widget.core.alerts import Alert
        from ai_token_widget.core.config import Config
        from ai_token_widget.core.models import Snapshot
        from ai_token_widget.core.notifications import NotificationHistory
        from ai_token_widget.ui.window import WidgetWindow

        class FakeTray:
            def __init__(self) -> None:
                self.messages: list[tuple] = []

            def showMessage(self, *args) -> None:
                self.messages.append(args)

        with tempfile.TemporaryDirectory() as temporary:
            from pathlib import Path

            path = Path(temporary) / "notifications.json"
            history = NotificationHistory(path)
            window = WidgetWindow(
                FakeRegistry(Snapshot()),
                Config(
                    poll_seconds=60,
                    notification_sound=True,
                    window_x=0,
                    window_y=0,
                ),
                history=history,
            )
            tray = FakeTray()
            window._tray = tray
            try:
                alerts = [
                    Alert(f"SECRET-KEY-{index}", f"title-{index}", "message")
                    for index in range(5)
                ]
                with mock.patch(
                    "ai_token_widget.ui.window.play_notification_sound"
                ) as sound:
                    window._show_alerts(alerts)
                self.assertEqual(len(tray.messages), 3)
                self.assertEqual(len(history), 5)
                sound.assert_called_once()
                self.assertNotIn(
                    "SECRET-KEY", path.read_text(encoding="utf-8")
                )
            finally:
                window.shutdown()
                window.deleteLater()
                self.app.processEvents()

    def test_diagnostics_text_is_sanitized(self) -> None:
        from ai_token_widget.core.config import Config
        from ai_token_widget.core.models import Session, SessionState, Snapshot
        from ai_token_widget.ui.window import WidgetWindow

        now = datetime.now(timezone.utc)
        session = Session(
            id="SECRET-ID",
            agent="codex",
            model="SECRET-MODEL",
            project="SECRET-PROJECT",
            state=SessionState.RUNNING,
            updated_at=now,
            cwd="C:\\SECRET-CWD",
        )
        window = WidgetWindow(
            FakeRegistry(Snapshot(sessions=(session,))),
            Config(poll_seconds=60, window_x=0, window_y=0),
        )
        try:
            self._wait_for(window, lambda: window._last_snapshot_at is not None)
            report = window._diagnostics_text()
            self.assertIn("Sessions: 1 total · 1 running", report)
            self.assertIn("Codex: 1 sessions, 1 running", report)
            self.assertNotIn("SECRET", report)
        finally:
            window.shutdown()
            window.deleteLater()
            self.app.processEvents()

    def test_groups_and_filters(self) -> None:
        from PySide6.QtWidgets import QLabel

        from ai_token_widget.core.config import Config
        from ai_token_widget.core.filters import FilterMode
        from ai_token_widget.core.models import Session, SessionState, Snapshot
        from ai_token_widget.ui.cards import SessionCard
        from ai_token_widget.ui.groups import GroupHeader
        from ai_token_widget.ui.window import WidgetWindow
        now = datetime.now(timezone.utc)
        snapshot = Snapshot(
            sessions=(
                Session(
                    id="codex",
                    agent="codex",
                    model="gpt-test",
                    project="alpha",
                    state=SessionState.RUNNING,
                    updated_at=now,
                ),
                Session(
                    id="claude",
                    agent="claude_code",
                    model="claude-test",
                    project="beta",
                    state=SessionState.IDLE,
                    updated_at=now,
                ),
            )
        )
        window = WidgetWindow(
            FakeRegistry(snapshot),
            Config(poll_seconds=60, window_x=0, window_y=0),
        )
        try:
            self._wait_for(window, lambda: bool(window._snapshot.sessions))
            self.assertEqual(len(window.findChildren(SessionCard)), 2)
            headers = window.findChildren(GroupHeader)
            self.assertEqual(
                [header.agent for header in headers],
                ["claude_code", "codex"],
            )

            window._filter_buttons[FilterMode.RUNNING].click()
            self.app.processEvents()
            self.assertEqual(len(window.findChildren(SessionCard)), 1)
            self.assertIn("1/2 shown", window._summary.text())

            window._search.setText("no-such-session")
            self.app.processEvents()
            self.assertEqual(len(window.findChildren(SessionCard)), 0)
            texts = " ".join(
                label.text() for label in window.findChildren(QLabel)
            )
            self.assertIn("No sessions match", texts)

            window._clear_filters()
            self.app.processEvents()
            self.assertEqual(len(window.findChildren(SessionCard)), 2)

            window._config.collapsed_groups = ["codex"]
            window._render()
            self.app.processEvents()
            self.assertEqual(len(window.findChildren(SessionCard)), 1)
        finally:
            window.shutdown()
            window.deleteLater()
            self.app.processEvents()

    def _wait_for(self, window, predicate, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
