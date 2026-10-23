"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .core.config import Config
from .core.logging_setup import configure_logging
from .core.registry import Registry
from .single_instance import SingleInstance, request_quit
from .sources.claude_code import ClaudeAdapter
from .sources.codex import CodexAdapter
from .sources.opencode import OpenCodeAdapter
from .ui.window import WidgetWindow


def build_registry(config: Config) -> Registry:
    common = {
        "max_age_hours": config.max_session_age_hours,
        "running_window_seconds": config.running_window_seconds,
    }
    return Registry(
        [
            ClaudeAdapter(**common),
            CodexAdapter(**common),
            OpenCodeAdapter(**common),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else list(sys.argv)
    if "--quit" in arguments[1:]:
        application = QApplication(arguments[:1] or ["AITokenWidget"])
        application.setApplicationName("AI Token Widget")
        return 0 if request_quit() else 1

    logger = configure_logging()
    logger.info("Starting AI Token Widget")
    application = QApplication(arguments)
    application.setApplicationName("AI Token Widget")
    application.setOrganizationName("AITokenWidget")
    application.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if not instance.acquire():
        logger.info("Another widget instance is already running")
        instance.close()
        return 0

    config = Config.load()
    registry = build_registry(config)
    window: WidgetWindow | None = None
    try:
        window = WidgetWindow(registry, config)
        instance.activated.connect(window.reveal)
        instance.quit_requested.connect(window.quit)
        window.show()
        exit_code = application.exec()
    finally:
        stopped = True
        if window is not None:
            stopped = window.shutdown()
        instance.close()
        if stopped:
            registry.close()
        logger.info("Stopped AI Token Widget")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
