"""Provider group header for the session list."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from ..core.grouping import SessionGroup
from . import theme


class GroupHeader(QFrame):
    """A clickable header that collapses or expands one provider group."""

    toggled = Signal(str)

    def __init__(
        self,
        group: SessionGroup,
        collapsed: bool = False,
        attention_count: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.agent = group.agent
        flagged = group.issue_count if attention_count is None else attention_count
        self.setObjectName("groupHeader")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(
            f"Expand {group.label}" if collapsed else f"Collapse {group.label}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 5, 2, 3)
        layout.setSpacing(6)

        chevron = QLabel("▸" if collapsed else "▾")
        chevron.setObjectName("groupChevron")
        accent = theme.AGENT_ACCENTS.get(group.agent, theme.TEXT)
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background: {accent}; border-radius: 3px;")
        title = QLabel(group.label)
        title.setObjectName("groupTitle")
        title.setStyleSheet(f"color: {accent};")

        count = len(group.sessions)
        bits = [f"{count} session" if count == 1 else f"{count} sessions"]
        if group.running_count:
            bits.append(f"{group.running_count} running")
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("groupMeta")

        layout.addWidget(chevron)
        layout.addWidget(dot)
        layout.addWidget(title)
        layout.addWidget(meta)
        layout.addStretch(1)

        if flagged:
            issue = QLabel(f"{flagged} flagged")
            issue.setObjectName("groupIssue")
            issue.setStyleSheet(f"color: {theme.RATE_LIMITED};")
            layout.addWidget(issue)

        for child in self.findChildren(QWidget):
            child.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self._emit_toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def _emit_toggle(self) -> None:
        self.toggled.emit(self.agent)


__all__ = ["GroupHeader"]
