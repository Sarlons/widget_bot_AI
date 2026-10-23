from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_token_widget.core.models import SessionState
from ai_token_widget.sources.opencode import OpenCodeAdapter

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
MODEL = json.dumps({"id": "deepseek-test", "providerID": "opencode"})


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _catalog() -> str:
    body = {
        "opencode": {
            "models": {
                "deepseek-test": {
                    "limit": {"context": 200_000, "output": 32_000},
                }
            }
        }
    }
    return json.dumps({"body": json.dumps(body)})


class OpenCodeAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "opencode.db"
        connection = sqlite3.connect(self.db)
        try:
            connection.executescript(
                """
                CREATE TABLE session_v2 (
                    id TEXT, project_id TEXT, directory TEXT, version TEXT,
                    cost REAL, tokens_input INTEGER, tokens_output INTEGER,
                    tokens_reasoning INTEGER, tokens_cache_read INTEGER,
                    tokens_cache_write INTEGER, agent TEXT, model TEXT,
                    time_created INTEGER, time_updated INTEGER,
                    time_archived INTEGER, parent_id TEXT
                );
                CREATE TABLE session_message (
                    id TEXT, session_id TEXT, type TEXT, seq INTEGER,
                    time_created INTEGER, time_updated INTEGER, data TEXT
                );
                CREATE TABLE project (id TEXT, worktree TEXT, name TEXT);
                CREATE TABLE kv (key TEXT, value TEXT, time_created INTEGER, time_updated INTEGER);
                """
            )
            connection.execute(
                "INSERT INTO project VALUES (?, ?, ?)",
                ("p1", "C:/work/alpha", "alpha"),
            )
            connection.execute(
                "INSERT INTO kv VALUES (?, ?, ?, ?)",
                ("models-dev:catalog", _catalog(), _ms(NOW), _ms(NOW)),
            )
            for session_id, last_completed in (
                ("ses_run", False),
                ("ses_wait", True),
            ):
                connection.execute(
                    "INSERT INTO session_v2 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        "p1",
                        "C:/work/alpha",
                        "2.1.3",
                        0.0,
                        1_000,
                        200,
                        50,
                        500,
                        10,
                        "build",
                        MODEL,
                        _ms(NOW - timedelta(minutes=5)),
                        _ms(NOW - timedelta(seconds=5)),
                        None,
                        None,
                    ),
                )
                connection.execute(
                    "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"{session_id}-user",
                        session_id,
                        "user",
                        1,
                        _ms(NOW - timedelta(seconds=10)),
                        None,
                        json.dumps(
                            {
                                "role": "user",
                                "text": "hello",
                                "time": {"created": _ms(NOW - timedelta(seconds=10))},
                            }
                        ),
                    ),
                )
                assistant = {
                    "role": "assistant",
                    "model": {"id": "deepseek-test", "providerID": "opencode"},
                    "tokens": {
                        "input": 500,
                        "output": 100,
                        "reasoning": 50,
                        "cache": {"read": 1000, "write": 0},
                    },
                    "time": {
                        "created": _ms(NOW - timedelta(seconds=6)),
                        "completed": _ms(NOW - timedelta(seconds=5)) if last_completed else None,
                    },
                }
                connection.execute(
                    "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"{session_id}-assistant",
                        session_id,
                        "assistant",
                        2,
                        _ms(NOW - timedelta(seconds=6)),
                        _ms(NOW - timedelta(seconds=5)),
                        json.dumps(assistant),
                    ),
                )
            # A streaming assistant placeholder can appear after the last
            # completed message and carries no token block.
            connection.execute(
                "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "ses_run-streaming",
                    "ses_run",
                    "assistant",
                    3,
                    _ms(NOW - timedelta(seconds=1)),
                    None,
                    json.dumps(
                        {
                            "role": "assistant",
                            "model": {"id": "deepseek-test", "providerID": "opencode"},
                            "time": {"created": _ms(NOW - timedelta(seconds=1))},
                        }
                    ),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _adapter(self, **kwargs) -> OpenCodeAdapter:
        return OpenCodeAdapter(root=self.root, now=lambda: NOW, **kwargs)

    def test_running_and_waiting_sessions(self) -> None:
        sessions = {session.id: session for session in self._adapter().sessions()}
        self.assertEqual(set(sessions), {"ses_run", "ses_wait"})
        self.assertEqual(sessions["ses_run"].state, SessionState.RUNNING)
        self.assertEqual(sessions["ses_wait"].state, SessionState.WAITING)

    def test_usage_context_and_model(self) -> None:
        session = {s.id: s for s in self._adapter().sessions()}["ses_run"]
        self.assertEqual(session.model, "deepseek-test")
        self.assertEqual(session.source, "opencode")
        self.assertEqual(session.project, "alpha")
        self.assertEqual(session.context_window, 200_000)
        self.assertFalse(session.context_estimated)
        # latest assistant message: 500 input + 100 output + 50 reasoning + 1000 cache read
        self.assertEqual(session.context_used, 1_650)
        self.assertEqual(session.usage_last.total, 1_650)
        self.assertEqual(session.usage_total.input_tokens, 1_000)
        self.assertEqual(session.usage_total.output_tokens, 200)
        self.assertEqual(session.usage_total.cache_read_tokens, 500)
        self.assertEqual(session.cost_usd, 0.0)

    def test_prompt_api_and_modified_file_metrics(self) -> None:
        edited = str(self.root / "edited.py")
        written = str(self.root / "written.py")
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "ses_run-user-2",
                    "ses_run",
                    "user",
                    4,
                    _ms(NOW - timedelta(seconds=4)),
                    None,
                    json.dumps({"role": "user", "text": "follow up"}),
                ),
            )
            assistant = {
                "role": "assistant",
                "model": {"id": "deepseek-test", "providerID": "opencode"},
                "content": [
                    {
                        "type": "tool",
                        "name": "edit",
                        "executed": False,
                        "state": {
                            "status": "completed",
                            "input": {"path": edited, "oldString": "a"},
                        },
                    },
                    {
                        "type": "tool",
                        "name": "write",
                        "executed": False,
                        "state": {
                            "status": "completed",
                            "input": {"path": written, "content": "x"},
                        },
                    },
                    {
                        "type": "tool",
                        "name": "read",
                        "executed": False,
                        "state": {
                            "status": "completed",
                            "input": {"path": str(self.root / "read.py")},
                        },
                    },
                    {
                        "type": "tool",
                        "name": "shell",
                        "executed": False,
                        "state": {
                            "status": "completed",
                            "input": {"command": "echo hi"},
                        },
                    },
                ],
            }
            connection.execute(
                "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "ses_run-assistant-2",
                    "ses_run",
                    "assistant",
                    5,
                    _ms(NOW - timedelta(seconds=3)),
                    _ms(NOW - timedelta(seconds=3)),
                    json.dumps(assistant),
                ),
            )
            connection.commit()
        finally:
            connection.close()

        session = {s.id: s for s in self._adapter().sessions()}["ses_run"]
        self.assertEqual(session.prompt_count, 2)
        self.assertEqual(session.prompt_chars, len("hello") + len("follow up"))
        self.assertEqual(session.assistant_count, 3)
        self.assertEqual(set(session.modified_paths), {edited, written})
        self.assertEqual(session.model_kind, "reasoning")

    def test_archived_sessions_are_skipped(self) -> None:
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE session_v2 SET time_archived = ? WHERE id = 'ses_wait'",
                (_ms(NOW),),
            )
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(
            [session.id for session in self._adapter().sessions()], ["ses_run"]
        )

    def test_session_table_fallback(self) -> None:
        fallback = Path(self.temp.name) / "fallback"
        fallback.mkdir()
        connection = sqlite3.connect(fallback / "opencode.db")
        try:
            connection.executescript(
                """
                CREATE TABLE session (
                    id TEXT, project_id TEXT, directory TEXT, cost REAL,
                    tokens_input INTEGER, tokens_output INTEGER,
                    tokens_reasoning INTEGER, tokens_cache_read INTEGER,
                    tokens_cache_write INTEGER, model TEXT,
                    time_created INTEGER, time_updated INTEGER
                );
                """
            )
            connection.execute(
                "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "old",
                    "p1",
                    "C:/work/alpha",
                    0.0,
                    10,
                    2,
                    0,
                    0,
                    0,
                    MODEL,
                    _ms(NOW - timedelta(minutes=3)),
                    _ms(NOW - timedelta(minutes=2)),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        adapter = OpenCodeAdapter(root=fallback, now=lambda: NOW)
        sessions = adapter.sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].state, SessionState.IDLE)
        self.assertIsNone(sessions[0].context_window)

    def test_missing_database_returns_empty(self) -> None:
        (self.root / "opencode.db").unlink()
        self.assertEqual(self._adapter().sessions(), [])


if __name__ == "__main__":
    unittest.main()
