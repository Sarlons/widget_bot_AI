from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai_token_widget import claude_statusline
from ai_token_widget.claude_bridge import (
    BridgeError,
    command_for,
    install,
    status,
    uninstall,
)

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


class NormalizeTest(unittest.TestCase):
    def test_current_shape(self) -> None:
        payload = {
            "session_id": "sess-1",
            "rate_limits": {
                "five_hour": {
                    "used_percentage": 42.5,
                    "resets_at": 1792690000,
                },
                "seven_day": {
                    "used_percentage": 18,
                    "resets_at": "2026-10-29T00:00:00Z",
                },
            },
        }
        snapshot = claude_statusline.normalize(payload, NOW)
        self.assertEqual(snapshot["session_id"], "sess-1")
        self.assertEqual(
            [window["label"] for window in snapshot["windows"]], ["5h", "weekly"]
        )
        self.assertEqual(snapshot["windows"][0]["used_percent"], 42.5)
        self.assertEqual(snapshot["windows"][1]["used_percent"], 18.0)
        self.assertEqual(snapshot["windows"][1]["resets_at"], "2026-10-29T00:00:00+00:00")

    def test_legacy_primary_secondary_shape(self) -> None:
        payload = {
            "rate_limits": {
                "primary": {"used_percent": 7, "reset_at": 1792690000000},
                "secondary": {"utilization": 0.5},
            }
        }
        snapshot = claude_statusline.normalize(payload, NOW)
        self.assertEqual(snapshot["windows"][0]["label"], "5h")
        self.assertEqual(snapshot["windows"][0]["used_percent"], 7.0)
        self.assertEqual(snapshot["windows"][1]["label"], "weekly")

    def test_no_rate_limits(self) -> None:
        snapshot = claude_statusline.normalize({"session_id": "s"}, NOW)
        self.assertEqual(snapshot["windows"], [])
        self.assertEqual(claude_statusline.status_text(snapshot), "Claude")

    def test_status_text(self) -> None:
        snapshot = {
            "windows": [
                {"label": "5h", "used_percent": 42},
                {"label": "weekly", "used_percent": 18},
            ]
        }
        self.assertEqual(
            claude_statusline.status_text(snapshot), "5h 58% left · weekly 82% left"
        )


class SnapshotTest(unittest.TestCase):
    def test_write_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "snapshot.json"
            snapshot = claude_statusline.normalize(
                {
                    "rate_limits": {
                        "five_hour": {"used_percentage": 10},
                    }
                },
                NOW,
            )
            written = claude_statusline.write_snapshot(snapshot, path)
            self.assertEqual(written, path)
            self.assertEqual(claude_statusline.read_snapshot(path), snapshot)

    def test_script_captures_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env = os.environ.copy()
            env["AITOKENWIDGET_DATA_DIR"] = temporary
            payload = {
                "session_id": "sess-2",
                "rate_limits": {"five_hour": {"used_percentage": 42}},
            }
            completed = subprocess.run(
                [sys.executable, str(Path(claude_statusline.__file__))],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                env=env,
                timeout=20,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertIn("58% left", completed.stdout)
            raw = json.loads(
                (Path(temporary) / claude_statusline.SNAPSHOT_NAME).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(raw["session_id"], "sess-2")
            self.assertEqual(raw["windows"][0]["used_percent"], 42.0)


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Path(self.temp.name) / "settings.json"
        self.data = Path(self.temp.name) / "data"
        self.settings.write_text(
            json.dumps(
                {
                    "theme": "dark",
                    "env": {"ANTHROPIC_API_KEY": "sk-not-a-real-secret"},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _read_settings(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def test_install_then_uninstall_restores_only_statusline(self) -> None:
        result = install(self.settings, self.data, python_exe="python")
        self.assertTrue(result.changed)
        settings = self._read_settings()
        self.assertIn("claude_statusline.py", settings["statusLine"]["command"])
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["env"]["ANTHROPIC_API_KEY"], "sk-not-a-real-secret")
        undo_text = result.undo_path.read_text(encoding="utf-8")
        self.assertNotIn("sk-not-a-real-secret", undo_text)
        self.assertTrue(status(self.settings, self.data)["installed"])

        removed = uninstall(self.settings, self.data)
        self.assertTrue(removed.changed)
        settings = self._read_settings()
        self.assertNotIn("statusLine", settings)
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["env"]["ANTHROPIC_API_KEY"], "sk-not-a-real-secret")
        self.assertFalse(result.undo_path.exists())

    def test_reinstall_is_a_noop(self) -> None:
        install(self.settings, self.data, python_exe="python")
        second = install(self.settings, self.data, python_exe="python")
        self.assertFalse(second.changed)

    def test_reinstall_updates_a_moved_bridge_command(self) -> None:
        install(self.settings, self.data, python_exe="python")
        second = install(self.settings, self.data, python_exe="python3")
        self.assertTrue(second.changed)
        self.assertIn('"python3"', self._read_settings()["statusLine"]["command"])
        uninstall(self.settings, self.data)
        self.assertNotIn("statusLine", self._read_settings())

    def test_existing_statusline_requires_force_and_is_restored(self) -> None:
        original = {"type": "command", "command": "echo custom"}
        raw = self._read_settings()
        raw["statusLine"] = original
        self.settings.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaises(BridgeError):
            install(self.settings, self.data, python_exe="python")
        result = install(self.settings, self.data, python_exe="python", force=True)
        self.assertTrue(result.changed)
        self.assertIn("claude_statusline.py", self._read_settings()["statusLine"]["command"])

        uninstall(self.settings, self.data)
        self.assertEqual(self._read_settings()["statusLine"], original)

    def test_uninstall_without_install_fails(self) -> None:
        with self.assertRaises(BridgeError):
            uninstall(self.settings, self.data)

    def test_command_contains_script_and_optional_data_dir(self) -> None:
        command = command_for("python", self.data)
        self.assertIn("claude_statusline.py", command)
        self.assertIn("--data-dir", command)

    def test_frozen_command_uses_bridge_executable(self) -> None:
        from unittest import mock

        from ai_token_widget import claude_bridge

        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "AITokenWidgetBridge.exe"
            executable.write_bytes(b"")
            with (
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "executable", str(executable)),
            ):
                command = command_for(data_dir=self.data)

        self.assertEqual(command, f'"{executable}" --data-dir "{self.data}"')
        self.assertTrue(claude_bridge._is_ours(command))

        with (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", str(executable)),
        ):
            with self.assertRaises(BridgeError):
                command_for("python", self.data)


if __name__ == "__main__":
    unittest.main()
