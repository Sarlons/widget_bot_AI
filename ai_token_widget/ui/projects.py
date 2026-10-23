"""Project-level summary rows for the widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.formatting import format_bytes, format_tokens
from ..core.projects import ProjectSummary
from . import theme

LOAD_COLORS = {
    1: theme.RUNNING,
    2: theme.RUNNING,
    3: theme.WAITING,
    4: "#fb923c",
    5: theme.RATE_LIMITED,
}


def _load_color(index: int) -> str:
    return LOAD_COLORS.get(max(1, min(5, index)), theme.FAINT)


def _load_bar(index: int) -> QWidget:
    bar = QWidget()
    bar.setFixedHeight(5)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    active = _load_color(index)
    for step in range(1, 6):
        segment = QFrame()
        segment.setFixedSize(15, 5)
        color = active if step <= index else "#262b35"
        segment.setStyleSheet(
            f"background: {color}; border: none; border-radius: 2px;"
        )
        layout.addWidget(segment)
    layout.addStretch(1)
    return bar


def _file_text(project: ProjectSummary) -> str:
    if project.modified_files == 0:
        return "no edits recorded"
    label = "file" if project.modified_files == 1 else "files"
    text = f"{project.modified_files} {label} · {format_bytes(project.modified_bytes)}"
    if project.missing_files:
        text += f" · {project.missing_files} missing"
    return text


class ProjectRow(QFrame):
    def __init__(self, project: ProjectSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.setObjectName("projectCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 7, 10, 7)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        name = QLabel(project.name)
        name.setObjectName("projectName")
        name.setWordWrap(True)
        name.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        tokens = QLabel(f"{format_tokens(project.token_total)} tok")
        tokens.setObjectName("projectTokens")
        tokens.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header.addWidget(name)
        header.addStretch(1)
        header.addWidget(tokens)
        outer.addLayout(header)

        agents = " · ".join(project.agent_labels)
        session_label = (
            "session" if project.session_count == 1 else "sessions"
        )
        bits = [agents, f"{project.session_count} {session_label}"]
        if project.running_count:
            bits.append(f"{project.running_count} running")
        bits.append(_file_text(project))
        meta = QLabel(" · ".join(bit for bit in bits if bit))
        meta.setObjectName("projectMeta")
        meta.setWordWrap(True)
        meta.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        outer.addWidget(meta)

        load_row = QHBoxLayout()
        load_row.setSpacing(6)
        label = QLabel("Load")
        label.setObjectName("rowLabel")
        load_row.addWidget(label)
        load_row.addWidget(_load_bar(project.load_index))
        load_text = QLabel(f"{project.load_index}/5 {project.load_label}")
        load_text.setObjectName("projectLoad")
        load_text.setStyleSheet(
            f"color: {_load_color(project.load_index)}; font-size: 9px; "
            "font-weight: 700; letter-spacing: 0.4px;"
        )
        load_row.addWidget(load_text)
        load_row.addStretch(1)
        outer.addLayout(load_row)

        self.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        project = self.project
        prompt_line = (
            f"{project.prompt_count} prompts · "
            f"{project.assistant_count} API turns"
        )
        average = project.average_prompt_chars
        if average is not None:
            prompt_line += f" · avg {average:.0f} chars"
        lines = [
            project.cwd or project.name,
            prompt_line,
            f"context pressure {project.context_pressure * 100:.0f}%",
            f"{project.modified_files} unique modified files",
        ]
        if project.modified_files:
            lines.append(
                f"{format_bytes(project.modified_bytes)} on disk"
                + (
                    f" · {project.missing_files} missing"
                    if project.missing_files
                    else ""
                )
            )
        return "\n".join(lines)


class ProjectSection(QWidget):
    def __init__(
        self,
        projects: tuple[ProjectSummary, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectSection")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(2, 2, 2, 0)
        header.setSpacing(6)
        title = QLabel("PROJECTS")
        title.setObjectName("projectSectionTitle")
        sessions = sum(project.session_count for project in projects)
        tokens = sum(project.token_total for project in projects)
        meta = QLabel(
            f"{len(projects)} folders · {sessions} sessions · "
            f"{format_tokens(tokens)} tokens"
        )
        meta.setObjectName("projectSectionMeta")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(meta)
        layout.addLayout(header)

        for project in projects:
            layout.addWidget(ProjectRow(project))


__all__ = ["ProjectRow", "ProjectSection"]
