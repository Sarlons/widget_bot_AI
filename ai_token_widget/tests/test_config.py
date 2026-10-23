from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_token_widget.core.config import Config


class ConfigTest(unittest.TestCase):
    def test_defaults_enable_notifications(self) -> None:
        config = Config()
        self.assertTrue(config.notifications_enabled)
        self.assertFalse(config.notification_sound)
        self.assertTrue(config.always_on_top)
        self.assertFalse(config.collapsed)
        self.assertEqual(config.low_quota_percent, 20)
        self.assertEqual(config.muted_agents, [])
        self.assertEqual(config.collapsed_groups, [])

    def test_validate_clamps_new_fields(self) -> None:
        config = Config(low_quota_percent=0)
        config.validate()
        self.assertEqual(config.low_quota_percent, 1)

        config = Config(low_quota_percent=99)
        config.validate()
        self.assertEqual(config.low_quota_percent, 50)

        config = Config(notifications_enabled="yes")  # type: ignore[arg-type]
        config.validate()
        self.assertTrue(config.notifications_enabled)

        config = Config(notification_sound="yes")  # type: ignore[arg-type]
        config.validate()
        self.assertFalse(config.notification_sound)

        config = Config(always_on_top="yes", collapsed="yes")  # type: ignore[arg-type]
        config.validate()
        self.assertTrue(config.always_on_top)
        self.assertFalse(config.collapsed)

        config = Config(opacity=2.0, window_width=10, window_height=10)
        config.validate()
        self.assertEqual(config.opacity, 1.0)
        self.assertEqual(config.window_width, 320)
        self.assertEqual(config.window_height, 360)

        config = Config(
            collapsed_groups=["codex", "", "codex", 5]  # type: ignore[list-item]
        )
        config.validate()
        self.assertEqual(config.collapsed_groups, ["codex"])

        config = Config(collapsed_groups="codex")  # type: ignore[arg-type]
        config.validate()
        self.assertEqual(config.collapsed_groups, [])

        config = Config(
            muted_agents=["codex", "", "codex", 5]  # type: ignore[list-item]
        )
        config.validate()
        self.assertEqual(config.muted_agents, ["codex"])

        config = Config(muted_agents="codex")  # type: ignore[arg-type]
        config.validate()
        self.assertEqual(config.muted_agents, [])

    def test_load_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "poll_seconds": 9,
                        "always_on_top": False,
                        "opacity": 0.8,
                        "collapsed": True,
                    }
                ),
                encoding="utf-8-sig",
            )
            config = Config.load(path)

        self.assertEqual(config.poll_seconds, 9)
        self.assertFalse(config.always_on_top)
        self.assertEqual(config.opacity, 0.8)
        self.assertTrue(config.collapsed)

    def test_load_ignores_unknown_keys_and_keeps_new_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps({"poll_seconds": 9, "future": True}), encoding="utf-8")
            config = Config.load(path)

        self.assertEqual(config.poll_seconds, 9)
        self.assertTrue(config.notifications_enabled)
        self.assertEqual(config.low_quota_percent, 20)
        self.assertEqual(config.muted_agents, [])
        self.assertEqual(config.collapsed_groups, [])

    def test_muted_agents_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            config = Config(
                muted_agents=["opencode", "codex", "codex"],
                low_quota_percent=33,
                notification_sound=True,
            )
            config.validate()
            self.assertTrue(config.save(path))

            loaded = Config.load(path)

        self.assertEqual(loaded.muted_agents, ["codex", "opencode"])
        self.assertEqual(loaded.low_quota_percent, 33)
        self.assertTrue(loaded.notification_sound)


if __name__ == "__main__":
    unittest.main()
