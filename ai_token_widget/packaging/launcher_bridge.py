"""Console entry point for the packaged Claude Code bridge.

With no arguments it behaves exactly like ``claude_statusline.py``: it reads the
status-line JSON from stdin, writes the quota snapshot and prints a short status
line. With ``install``, ``uninstall`` or ``status`` it runs the opt-in bridge
CLI. This lets a single console executable serve both Claude Code and the user.
"""

from __future__ import annotations

import sys

from ai_token_widget import claude_bridge, claude_statusline

HELP = """AI Token Widget - Claude Code quota bridge

Usage:
  AITokenWidgetBridge.exe                     capture status-line JSON from stdin
  AITokenWidgetBridge.exe install [options]   install the opt-in bridge
  AITokenWidgetBridge.exe status [options]    show bridge and snapshot status
  AITokenWidgetBridge.exe uninstall [options] remove the bridge and restore settings
  AITokenWidgetBridge.exe --help              show this help

Install options:
  --settings PATH   override ~/.claude/settings.json
  --data-dir PATH   override the widget data directory
  --force           replace a different existing statusLine (previous value kept)
"""


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] == "--data-dir" or arguments[0].startswith(
        "--data-dir="
    ):
        return claude_statusline.main(arguments)
    if arguments[0] in {"install", "uninstall", "status", "-h", "--help"}:
        return claude_bridge.cli(arguments)
    print(HELP, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
