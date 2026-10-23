"""Process discovery.

Image names alone are not enough: ``claude.exe`` is usually the Claude desktop
app, and most agents run inside ``node.exe``. We match:

* known agent executables (excluding the desktop app), and
* node/bun processes whose command line references an agent package.

Command lines are inspected in memory only. They are never logged, because
some users pass credentials on the command line.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # psutil is a runtime dependency; keep imports testable without it.
    import psutil
except ImportError:  # pragma: no cover - exercised only on a broken install
    psutil = None  # type: ignore[assignment]

AGENT_LABELS = {
    "claude_code": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
}


@dataclass(frozen=True)
class AgentProcess:
    pid: int
    agent: str
    cwd: str | None


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    text = value
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return os.path.normcase(os.path.normpath(text))


def _agent_for(name: str, exe: str | None, cmdline: list[str]) -> str | None:
    lowered = name.lower()
    exe_lower = (exe or "").lower()

    if lowered == "codex.exe":
        return "codex"
    if lowered == "opencode.exe":
        return "opencode"
    if lowered == "claude.exe":
        # The desktop app ships under WindowsApps; the CLI does not.
        return None if "windowsapps" in exe_lower else "claude_code"

    if lowered in ("node.exe", "bun.exe", "deno.exe"):
        joined = " ".join(cmdline).lower()
        if "@anthropic-ai/claude-code" in joined or "claude-code" in joined:
            return "claude_code"
        if "@openai/codex" in joined or "codex-cli" in joined:
            return "codex"
        if "@opencode" in joined or "opencode-ai" in joined:
            return "opencode"
    return None


def scan_processes() -> list[AgentProcess]:
    if psutil is None:
        return []
    found: list[AgentProcess] = []
    for process in psutil.process_iter(
        ["pid", "name", "exe", "cmdline", "cwd"], ad_value=None
    ):
        try:
            info = process.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        name = info.get("name") or ""
        exe = info.get("exe")
        cmdline = info.get("cmdline") or []
        agent = _agent_for(name, exe, cmdline)
        if agent is None:
            continue
        try:
            cwd = process.cwd()
        except (psutil.Error, OSError):
            cwd = info.get("cwd")
        found.append(AgentProcess(pid=process.pid, agent=agent, cwd=_normalize(cwd)))
    return found
