from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_token_widget.core.config import Config
from ai_token_widget.core.diagnostics import build_diagnostics
from ai_token_widget.core.models import Session, SessionState, Snapshot

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)


class DiagnosticsTest(unittest.TestCase):
    def test_report_counts_without_session_details(self) -> None:
        snapshot = Snapshot(
            sessions=(
                Session(
                    id="SECRET-ID",
                    agent="codex",
                    model="SECRET-MODEL",
                    project="SECRET-PROJECT",
                    state=SessionState.RUNNING,
                    updated_at=NOW,
                    cwd="C:\\SECRET-CWD",
                ),
                Session(
                    id="SECRET-ID-2",
                    agent="claude_code",
                    model="SECRET-MODEL-2",
                    project="SECRET-PROJECT-2",
                    state=SessionState.IDLE,
                    updated_at=NOW,
                    cwd="C:\\SECRET-CWD-2",
                ),
            )
        )

        report = build_diagnostics(
            version="9.9.9",
            config=Config(),
            snapshot=snapshot,
            last_snapshot_at=NOW,
            refresh_busy=False,
            now=NOW,
        )

        self.assertIn("AI Token Widget 9.9.9", report)
        self.assertIn("Sessions: 2 total · 1 running · 0 limited", report)
        self.assertIn("Codex: 1 sessions, 1 running", report)
        self.assertIn("Claude Code: 1 sessions, 0 running", report)
        self.assertIn("OpenCode: 0 sessions, 0 running", report)
        self.assertIn("%APPDATA%\\AITokenWidget\\widget.log", report)
        for secret in (
            "SECRET-ID",
            "SECRET-MODEL",
            "SECRET-PROJECT",
            "SECRET-CWD",
        ):
            self.assertNotIn(secret, report)

    def test_report_includes_age_refresh_and_errors(self) -> None:
        report = build_diagnostics(
            version="0.5.1",
            config=Config(
                poll_seconds=5,
                low_quota_percent=25,
                notification_sound=True,
            ),
            snapshot=Snapshot(errors=("Codex: RuntimeError",)),
            last_snapshot_at=NOW - timedelta(seconds=125),
            refresh_busy=True,
            refresh_seconds=42.0,
            refresh_error="TimeoutError",
            history_count=4,
            now=NOW,
        )

        self.assertIn("Snapshot age: 2m ago", report)
        self.assertIn("Refresh: running for 42s", report)
        self.assertIn("Last refresh error: TimeoutError", report)
        self.assertIn("  - Codex: RuntimeError", report)
        self.assertIn("poll=5s, low_quota=25%", report)
        self.assertIn("sound=on", report)
        self.assertIn("Notification history: 4 saved alerts", report)

    def test_empty_report(self) -> None:
        report = build_diagnostics(
            version="0.5.1",
            config=Config(),
            snapshot=Snapshot(),
            last_snapshot_at=None,
            refresh_busy=False,
            history_count=0,
            now=NOW,
        )

        self.assertIn("Snapshot: none", report)
        self.assertIn("Snapshot age: none", report)
        self.assertIn("Refresh: idle", report)
        self.assertIn("Sessions: 0 total · 0 running · 0 limited", report)
        self.assertIn("Notification history: 0 saved alerts", report)
        self.assertIn("Adapter errors:\n  none", report)


if __name__ == "__main__":
    unittest.main()
