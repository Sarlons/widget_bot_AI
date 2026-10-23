"""Single-instance guard for the widget.

A local socket server owns a per-user name. A second launch connects to it,
asks the running widget to come to the front and exits. A ``quit`` message asks
the running widget to shut down cleanly; the installer uses that before
replacing or removing files. The fallback is deliberately permissive: if the
socket cannot be created the widget still starts, because a broken guard must
not prevent the user from seeing usage.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger("ai_token_widget.single_instance")


def default_name() -> str:
    digest = hashlib.sha256(str(Path.home()).encode("utf-8")).hexdigest()[:12]
    return f"AITokenWidget-{digest}"


class SingleInstance(QObject):
    activated = Signal()
    quit_requested = Signal()

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name or default_name()
        self._server: QLocalServer | None = None
        self._probe: QLocalSocket | None = None
        self._owns_server = False

    @property
    def name(self) -> str:
        return self._name

    def acquire(self) -> bool:
        probe = QLocalSocket(self)
        probe.connectToServer(self._name)
        if probe.waitForConnected(250):
            probe.disconnectFromServer()
            self._probe = probe
            return False
        probe.deleteLater()

        # Remove a stale endpoint left by a crash; a live process still owns
        # the pipe, so this is a no-op in the normal case.
        QLocalServer.removeServer(self._name)

        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._name):
            retry = QLocalSocket(self)
            retry.connectToServer(self._name)
            if retry.waitForConnected(250):
                retry.disconnectFromServer()
                self._probe = retry
                return False
            retry.deleteLater()
            logger.warning(
                "single-instance socket unavailable (%s); continuing",
                server.errorString(),
            )
            return True

        server.newConnection.connect(self._accept)
        self._server = server
        self._owns_server = True
        return True

    def _accept(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            connection.disconnected.connect(connection.deleteLater)
            if connection.bytesAvailable() == 0:
                # Give the second process a moment to send its command.
                connection.waitForReadyRead(100)
            payload = bytes(connection.readAll()).strip().lower()
            if payload == b"quit":
                self.quit_requested.emit()
            else:
                self.activated.emit()
            connection.disconnectFromServer()
            connection.deleteLater()

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server.deleteLater()
            self._server = None
        if self._owns_server:
            QLocalServer.removeServer(self._name)
            self._owns_server = False
        if self._probe is not None:
            self._probe.deleteLater()
            self._probe = None


def request_quit(name: str | None = None, timeout_ms: int = 3000) -> bool:
    """Ask a running widget to quit cleanly.

    Returns ``False`` when no instance is listening. The loop processes events
    so the same code also works when client and server share a process (tests).
    """
    socket = QLocalSocket()
    socket.connectToServer(name or default_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"quit\n")
    socket.flush()
    deadline = time.monotonic() + timeout_ms / 1000
    unconnected = QLocalSocket.LocalSocketState.UnconnectedState
    while socket.state() != unconnected:
        if time.monotonic() >= deadline:
            socket.abort()
            return False
        QCoreApplication.processEvents()
        socket.waitForDisconnected(50)
    return True


__all__ = ["SingleInstance", "default_name", "request_quit"]

