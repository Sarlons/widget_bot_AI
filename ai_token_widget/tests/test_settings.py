from __future__ import annotations

import importlib.util
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_QT, "PySide6 is not installed")
class SettingsDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_initializes_from_config(self) -> None:
        from ai_token_widget.core.config import Config
        from ai_token_widget.ui.settings import SettingsDialog

        config = Config(
            notifications_enabled=False,
            notification_sound=True,
            low_quota_percent=35,
            poll_seconds=12,
            muted_agents=["codex"],
            always_on_top=False,
            collapsed=True,
            opacity=0.8,
        )
        dialog = SettingsDialog(config)
        try:
            self.assertFalse(dialog._notifications.isChecked())
            self.assertTrue(dialog._sound.isChecked())
            self.assertFalse(dialog._sound.isEnabled())
            self.assertEqual(dialog._low_quota.value(), 35)
            self.assertEqual(dialog._poll.value(), 12)
            self.assertFalse(dialog._always_on_top.isChecked())
            self.assertTrue(dialog._start_collapsed.isChecked())
            self.assertEqual(dialog._opacity.value(), 80)
            self.assertEqual(dialog._opacity_value.text(), "80%")
            self.assertFalse(dialog.reset_position_requested())
            self.assertFalse(dialog._mutes["claude_code"].isChecked())
            self.assertTrue(dialog._mutes["codex"].isChecked())
            self.assertFalse(dialog._mutes["opencode"].isChecked())
        finally:
            dialog.deleteLater()
            self.app.processEvents()

    def test_apply_updates_config_and_preserves_unknown_mutes(self) -> None:
        from ai_token_widget.core.config import Config
        from ai_token_widget.ui.settings import SettingsDialog

        config = Config(
            notifications_enabled=False,
            low_quota_percent=35,
            poll_seconds=12,
            muted_agents=["future_agent", "codex"],
        )
        dialog = SettingsDialog(config)
        try:
            dialog._notifications.setChecked(True)
            dialog._sound.setChecked(True)
            dialog._low_quota.setValue(10)
            dialog._poll.setValue(20)
            dialog._mutes["claude_code"].setChecked(True)
            dialog._mutes["codex"].setChecked(False)
            dialog._always_on_top.setChecked(False)
            dialog._start_collapsed.setChecked(True)
            dialog._opacity.setValue(65)
            dialog._reset_position.click()

            self.assertFalse(config.notifications_enabled)
            self.assertTrue(dialog._sound.isEnabled())
            self.assertTrue(dialog.reset_position_requested())
            self.assertEqual(dialog._reset_position.text(), "Reset on Save")
            self.assertFalse(dialog._reset_position.isEnabled())
            dialog.apply_to(config)

            self.assertTrue(config.notifications_enabled)
            self.assertTrue(config.notification_sound)
            self.assertEqual(config.low_quota_percent, 10)
            self.assertEqual(config.poll_seconds, 20)
            self.assertFalse(config.always_on_top)
            self.assertTrue(config.collapsed)
            self.assertEqual(config.opacity, 0.65)
            self.assertEqual(config.muted_agents, ["claude_code", "future_agent"])
        finally:
            dialog.deleteLater()
            self.app.processEvents()


    def test_copy_diagnostics_uses_provider(self) -> None:
        from PySide6.QtWidgets import QApplication

        from ai_token_widget.core.config import Config
        from ai_token_widget.ui.settings import SettingsDialog

        dialog = SettingsDialog(
            Config(), diagnostics_provider=lambda: "sanitized report"
        )
        try:
            dialog._copy_diagnostics()
            self.assertEqual(
                QApplication.clipboard().text(), "sanitized report"
            )
            self.assertEqual(dialog._copy_report.text(), "Copied")
        finally:
            dialog.deleteLater()
            self.app.processEvents()

    def test_diagnostics_button_requires_provider(self) -> None:
        from ai_token_widget.core.config import Config
        from ai_token_widget.ui.settings import SettingsDialog

        without = SettingsDialog(Config())
        with_provider = SettingsDialog(
            Config(), diagnostics_provider=lambda: "report"
        )
        try:
            self.assertFalse(without._copy_report.isEnabled())
            self.assertTrue(with_provider._copy_report.isEnabled())
        finally:
            without.deleteLater()
            with_provider.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
