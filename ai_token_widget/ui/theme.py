"""Colors and stylesheet for the floating widget."""

from __future__ import annotations

BACKGROUND = "#14161b"
SURFACE = "#1c1f27"
SURFACE_HOVER = "#22262f"
BORDER = "#2b303b"
TEXT = "#e6e8ee"
MUTED = "#8b93a7"
FAINT = "#5d6578"

RUNNING = "#4ade80"
WAITING = "#fbbf24"
RATE_LIMITED = "#f87171"
IDLE = "#6b7280"
ERROR = "#f87171"

AGENT_ACCENTS = {
    "claude_code": "#d97757",
    "codex": "#10a37f",
    "opencode": "#7c9cff",
}

STATE_COLORS = {
    "running": RUNNING,
    "waiting": WAITING,
    "rate_limited": RATE_LIMITED,
    "idle": IDLE,
    "error": ERROR,
}

STATE_LABELS = {
    "running": "RUNNING",
    "waiting": "WAITING",
    "rate_limited": "LIMITED",
    "idle": "IDLE",
    "error": "ERROR",
}

STYLESHEET = f"""
* {{
    font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
    color: {TEXT};
}}
QWidget#root {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QLabel#title {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.4px;
    color: {TEXT};
}}
QLabel#summary {{
    font-size: 11px;
    color: {MUTED};
}}
QLabel#footer {{
    font-size: 10px;
    color: {FAINT};
}}
QLabel#agent {{
    font-size: 13px;
    font-weight: 600;
}}
QLabel#project {{
    font-size: 11px;
    color: {MUTED};
}}
QLabel#model {{
    font-size: 10px;
    color: {FAINT};
}}
QLabel#state {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}
QLabel#rowLabel {{
    font-size: 10px;
    color: {MUTED};
}}
QLabel#rowValue {{
    font-size: 10px;
    color: {MUTED};
}}
QLabel#tokens {{
    font-size: 10px;
    color: {FAINT};
}}
QLabel#empty {{
    font-size: 12px;
    color: {MUTED};
    padding: 24px 8px;
}}
QFrame#filterBar {{
    background: transparent;
}}
QLineEdit#filterSearch {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 10px;
    color: {TEXT};
    selection-background-color: #334155;
    selection-color: {TEXT};
}}
QLineEdit#filterSearch:focus {{
    border: 1px solid #3b465c;
}}
QLineEdit#filterSearch QToolButton {{
    background: transparent;
    border: none;
    padding: 0;
}}
QPushButton#filterChip {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: {MUTED};
    font-size: 9px;
    font-weight: 600;
    padding: 4px 5px;
}}
QPushButton#filterChip:hover {{
    background: {SURFACE_HOVER};
    color: {TEXT};
}}
QPushButton#filterChip:checked {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    color: {TEXT};
}}
QFrame#groupHeader {{
    background: transparent;
    border: none;
    border-radius: 8px;
}}
QFrame#groupHeader:hover {{
    background: {SURFACE};
}}
QLabel#groupChevron {{
    color: {FAINT};
    font-size: 10px;
}}
QLabel#groupTitle {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}
QLabel#groupMeta {{
    font-size: 9px;
    color: {FAINT};
}}
QLabel#groupIssue {{
    font-size: 9px;
    font-weight: 600;
}}
QPushButton#filterClear {{
    background: transparent;
    border: none;
    color: {MUTED};
    font-size: 10px;
    text-decoration: underline;
    padding: 4px;
}}
QPushButton#filterClear:hover {{
    color: {TEXT};
}}
QFrame#sessionCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#headerBar {{
    background: transparent;
}}
QPushButton#iconButton {{
    background: transparent;
    border: none;
    color: {MUTED};
    font-size: 14px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 6px;
}}
QPushButton#iconButton:hover {{
    background: {SURFACE_HOVER};
    color: {TEXT};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #343b49;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QProgressBar {{
    background: #262b35;
    border: none;
    border-radius: 3px;
    height: 5px;
}}
QDialog#settingsDialog {{
    background: {BACKGROUND};
}}
QWidget#settingsContent {{
    background: transparent;
}}
QDialog#historyDialog {{
    background: {BACKGROUND};
}}
QWidget#historyContent {{
    background: transparent;
}}
QFrame#historyItem {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#historyTitle {{
    font-size: 11px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#historyTime {{
    font-size: 9px;
    color: {FAINT};
}}
QLabel#historyMessage {{
    font-size: 10px;
    color: {MUTED};
}}
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 10px;
    padding: 10px 8px 8px 8px;
    font-size: 11px;
    color: {MUTED};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT};
}}
QCheckBox {{
    font-size: 11px;
    color: {TEXT};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {BACKGROUND};
}}
QCheckBox::indicator:hover {{
    border: 1px solid #3b465c;
}}
QCheckBox::indicator:checked {{
    background: {RUNNING};
    border: 1px solid {RUNNING};
}}
QSpinBox {{
    background: {BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 3px 6px;
    min-width: 54px;
    color: {TEXT};
}}
QSpinBox:focus {{
    border: 1px solid #3b465c;
}}
QLabel#dialogHint {{
    font-size: 10px;
    color: {FAINT};
}}
QPushButton#dialogLink {{
    background: transparent;
    border: none;
    color: {MUTED};
    font-size: 10px;
    padding: 2px;
    text-decoration: underline;
}}
QPushButton#dialogLink:hover {{
    color: {TEXT};
}}
QPushButton#dialogLink:disabled {{
    color: {FAINT};
    text-decoration: none;
}}
QDialogButtonBox QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
    color: {TEXT};
    font-size: 11px;
    min-width: 64px;
}}
QDialogButtonBox QPushButton:hover {{
    background: {SURFACE_HOVER};
}}
QDialogButtonBox QPushButton:default {{
    border: 1px solid #3b465c;
}}
"""
