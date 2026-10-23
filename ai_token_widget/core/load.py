"""Heuristics for the management-load index.

The index is deliberately transparent: it combines how often prompts are sent,
how much of the context window is in use, how many model/API turns happened and
whether the selected model is a heavier reasoning or multimodal family. It is a
UI hint, not a billing or quota metric.
"""

from __future__ import annotations

import math

MODEL_GENERAL = "general"
MODEL_REASONING = "reasoning"
MODEL_MULTIMODAL = "multimodal"

MODEL_WEIGHTS = {
    MODEL_GENERAL: 0.55,
    MODEL_MULTIMODAL: 0.82,
    MODEL_REASONING: 1.0,
}

_REASONING_MARKERS = (
    "reasoning",
    "thinking",
    "deepseek-r",
    "qwq",
    "magistral",
    "o1",
    "o3",
    "o4",
    "gpt-5",
    "gpt-6",
    "codex",
)
_MULTIMODAL_MARKERS = (
    "vision",
    "image",
    "multimodal",
    "omni",
    "gemini",
    "gpt-4o",
    "claude",
    "fable",
    "opus",
    "sonnet",
    "haiku",
)

LOAD_LABELS = {
    1: "LIGHT",
    2: "LIGHT",
    3: "MEDIUM",
    4: "HEAVY",
    5: "VERY HEAVY",
}


def classify_model_kind(model: str | None, reasoning_tokens: int = 0) -> str:
    """Return ``reasoning``, ``multimodal`` or ``general`` for a model id."""
    if reasoning_tokens > 0:
        return MODEL_REASONING
    text = (model or "").lower()
    if any(marker in text for marker in _REASONING_MARKERS):
        return MODEL_REASONING
    if any(marker in text for marker in _MULTIMODAL_MARKERS):
        return MODEL_MULTIMODAL
    return MODEL_GENERAL


def model_weight(kind: str | None) -> float:
    return MODEL_WEIGHTS.get(kind or MODEL_GENERAL, MODEL_WEIGHTS[MODEL_GENERAL])


def _log_scale(value: int, full_scale: int) -> float:
    """Map a non-negative count to 0..1 with diminishing returns."""
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(max(1, full_scale)))


def compute_load_score(
    *,
    prompt_count: int,
    assistant_count: int,
    context_pressure: float,
    model_factor: float,
    prompt_chars: int = 0,
) -> float:
    """Return a 0..1 management-load score.

    ``prompt_chars`` is the total character count of real user prompts, used
    only as an amplitude signal; prompt text is never retained. The prompt
    component combines frequency (65%) and average size (35%).
    ``context_pressure`` is the average fraction of the context window used by
    the sessions in the group. ``model_factor`` comes from :func:`model_weight`.
    """
    prompt_density = _log_scale(prompt_count, 60)
    average_chars = prompt_chars / prompt_count if prompt_count > 0 else 0
    prompt_amplitude = _log_scale(int(average_chars), 2_000)
    prompt_factor = 0.65 * prompt_density + 0.35 * prompt_amplitude
    api_density = _log_scale(assistant_count, 600)
    pressure = max(0.0, min(1.0, context_pressure))
    factor = max(0.0, min(1.0, model_factor))
    score = (
        0.35 * prompt_factor
        + 0.30 * pressure
        + 0.20 * api_density
        + 0.15 * factor
    )
    return max(0.0, min(1.0, score))


def load_index(score: float) -> int:
    """Map a 0..1 score to a 1..5 visual index."""
    if score < 0.20:
        return 1
    if score < 0.40:
        return 2
    if score < 0.60:
        return 3
    if score < 0.80:
        return 4
    return 5


def load_label(index: int) -> str:
    return LOAD_LABELS.get(max(1, min(5, index)), LOAD_LABELS[1])


__all__ = [
    "LOAD_LABELS",
    "MODEL_GENERAL",
    "MODEL_MULTIMODAL",
    "MODEL_REASONING",
    "classify_model_kind",
    "compute_load_score",
    "load_index",
    "load_label",
    "model_weight",
]
