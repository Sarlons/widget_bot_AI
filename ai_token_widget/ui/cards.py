"""One card per agent session."""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.agents import agent_label
from ..core.formatting import (
    format_age,
    format_cost,
    format_percent,
    format_reset,
    format_tokens,
)
from ..core.models import Confidence, Session
from . import theme


def _bar_color(remaining_percent: float | None) -> str:
    if remaining_percent is None:
        return theme.FAINT
    if remaining_percent >= 50:
        return theme.RUNNING
    if remaining_percent >= 20:
        return theme.WAITING
    return theme.RATE_LIMITED


def _progress(value: float | None, color: str) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(int(round(value or 0)))
    bar.setTextVisible(False)
    bar.setFixedHeight(5)
    bar.setStyleSheet(
        "QProgressBar { background: #262b35; border: none; border-radius: 3px; }"
        f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
    )
    return bar


def _row(label: str, value: str) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    left = QLabel(label)
    left.setObjectName("rowLabel")
    right = QLabel(value)
    right.setObjectName("rowValue")
    right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    right.setWordWrap(True)
    right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    layout.addWidget(left)
    layout.addStretch(1)
    layout.addWidget(right)
    return container


class SessionCard(QFrame):
    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.setObjectName("sessionCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        accent = theme.AGENT_ACCENTS.get(session.agent, theme.TEXT)
        state_color = theme.STATE_COLORS.get(session.state.value, theme.IDLE)
        state_label = theme.STATE_LABELS.get(session.state.value, session.state.value.upper())

        header = QHBoxLayout()
        header.setSpacing(7)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {state_color}; border-radius: 4px;")
        agent = QLabel(agent_label(session.agent))
        agent.setObjectName("agent")
        agent.setStyleSheet(f"color: {accent};")
        project = QLabel(session.project)
        project.setObjectName("project")
        project.setWordWrap(True)
        project.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        state = QLabel(state_label)
        state.setObjectName("state")
        state.setStyleSheet(f"color: {state_color};")
        header.addWidget(dot)
        header.addWidget(agent)
        header.addWidget(project)
        header.addStretch(1)
        header.addWidget(state)
        outer.addLayout(header)

        meta = QLabel(_meta_line(session))
        meta.setObjectName("model")
        meta.setWordWrap(True)
        outer.addWidget(meta)

        if session.context_window and session.context_used is not None:
            outer.addWidget(
                _row(
                    "Context (est.)" if session.context_estimated else "Context",
                    f"{format_percent(session.context_remaining_percent)} left",
                )
            )
            outer.addWidget(
                _progress(
                    session.context_remaining_percent,
                    _bar_color(session.context_remaining_percent),
                )
            )
            context_tokens = QLabel(
                f"{format_tokens(session.context_used)} / "
                f"{format_tokens(session.context_window)} tokens"
            )
            context_tokens.setWordWrap(True)
            outer.addWidget(context_tokens)
        else:
            outer.addWidget(_row("Context", "unavailable"))

        quota = session.quota
        if quota and quota.windows:
            outer.addWidget(_quota_header(quota.confidence, quota.plan, quota.captured_at))
            for window in quota.windows:
                value = f"{format_percent(window.remaining_percent)} left"
                if window.resets_at:
                    value += f" · resets {format_reset(window.resets_at)}"
                outer.addWidget(_row(window.label, value))
                outer.addWidget(
                    _progress(
                        window.remaining_percent, _bar_color(window.remaining_percent)
                    )
                )
        elif quota and quota.credits_usd is not None:
            outer.addWidget(_quota_header(quota.confidence, quota.plan, quota.captured_at))
            outer.addWidget(_row("Credits", f"${quota.credits_usd:.2f}"))
        else:
            outer.addWidget(_row("Quota", "unavailable"))

        usage = session.usage_total
        token_bits = [f"in {format_tokens(usage.billed_input)}", f"out {format_tokens(usage.output_tokens)}"]
        if usage.reasoning_tokens:
            token_bits.append(f"reasoning {format_tokens(usage.reasoning_tokens)}")
        if usage.total:
            token_bits.append(f"total {format_tokens(usage.total)}")
        if session.cost_usd is not None:
            token_bits.append(f"cost {format_cost(session.cost_usd)}")
        tokens = QLabel(" · ".join(token_bits))
        tokens.setObjectName("tokens")
        tokens.setWordWrap(True)
        outer.addWidget(tokens)


def _meta_line(session: Session) -> str:
    bits = [session.model]
    source = session.source
    if source and not source.startswith("{"):
        if len(source) > 28:
            source = source[:27] + "…"
        bits.append(source)
    if session.pid:
        bits.append(f"pid {session.pid}")
    bits.append(format_age(session.age_seconds))
    return " · ".join(bits)


def _quota_header(
    confidence: Confidence, plan: str | None, captured_at=None
) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    label = QLabel("Quota")
    label.setObjectName("rowLabel")
    badge = QLabel(
        "EXACT" if confidence is Confidence.EXACT else
        "EST." if confidence is Confidence.ESTIMATED else "N/A"
    )
    color = (
        theme.RUNNING if confidence is Confidence.EXACT
        else theme.WAITING if confidence is Confidence.ESTIMATED
        else theme.FAINT
    )
    badge.setStyleSheet(
        f"color: {color}; font-size: 8px; font-weight: 700; letter-spacing: 0.8px;"
        f"border: 1px solid {color}; border-radius: 4px; padding: 0px 4px;"
    )
    layout.addWidget(label)
    layout.addWidget(badge)
    if plan:
        plan_label = QLabel(plan)
        plan_label.setObjectName("rowValue")
        layout.addWidget(plan_label)
    if captured_at is not None:
        moment = captured_at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - moment).total_seconds()
        if age > 120:
            age_label = QLabel(f"as of {format_age(age)}")
            age_label.setObjectName("rowValue")
            layout.addWidget(age_label)
    layout.addStretch(1)
    return container


__all__ = ["SessionCard"]
