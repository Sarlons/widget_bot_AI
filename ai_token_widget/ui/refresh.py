"""Background snapshot refresh.

Adapters read SQLite databases and transcript files. Running them on the GUI
thread can freeze the window while a large transcript is parsed, so the window
owns a worker thread and only renders completed snapshots.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from ..core.registry import Registry

logger = logging.getLogger("ai_token_widget.refresh")


class RefreshWorker(QObject):
    snapshot_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, registry: Registry) -> None:
        super().__init__()
        self._registry = registry

    @Slot()
    def refresh(self) -> None:
        try:
            snapshot = self._registry.refresh()
        except Exception as exc:  # the UI must keep the previous snapshot
            logger.exception("Snapshot refresh failed")
            self.failed.emit(type(exc).__name__)
            return
        self.snapshot_ready.emit(snapshot)


__all__ = ["RefreshWorker"]
