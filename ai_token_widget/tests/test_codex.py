from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_token_widget.core.models import (
    Confidence,
    Quota,
    QuotaWindow,
    SessionState,
)
from ai_token_widget.sources.codex import (
    CodexAdapter,
    RolloutData,
    apply_window_rollover,
    normalize_windows_path,
    select_shared_quota,
)

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _token_count(reset_offset: int = 3600) -> dict:
    reset = int((NOW + timedelta(seconds=reset_offset)).timestamp())
    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 2000,
                    "cache_write_input_tokens": 300,
                    "output_tokens": 400,
                    "reasoning_output_tokens": 50,
                    "total_tokens": 3750,
                },
                "last_token_usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 2000,
                    "output_tokens": 500,
                    "total_tokens": 3500,
                },
                "model_context_window": 10_000,
            },
            "rate_limits": {
                "primary": {
                    "used_percent": 40.0,
                    "window_minutes": 300,
                    "resets_at": reset,
                },
                "secondary": {
                    "used_percent": 20.0,
                    "window_minutes": 10080,
                    "resets_at": reset + 86400,
                },
                "credits": {"has_credits": True, "unlimited": False, "balance": "12.5"},
                "plan_type": "pro",
            },
        },
    }


class CodexAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "sessions" / "2026" / "10" / "22").mkdir(parents=True)
        self.rollout = self.root / "sessions" / "2026" / "10" / "22" / "rollout-test.jsonl"
        records = [
            {
                "type": "session_meta",
                "payload": {"cwd": "\\\\?\\C:\\work\\alpha", "cli_version": "test"},
            },
            {"type": "turn_context", "payload": {"model": "gpt-test"}},
            _token_count(),
        ]
        self.rollout.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        self._write_db(
            id="thread-1",
            updated_at=int(NOW.timestamp()) - 30,
            created_at=int(NOW.timestamp()) - 3600,
            model="gpt-test",
            cwd="\\\\?\\C:\\work\\alpha",
            tokens_used=99_000,
            rollout_path=str(self.rollout),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_db(self, **values) -> None:
        path = self.root / "state_5.sqlite"
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS threads ("
                "id TEXT, updated_at INTEGER, created_at INTEGER, model TEXT, "
                "cwd TEXT, tokens_used INTEGER, source TEXT, rollout_path TEXT)"
            )
            connection.execute("DELETE FROM threads")
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    values["id"],
                    values["updated_at"],
                    values["created_at"],
                    values["model"],
                    values["cwd"],
                    values["tokens_used"],
                    "vscode",
                    values["rollout_path"],
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _adapter(self, **kwargs) -> CodexAdapter:
        return CodexAdapter(root=self.root, now=lambda: NOW, **kwargs)

    def _write_rollout(self, record: dict, path: Path | None = None) -> Path:
        target = path or self.rollout
        records = [
            {
                "type": "session_meta",
                "payload": {"cwd": "\\\\?\\C:\\work\\alpha", "cli_version": "test"},
            },
            {"type": "turn_context", "payload": {"model": "gpt-test"}},
            record,
        ]
        target.write_text(
            "\n".join(json.dumps(item) for item in records) + "\n",
            encoding="utf-8",
        )
        return target

    def _insert_thread(
        self, thread_id: str, updated_at: int, rollout_path: Path
    ) -> None:
        connection = sqlite3.connect(self.root / "state_5.sqlite")
        try:
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    updated_at,
                    int((NOW - timedelta(hours=1)).timestamp()),
                    "gpt-test",
                    "C:\\work\\alpha",
                    99_000,
                    "vscode",
                    str(rollout_path),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def test_session_from_sqlite_and_rollout(self) -> None:
        sessions = self._adapter().sessions()
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        self.assertEqual(session.agent, "codex")
        self.assertEqual(session.id, "thread-1")
        self.assertEqual(session.model, "gpt-test")
        self.assertEqual(session.project, "alpha")
        self.assertEqual(session.cwd, "C:\\work\\alpha")
        self.assertEqual(session.state, SessionState.RUNNING)
        self.assertEqual(session.context_window, 10_000)
        self.assertEqual(session.context_used, 3_500)
        self.assertEqual(session.context_remaining, 6_500)
        self.assertEqual(session.usage_total.total, 3_750)
        # Codex input_tokens already include cached_input_tokens.
        self.assertEqual(session.usage_total.billed_input, 1_000)
        self.assertIsNotNone(session.quota)
        self.assertEqual(session.quota.confidence, Confidence.EXACT)
        self.assertEqual([window.label for window in session.quota.windows], ["5h", "weekly"])
        self.assertEqual(session.quota.windows[0].used_percent, 40.0)
        self.assertEqual(session.quota.credits_usd, 12.5)
        self.assertEqual(session.quota.plan, "pro")

    def test_rollout_tail_uses_latest_token_count(self) -> None:
        later = _token_count()
        later["payload"]["info"]["last_token_usage"]["total_tokens"] = 4_000
        later["payload"]["info"]["model_context_window"] = 20_000
        with self.rollout.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(later) + "\n")
        session = self._adapter().sessions()[0]
        self.assertEqual(session.context_window, 20_000)
        self.assertEqual(session.context_used, 4_000)

    def test_shared_quota_uses_freshest_capture(self) -> None:
        older = _token_count()
        older["timestamp"] = (NOW - timedelta(minutes=10)).isoformat().replace(
            "+00:00", "Z"
        )
        older["payload"]["rate_limits"]["primary"]["used_percent"] = 40.0
        older["payload"]["rate_limits"]["secondary"]["used_percent"] = 20.0
        self._write_rollout(older)

        second = self.root / "sessions" / "2026" / "10" / "22" / "rollout-two.jsonl"
        newer = _token_count()
        newer["timestamp"] = (NOW - timedelta(minutes=1)).isoformat().replace(
            "+00:00", "Z"
        )
        newer["payload"]["rate_limits"]["primary"]["used_percent"] = 90.0
        newer["payload"]["rate_limits"]["secondary"]["used_percent"] = 50.0
        self._write_rollout(newer, second)
        self._insert_thread("thread-2", int(NOW.timestamp()) - 10, second)

        sessions = self._adapter().sessions()
        self.assertEqual(len(sessions), 2)
        for session in sessions:
            self.assertIsNotNone(session.quota)
            self.assertEqual(session.quota.windows[0].used_percent, 90.0)
            self.assertEqual(session.quota.windows[1].used_percent, 50.0)

    def test_disabled_credits_do_not_create_a_zero_credit_quota(self) -> None:
        record = _token_count()
        record["payload"]["rate_limits"] = {
            "credits": {"has_credits": False, "unlimited": False, "balance": "0"},
            "plan_type": "plus",
        }
        self._write_rollout(record)
        session = self._adapter().sessions()[0]
        self.assertIsNone(session.quota)

    def test_select_shared_quota_skips_empty_candidates(self) -> None:
        newer = Quota(
            confidence=Confidence.EXACT,
            windows=(QuotaWindow(label="5h", used_percent=90.0),),
            captured_at=NOW - timedelta(minutes=1),
        )
        older = Quota(
            confidence=Confidence.EXACT,
            windows=(QuotaWindow(label="5h", used_percent=40.0),),
            captured_at=NOW - timedelta(minutes=10),
        )
        selected = select_shared_quota(
            [
                RolloutData(),
                RolloutData(quota=older),
                RolloutData(quota=newer),
            ]
        )
        self.assertIs(selected, newer)

    def test_select_shared_quota_prefers_windows_over_newer_credits(self) -> None:
        with_windows = Quota(
            confidence=Confidence.EXACT,
            windows=(QuotaWindow(label="5h", used_percent=40.0),),
            captured_at=NOW - timedelta(minutes=10),
        )
        credits_only = Quota(
            confidence=Confidence.EXACT,
            windows=(),
            credits_usd=5.0,
            captured_at=NOW - timedelta(minutes=1),
        )
        selected = select_shared_quota(
            [RolloutData(quota=credits_only), RolloutData(quota=with_windows)]
        )
        self.assertIs(selected, with_windows)

    def test_stale_thread_is_filtered(self) -> None:
        self._write_db(
            id="old",
            updated_at=int((NOW - timedelta(days=2)).timestamp()),
            created_at=int((NOW - timedelta(days=3)).timestamp()),
            model="gpt-test",
            cwd="C:\\work\\alpha",
            tokens_used=1,
            rollout_path=str(self.rollout),
        )
        self.assertEqual(self._adapter(max_age_hours=24).sessions(), [])

    def test_no_state_database_returns_empty(self) -> None:
        (self.root / "state_5.sqlite").unlink()
        self.assertEqual(self._adapter().sessions(), [])

    def test_quota_rollover_resets_expired_window(self) -> None:
        session = self._adapter().sessions()[0]
        rolled = apply_window_rollover(
            session.quota, NOW + timedelta(seconds=7200)
        )
        self.assertIsNotNone(rolled)
        self.assertEqual(rolled.windows[0].used_percent, 0.0)
        self.assertIsNone(rolled.windows[0].resets_at)
        self.assertEqual(rolled.windows[1].used_percent, 20.0)

    def test_normalize_windows_path(self) -> None:
        self.assertEqual(normalize_windows_path("\\\\?\\C:\\work\\alpha"), "C:\\work\\alpha")
        self.assertIsNone(normalize_windows_path(""))


if __name__ == "__main__":
    unittest.main()
