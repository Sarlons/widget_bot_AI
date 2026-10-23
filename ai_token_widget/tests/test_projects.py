from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai_token_widget.core.load import (
    classify_model_kind,
    compute_load_score,
    load_index,
    load_label,
)
from ai_token_widget.core.models import Session, SessionState, Usage
from ai_token_widget.core.projects import aggregate_projects

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _session(
    session_id: str,
    cwd: str | None,
    *,
    project: str = "alpha",
    tokens: int = 1_000,
    prompt_count: int = 0,
    prompt_chars: int = 0,
    assistant_count: int = 0,
    context_used: int | None = None,
    context_window: int | None = None,
    modified_paths: tuple[str, ...] = (),
    model_kind: str = "general",
) -> Session:
    return Session(
        id=session_id,
        agent="codex",
        model="test-model",
        project=project,
        state=SessionState.IDLE,
        usage_total=Usage(reported_total=tokens),
        context_used=context_used,
        context_window=context_window,
        cwd=cwd,
        updated_at=NOW,
        prompt_count=prompt_count,
        prompt_chars=prompt_chars,
        assistant_count=assistant_count,
        model_kind=model_kind,
        modified_paths=modified_paths,
    )


class ProjectAggregationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.alpha = self.root / "alpha"
        self.other = self.root / "other"
        self.alpha.mkdir()
        self.other.mkdir()
        (self.alpha / "a.txt").write_bytes(b"abcde")
        (self.alpha / "b.txt").write_bytes(b"1234567")
        (self.other / "c.txt").write_bytes(b"xyz")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_groups_by_cwd_and_deduplicates_modified_files(self) -> None:
        sessions = [
            _session(
                "one",
                str(self.alpha),
                tokens=1_000,
                modified_paths=("a.txt", str(self.alpha / "b.txt")),
            ),
            _session(
                "two",
                str(self.alpha).upper(),
                tokens=2_000,
                modified_paths=("a.txt", str(self.alpha / "b.txt")),
            ),
            _session(
                "three",
                str(self.other),
                project="other",
                tokens=500,
                modified_paths=("c.txt",),
            ),
        ]
        projects = aggregate_projects(sessions)
        self.assertEqual(len(projects), 2)
        alpha = next(project for project in projects if project.name == "alpha")
        other = next(project for project in projects if project.name == "other")
        self.assertEqual(alpha.token_total, 3_000)
        self.assertEqual(alpha.session_count, 2)
        self.assertEqual(alpha.modified_files, 2)
        self.assertEqual(alpha.modified_bytes, 12)
        self.assertEqual(alpha.missing_files, 0)
        self.assertEqual(other.token_total, 500)
        self.assertEqual(other.modified_bytes, 3)

    def test_unknown_cwd_is_counted_but_not_sized_relative_to_widget(self) -> None:
        project = aggregate_projects(
            [
                _session(
                    "loose",
                    None,
                    project="loose",
                    modified_paths=("relative.txt",),
                )
            ]
        )[0]
        self.assertEqual(project.name, "loose")
        self.assertEqual(project.modified_files, 1)
        self.assertEqual(project.modified_bytes, 0)
        self.assertEqual(project.missing_files, 1)

    def test_deleted_file_is_counted_as_missing(self) -> None:
        missing = str(self.alpha / "gone.txt")
        project = aggregate_projects(
            [_session("one", str(self.alpha), modified_paths=(missing,))]
        )[0]
        self.assertEqual(project.modified_files, 1)
        self.assertEqual(project.modified_bytes, 0)
        self.assertEqual(project.missing_files, 1)

    def test_limit_keeps_highest_token_projects(self) -> None:
        sessions = [
            _session("one", str(self.alpha), tokens=100),
            _session("two", str(self.other), project="other", tokens=300),
            _session(
                "three",
                str(self.root / "third"),
                project="third",
                tokens=200,
            ),
        ]
        projects = aggregate_projects(sessions, limit=2)
        self.assertEqual([project.name for project in projects], ["other", "third"])

    def test_load_score_increases_with_prompts_api_and_context(self) -> None:
        light = aggregate_projects(
            [
                _session(
                    "light",
                    str(self.alpha),
                    prompt_count=1,
                    assistant_count=2,
                    context_used=100,
                    context_window=10_000,
                )
            ]
        )[0]
        heavy = aggregate_projects(
            [
                _session(
                    "heavy",
                    str(self.other),
                    project="other",
                    prompt_count=60,
                    assistant_count=600,
                    context_used=9_000,
                    context_window=10_000,
                    model_kind="reasoning",
                )
            ]
        )[0]
        self.assertGreater(heavy.load_score, light.load_score)
        self.assertEqual(light.load_index, 1)
        self.assertGreaterEqual(heavy.load_index, 4)
        self.assertEqual(heavy.load_label, load_label(heavy.load_index))

    def test_prompt_amplitude_increases_load(self) -> None:
        short = aggregate_projects(
            [
                _session(
                    "short",
                    str(self.alpha),
                    prompt_count=10,
                    prompt_chars=100,
                )
            ]
        )[0]
        long = aggregate_projects(
            [
                _session(
                    "long",
                    str(self.other),
                    project="other",
                    prompt_count=10,
                    prompt_chars=20_000,
                )
            ]
        )[0]
        self.assertGreater(long.load_score, short.load_score)


class LoadHeuristicTest(unittest.TestCase):
    def test_model_classification(self) -> None:
        self.assertEqual(classify_model_kind("gpt-5-codex"), "reasoning")
        self.assertEqual(classify_model_kind("gpt-4o"), "multimodal")
        self.assertEqual(classify_model_kind("claude-opus-5-5"), "multimodal")
        self.assertEqual(classify_model_kind("unknown"), "general")
        self.assertEqual(classify_model_kind("unknown", reasoning_tokens=1), "reasoning")

    def test_index_thresholds(self) -> None:
        self.assertEqual(load_index(0.0), 1)
        self.assertEqual(load_index(0.2), 2)
        self.assertEqual(load_index(0.4), 3)
        self.assertEqual(load_index(0.6), 4)
        self.assertEqual(load_index(0.8), 5)
        self.assertEqual(load_label(3), "MEDIUM")
        self.assertEqual(
            compute_load_score(
                prompt_count=0,
                assistant_count=0,
                context_pressure=0.0,
                model_factor=0.0,
            ),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
