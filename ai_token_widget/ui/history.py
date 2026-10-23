"""Dialog listing the notifications raised by the widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.notifications import NotificationHistory, NotificationRecord
from . import theme


class NotificationHistoryDialog(QDialog):
    """Read and clear the bounded, local notification history."""

    def __init__(
        self,
        history: NotificationHistory,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._history = history
        self.setObjectName("historyDialog")
        self.setWindowTitle("Notification history")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(380, 300)
        self.resize(420, 420)
        self.setStyleSheet(theme.STYLESHEET)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(8)

        title = QLabel("NOTIFICATION HISTORY")
        title.setObjectName("title")
        outer.addWidget(title)

        self._count = QLabel("")
        self._count.setObjectName("dialogHint")
        outer.addWidget(self._count)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._content = QWidget()
        self._content.setObjectName("historyContent")
        self._list = QVBoxLayout(self._content)
        self._list.setContentsMargins(0, 0, 4, 0)
        self._list.setSpacing(6)
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

        bottom = QHBoxLayout()
        self._clear = QPushButton("Clear history")
        self._clear.setObjectName("dialogLink")
        self._clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear.clicked.connect(self._clear_history)
        bottom.addWidget(self._clear)
        bottom.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

        self._rebuild()

    def _record_widget(self, record: NotificationRecord) -> QFrame:
        card = QFrame()
        card.setObjectName("historyItem")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(record.title)
        title.setObjectName("historyTitle")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        time = QLabel(record.created_at.astimezone().strftime("%d/%m %H:%M"))
        time.setObjectName("historyTime")
        time.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        head.addWidget(title, 1)
        head.addWidget(time)
        layout.addLayout(head)

        message = QLabel(record.message)
        message.setObjectName("historyMessage")
        message.setTextFormat(Qt.TextFormat.PlainText)
        message.setWordWrap(True)
        layout.addWidget(message)
        return card

    def _rebuild(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        records = self._history.records()
        if records:
            suffix = "" if len(records) == 1 else "s"
            self._count.setText(
                f"{len(records)} saved alert{suffix} · newest first"
            )
            for record in records:
                self._list.addWidget(self._record_widget(record))
        else:
            self._count.setText("No notifications yet")
            empty = QLabel(
                "Alerts appear here after they are shown in the tray."
            )
            empty.setObjectName("empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            self._list.addWidget(empty)
        self._list.addStretch(1)
        self._clear.setEnabled(bool(records))

    def _clear_history(self) -> None:
        self._history.clear()
        self._rebuild()


__all__ = ["NotificationHistoryDialog"]
