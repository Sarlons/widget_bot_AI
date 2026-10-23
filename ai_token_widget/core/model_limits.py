"""Context-window metadata for providers that do not expose it locally.

Codex reports the context window in its rollout logs; OpenCode ships a local
models.dev catalog. Claude Code transcripts do not, so the window is estimated
from the model family and the UI labels it as such.
"""

from __future__ import annotations


def claude_context_window(model: str | None) -> tuple[int | None, bool]:
    """Return ``(window, estimated)`` for a Claude model name.

    Claude Code writes the model id only, not the effective limit. The current
    Claude 5.x families (Fable, Opus, Sonnet and Haiku) use a 1M window, as do
    Opus 4.6-4.8 and Sonnet 4.6. Older families such as Haiku 4.5 fall back to
    the standard 200K window.
    """
    if not model or model == "<synthetic>":
        return None, False
    lowered = model.lower()
    if "1m" in lowered or any(
        family in lowered
        for family in (
            "fable-5",
            "mythos-5",
            "opus-5",
            "sonnet-5",
            "haiku-5",
            "opus-4-6",
            "opus-4-7",
            "opus-4-8",
            "sonnet-4-6",
        )
    ):
        return 1_000_000, True
    if "claude" in lowered:
        return 200_000, True
    return None, False
