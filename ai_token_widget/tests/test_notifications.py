from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ai_token_widget.core.alerts import Alert
from ai_token_widget.core.notifications import (
    NotificationHistory,
    play_notification_sound,
)

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


class NotificationHistoryTest(unittest.TestCase):
    def test_append_newest_first_and_persist_without_alert_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notifications.json"
            history = NotificationHistory(path, limit=3)

            for index, title in enumerate(("a", "b", "c", "d")):
                history.append(
                    Alert(f"SECRET-KEY-{index}", title, f"message-{index}"),
                    now=NOW,
                )

            self.assertEqual(
                [record.title for record in history.records()], ["d", "c", "b"]
            )
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("SECRET-KEY", raw)
            self.assertIn("message-3", raw)

            reloaded = NotificationHistory(path, limit=3)
            self.assertEqual(
                [record.title for record in reloaded.records()],
                ["d", "c", "b"],
            )

    def test_append_many_preserves_order_and_saves_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notifications.json"
            history = NotificationHistory(path)
            alerts = (
                Alert("key-a", "a", "message-a"),
                Alert("key-b", "b", "message-b"),
                Alert("key-c", "c", "message-c"),
            )
            with mock.patch.object(history, "_save") as save:
                count = history.append_many(alerts, now=NOW)
            self.assertEqual(count, 3)
            save.assert_called_once()
            self.assertEqual(
                [record.title for record in history.records()],
                ["a", "b", "c"],
            )

    def test_clear_persists_an_empty_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notifications.json"
            history = NotificationHistory(path)
            history.append(Alert("key", "title", "message"), now=NOW)
            self.assertEqual(len(history), 1)

            history.clear()
            self.assertEqual(len(history), 0)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

            reloaded = NotificationHistory(path)
            self.assertEqual(len(reloaded), 0)

    def test_invalid_records_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notifications.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertLogs(
                "ai_token_widget.notifications", level="WARNING"
            ):
                self.assertEqual(len(NotificationHistory(path)), 0)

            path.write_text(
                json.dumps(
                    [
                        {
                            "created_at": NOW.isoformat(),
                            "title": "good",
                            "message": "kept",
                        },
                        {"created_at": NOW.isoformat(), "title": 5},
                        "not a record",
                    ]
                ),
                encoding="utf-8",
            )
            history = NotificationHistory(path)
            self.assertEqual(len(history), 1)
            self.assertEqual(history.records()[0].title, "good")

    def test_utf8_bom_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notifications.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "created_at": NOW.isoformat(),
                            "title": "title",
                            "message": "message",
                        }
                    ]
                ),
                encoding="utf-8-sig",
            )
            history = NotificationHistory(path)
            self.assertEqual(len(history), 1)
            self.assertEqual(history.records()[0].title, "title")

    def test_load_keeps_the_newest_entries_up_to_the_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notifications.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "created_at": NOW.isoformat(),
                            "title": f"title-{index}",
                            "message": "message",
                        }
                        for index in range(5)
                    ]
                ),
                encoding="utf-8",
            )
            history = NotificationHistory(path, limit=2)
            self.assertEqual(
                [record.title for record in history.records()],
                ["title-0", "title-1"],
            )

    def test_play_sound_returns_false_without_winsound(self) -> None:
        with mock.patch.dict(sys.modules, {"winsound": None}):
            self.assertFalse(play_notification_sound())

    def test_play_sound_uses_winsound(self) -> None:
        calls: list[int] = []
        fake = SimpleNamespace(
            MB_ICONASTERISK=64,
            MessageBeep=lambda value: calls.append(value),
        )
        with mock.patch.dict(sys.modules, {"winsound": fake}):
            self.assertTrue(play_notification_sound())
        self.assertEqual(calls, [64])


if __name__ == "__main__":
    unittest.main()
