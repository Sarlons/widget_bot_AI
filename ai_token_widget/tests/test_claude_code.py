from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_token_widget.claude_statusline import SNAPSHOT_NAME
from ai_token_widget.core.model_limits import claude_context_window
from ai_token_widget.core.models import SessionState
from ai_token_widget.sources.claude_code import ClaudeAdapter

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _usage(input_tokens=0, output_tokens=0, cache_read=0, cache_write=0) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
    }


def _assistant(
    moment: datetime,
    usage: dict,
    model: str = "claude-opus-5-5",
    sidechain: bool = False,
    message_id: str | None = None,
    content: list[dict] | None = None,
) -> dict:
    message = {"role": "assistant", "model": model, "usage": usage}
    if message_id is not None:
        message["id"] = message_id
    if content is not None:
        message["content"] = content
    return {
        "type": "assistant",
        "sessionId": "will-be-overridden",
        "cwd": "C:\\work\\alpha",
        "version": "2.1.299",
        "isSidechain": sidechain,
        "timestamp": _iso(moment),
        "message": message,
    }


def _user(
    moment: datetime, session_id: str, content: str | list[dict] | None = None
) -> dict:
    message = {"role": "user"}
    if content is not None:
        message["content"] = content
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": "C:\\work\\alpha",
        "timestamp": _iso(moment),
        "message": message,
    }


class ClaudeAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "claude"
        self.projects = self.root / "projects" / "project"
        self.projects.mkdir(parents=True)
        self.data_dir = Path(self.temp.name) / "data"
        self.data_dir.mkdir()

        records = [
            _user(NOW - timedelta(seconds=30), "sess-run"),
            _assistant(NOW - timedelta(seconds=20), _usage(2, 198, 41904, 21587)),
            _assistant(
                NOW - timedelta(seconds=15),
                _usage(1, 1, 100, 0),
                sidechain=True,
            ),
            _assistant(NOW - timedelta(seconds=10), _usage(10, 20, 1000, 100)),
            _user(NOW - timedelta(seconds=5), "sess-run"),
        ]
        self._write("sess-run.jsonl", records, "sess-run")

        self._write(
            "sess-wait.jsonl",
            [
                _assistant(
                    NOW - timedelta(seconds=100),
                    _usage(5, 7, 200, 20),
                    model="claude-haiku-4-5",
                )
            ],
            "sess-wait",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, name: str, records: list[dict], session_id: str) -> None:
        for record in records:
            if record.get("sessionId") == "will-be-overridden":
                record["sessionId"] = session_id
        path = self.projects / name
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )

    def _adapter(self, **kwargs) -> ClaudeAdapter:
        return ClaudeAdapter(
            root=self.root,
            now=lambda: NOW,
            data_dir=self.data_dir,
            **kwargs,
        )

    def test_usage_and_context(self) -> None:
        sessions = {session.id: session for session in self._adapter().sessions()}
        self.assertEqual(set(sessions), {"sess-run", "sess-wait"})
        session = sessions["sess-run"]
        self.assertEqual(session.model, "claude-opus-5-5")
        self.assertEqual(session.project, "alpha")
        self.assertEqual(session.state, SessionState.RUNNING)
        self.assertEqual(session.usage_total.input_tokens, 13)
        self.assertEqual(session.usage_total.output_tokens, 219)
        self.assertEqual(session.usage_total.cache_read_tokens, 43_004)
        self.assertEqual(session.usage_total.cache_write_tokens, 21_687)
        self.assertEqual(session.context_used, 1_130)
        self.assertEqual(session.context_window, 1_000_000)
        self.assertTrue(session.context_estimated)
        self.assertIsNone(session.quota)

    def test_duplicate_message_ids_are_counted_once(self) -> None:
        self._write(
            "duplicates.jsonl",
            [
                _assistant(
                    NOW - timedelta(seconds=50),
                    _usage(10, 2, 100, 0),
                    message_id="msg-1",
                ),
                _assistant(
                    NOW - timedelta(seconds=49),
                    _usage(10, 2, 100, 0),
                    message_id="msg-1",
                ),
                _assistant(
                    NOW - timedelta(seconds=48),
                    _usage(12, 3, 120, 0),
                    message_id="msg-1",
                ),
                _assistant(
                    NOW - timedelta(seconds=47),
                    _usage(5, 1, 50, 0),
                    message_id="msg-2",
                ),
            ],
            "duplicates",
        )
        session = {s.id: s for s in self._adapter().sessions()}["duplicates"]
        self.assertEqual(session.usage_total.input_tokens, 17)
        self.assertEqual(session.usage_total.output_tokens, 4)
        self.assertEqual(session.usage_total.cache_read_tokens, 170)
        self.assertEqual(session.usage_last.input_tokens, 5)

    def test_recent_completed_turn_is_waiting(self) -> None:
        session = {s.id: s for s in self._adapter().sessions()}["sess-wait"]
        self.assertEqual(session.state, SessionState.WAITING)
        self.assertEqual(session.model, "claude-haiku-4-5")
        self.assertEqual(session.context_window, 200_000)

    def test_synthetic_messages_are_ignored(self) -> None:
        self._write(
            "synthetic.jsonl",
            [
                _assistant(
                    NOW - timedelta(seconds=50),
                    _usage(1_000_000, 1_000_000, 0, 0),
                    model="<synthetic>",
                ),
                _assistant(NOW - timedelta(seconds=40), _usage(10, 2, 0, 0)),
            ],
            "synthetic",
        )
        session = {s.id: s for s in self._adapter().sessions()}["synthetic"]
        self.assertEqual(session.usage_total.input_tokens, 10)
        self.assertEqual(session.usage_total.output_tokens, 2)
        self.assertEqual(session.model, "claude-opus-5-5")

    def test_prompt_api_and_modified_file_metrics(self) -> None:
        written = Path(self.temp.name) / "written.txt"
        edited = Path(self.temp.name) / "edited.txt"
        read_only = Path(self.temp.name) / "read.txt"
        self._write(
            "metrics.jsonl",
            [
                _user(
                    NOW - timedelta(seconds=60),
                    "metrics",
                    content="please change two files",
                ),
                _assistant(
                    NOW - timedelta(seconds=50),
                    _usage(10, 2, 0, 0),
                    message_id="msg-1",
                    content=[
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(written), "content": "x"},
                        },
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": str(edited), "old_string": "a"},
                        },
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": str(read_only)},
                        },
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "echo hi"},
                        },
                    ],
                ),
                # A duplicate content block for the same API response.
                _assistant(
                    NOW - timedelta(seconds=49),
                    _usage(10, 2, 0, 0),
                    message_id="msg-1",
                    content=[
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(written), "content": "x"},
                        }
                    ],
                ),
                _assistant(
                    NOW - timedelta(seconds=48),
                    _usage(5, 1, 0, 0),
                    message_id="msg-2",
                ),
                _user(
                    NOW - timedelta(seconds=47),
                    "metrics",
                    content=[{"type": "tool_result", "content": "ok"}],
                ),
                _user(
                    NOW - timedelta(seconds=46),
                    "metrics",
                    content=[{"type": "text", "text": "follow up"}],
                ),
            ],
            "metrics",
        )
        session = {s.id: s for s in self._adapter().sessions()}["metrics"]
        self.assertEqual(session.prompt_count, 2)
        self.assertEqual(
            session.prompt_chars,
            len("please change two files") + len("follow up"),
        )
        self.assertEqual(session.assistant_count, 2)
        self.assertEqual(
            set(session.modified_paths), {str(written), str(edited)}
        )
        self.assertEqual(session.model_kind, "multimodal")
        self.assertEqual(session.modified_file_count, 2)

    def test_statusline_quota_is_attached(self) -> None:
        snapshot = {
            "version": 1,
            "captured_at": _iso(NOW - timedelta(seconds=30)),
            "windows": [
                {
                    "label": "5h",
                    "used_percent": 42.0,
                    "resets_at": _iso(NOW + timedelta(hours=1)),
                },
                {
                    "label": "weekly",
                    "used_percent": 18.0,
                    "resets_at": _iso(NOW - timedelta(hours=1)),
                },
            ],
        }
        (self.data_dir / SNAPSHOT_NAME).write_text(
            json.dumps(snapshot), encoding="utf-8"
        )
        session = {s.id: s for s in self._adapter().sessions()}["sess-run"]
        self.assertIsNotNone(session.quota)
        self.assertEqual(session.quota.source, "claude-statusline")
        self.assertEqual(session.quota.windows[0].label, "5h")
        self.assertEqual(session.quota.windows[0].used_percent, 42.0)
        self.assertEqual(session.quota.windows[1].used_percent, 0.0)
        self.assertIsNone(session.quota.windows[1].resets_at)

    def test_stale_statusline_quota_is_ignored(self) -> None:
        snapshot = {
            "version": 1,
            "captured_at": _iso(NOW - timedelta(hours=25)),
            "windows": [{"label": "5h", "used_percent": 42.0}],
        }
        (self.data_dir / SNAPSHOT_NAME).write_text(
            json.dumps(snapshot), encoding="utf-8"
        )
        session = {s.id: s for s in self._adapter().sessions()}["sess-run"]
        self.assertIsNone(session.quota)

    def test_old_file_is_filtered_by_mtime(self) -> None:
        path = self.projects / "sess-wait.jsonl"
        old = (NOW - timedelta(days=2)).timestamp()
        os.utime(path, (old, old))
        self.assertEqual(
            {session.id for session in self._adapter().sessions()}, {"sess-run"}
        )

    def test_exhausted_quota_marks_rate_limited(self) -> None:
        snapshot = {
            "version": 1,
            "captured_at": _iso(NOW - timedelta(seconds=30)),
            "windows": [{"label": "5h", "used_percent": 100.0}],
        }
        (self.data_dir / SNAPSHOT_NAME).write_text(
            json.dumps(snapshot), encoding="utf-8"
        )
        session = {s.id: s for s in self._adapter().sessions()}["sess-run"]
        self.assertEqual(session.state, SessionState.RATE_LIMITED)

    def test_missing_projects_returns_empty(self) -> None:
        adapter = ClaudeAdapter(
            root=Path(self.temp.name) / "missing",
            now=lambda: NOW,
            data_dir=self.data_dir,
        )
        self.assertEqual(adapter.sessions(), [])


class ModelLimitsTest(unittest.TestCase):
    def test_known_families(self) -> None:
        self.assertEqual(claude_context_window("claude-opus-5-5"), (1_000_000, True))
        self.assertEqual(claude_context_window("claude-sonnet-5-5"), (1_000_000, True))
        self.assertEqual(claude_context_window("claude-haiku-5-5"), (1_000_000, True))
        self.assertEqual(claude_context_window("claude-fable-5-1"), (1_000_000, True))
        self.assertEqual(claude_context_window("claude-opus-4-8"), (1_000_000, True))
        self.assertEqual(claude_context_window("claude-sonnet-4-6"), (1_000_000, True))
        self.assertEqual(claude_context_window("claude-haiku-4-5"), (200_000, True))
        self.assertEqual(claude_context_window("unknown-model"), (None, False))
        self.assertEqual(claude_context_window("<synthetic>"), (None, False))


if __name__ == "__main__":
    unittest.main()
