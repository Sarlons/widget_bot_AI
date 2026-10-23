"""Frameless always-on-top widget window."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..core.config import Config
from ..core.alerts import Alert, AlertTracker
from ..core.diagnostics import build_diagnostics
from ..core.filters import (
    FilterMode,
    SessionFilter,
    filter_sessions,
    needs_attention,
)
from ..core.formatting import format_age
from ..core.grouping import group_sessions
from ..core.models import SessionState, Snapshot
from ..core.notifications import NotificationHistory, play_notification_sound
from ..core.projects import aggregate_projects
from ..core.registry import Registry
from . import theme
from .cards import SessionCard
from .groups import GroupHeader
from .history import NotificationHistoryDialog
from .projects import ProjectSection
from .refresh import RefreshWorker
from .settings import SettingsDialog

logger = logging.getLogger("ai_token_widget.window")

SLOW_REFRESH_SECONDS = 15.0
MIN_STALE_SECONDS = 30.0


class DragHeader(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerBar")
        self._offset: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = (
                event.globalPosition().toPoint()
                - self.window().frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._offset = None
        super().mouseReleaseEvent(event)


class WidgetWindow(QWidget):
    refreshRequested = Signal()

    def __init__(
        self,
        registry: Registry,
        config: Config,
        history: NotificationHistory | None = None,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._config = config
        self._history = (
            history if history is not None else NotificationHistory()
        )
        self._snapshot = Snapshot()
        self._tray: QSystemTrayIcon | None = None
        self._quitting = False
        self._shutting_down = False
        self._refresh_busy = False
        self._refresh_pending = False
        self._refresh_started_monotonic: float | None = None
        self._slow_refresh_logged = False
        self._last_snapshot_at: datetime | None = None
        self._refresh_error: str | None = None
        self._logged_errors: set[str] = set()
        self._alerts = AlertTracker(config.low_quota_percent, config.muted_agents)
        self._filter_mode = FilterMode.ALL
        self._filter_buttons: dict[FilterMode, QPushButton] = {}
        self._notifications_action: QAction | None = None
        self._sound_action: QAction | None = None

        self.setWindowTitle("AI Token Widget")
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(config.window_width)
        self.setWindowOpacity(config.opacity)

        self._build_ui()
        self._build_tray()
        self._restore_geometry()
        self._start_worker()

        self._timer = QTimer(self)
        self._timer.setInterval(config.poll_seconds * 1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        self._age_timer = QTimer(self)
        self._age_timer.setInterval(1000)
        self._age_timer.timeout.connect(self._age_tick)
        self._age_timer.start()

        self.request_refresh()

    # -- construction ---------------------------------------------------

    def _start_worker(self) -> None:
        self._worker_thread = QThread(self)
        self._worker = RefreshWorker(self._registry)
        self._worker.moveToThread(self._worker_thread)
        self.refreshRequested.connect(self._worker.refresh)
        self._worker.snapshot_ready.connect(self._apply_snapshot)
        self._worker.failed.connect(self._refresh_failed)
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.start()

    def _build_ui(self) -> None:
        shell = QVBoxLayout(self)
        shell.setContentsMargins(12, 12, 12, 12)
        shell.setSpacing(0)

        self._root = QFrame()
        self._root.setObjectName("root")
        shell.addWidget(self._root)

        root_layout = QVBoxLayout(self._root)
        root_layout.setContentsMargins(14, 12, 14, 10)
        root_layout.setSpacing(8)

        header = DragHeader()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel("AI USAGE")
        title.setObjectName("title")
        self._summary = QLabel("starting…")
        self._summary.setObjectName("summary")

        self._refresh_button = self._icon_button("↻", "Refresh now")
        self._settings_button = self._icon_button("⚙", "Settings")
        self._settings_button.setStyleSheet('font-family: "Segoe UI Symbol";')
        self._collapse_button = self._icon_button("−", "Collapse")
        self._close_button = self._icon_button("×", "Hide to tray")
        self._refresh_button.clicked.connect(self.request_refresh)
        self._settings_button.clicked.connect(self._open_settings)
        self._collapse_button.clicked.connect(self.toggle_collapsed)
        self._close_button.clicked.connect(self._hide_to_tray)

        header_layout.addWidget(title)
        header_layout.addWidget(self._summary)
        header_layout.addStretch(1)
        header_layout.addWidget(self._settings_button)
        header_layout.addWidget(self._refresh_button)
        header_layout.addWidget(self._collapse_button)
        header_layout.addWidget(self._close_button)
        root_layout.addWidget(header)

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_filter_bar())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._cards_host = QWidget()
        self._cards_host.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch(1)
        self._scroll.setWidget(self._cards_host)
        body_layout.addWidget(self._scroll)
        root_layout.addWidget(self._body, 1)

        self._footer = QLabel("")
        self._footer.setObjectName("footer")
        root_layout.addWidget(self._footer)

        self._apply_style()

    def _icon_button(self, text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("iconButton")
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(22, 22)
        return button

    def _build_filter_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("filterBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(4)

        self._search = QLineEdit()
        self._search.setObjectName("filterSearch")
        self._search.setPlaceholderText("Project, model, agent…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(24)
        self._search.setMinimumWidth(60)
        self._search.textChanged.connect(self._filters_changed)
        layout.addWidget(self._search, 1)

        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        choices = (
            (FilterMode.ALL, "All", "Show every recent session"),
            (FilterMode.RUNNING, "Running", "Show only sessions generating now"),
            (
                FilterMode.ATTENTION,
                "Issues",
                "Low quota, rate-limited/error sessions or nearly full context",
            ),
        )
        for mode, label, tooltip in choices:
            button = QPushButton(label)
            button.setObjectName("filterChip")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tooltip)
            button.setFixedHeight(24)
            button.clicked.connect(
                lambda _checked=False, value=mode: self._set_filter_mode(value)
            )
            self._filter_group.addButton(button)
            self._filter_buttons[mode] = button
            layout.addWidget(button)
        self._filter_buttons[FilterMode.ALL].setChecked(True)
        return bar

    def _filters_changed(self) -> None:
        self._render()

    def _set_filter_mode(self, mode: FilterMode) -> None:
        self._filter_mode = mode
        button = self._filter_buttons.get(mode)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._render()

    def _clear_filters(self) -> None:
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._filter_mode = FilterMode.ALL
        self._filter_buttons[FilterMode.ALL].setChecked(True)
        self._render()

    def _filters_active(self) -> bool:
        return (
            self._filter_mode is not FilterMode.ALL
            or bool(self._search.text().strip())
        )

    def _toggle_group(self, agent: str) -> None:
        collapsed = set(self._config.collapsed_groups)
        if agent in collapsed:
            collapsed.remove(agent)
        else:
            collapsed.add(agent)
        self._config.collapsed_groups = sorted(collapsed)
        self._config.save()
        self._render()

    def _apply_style(self) -> None:
        self.setStyleSheet(theme.STYLESHEET)
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect

            shadow = QGraphicsDropShadowEffect(self._root)
            shadow.setBlurRadius(28)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 170))
            self._root.setGraphicsEffect(shadow)
        except Exception:
            pass

    def _default_position(self, width: int, height: int) -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if available is None:
            return 100, 100
        x = available.right() - width - 24
        y = available.top() + 80
        x = max(available.left(), min(x, available.right() - width))
        y = max(available.top(), min(y, available.bottom() - height))
        return x, y

    def _restore_geometry(self) -> None:
        width = self._config.window_width
        height = 74 if self._config.collapsed else self._config.window_height
        self.resize(width, height)
        if self._config.window_x is not None and self._config.window_y is not None:
            x, y = self._config.window_x, self._config.window_y
            screen = QApplication.primaryScreen()
            available = screen.availableGeometry() if screen else None
            if available is not None:
                x = max(available.left(), min(x, available.right() - width))
                y = max(available.top(), min(y, available.bottom() - height))
        else:
            x, y = self._default_position(width, height)
        self.move(x, y)
        self._body.setVisible(not self._config.collapsed)
        self._collapse_button.setText(
            "+" if self._config.collapsed else "−"
        )

    # -- tray -----------------------------------------------------------

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self._make_icon(theme.IDLE), self)
        self._tray.setToolTip("AI Token Widget")
        menu = QMenu()
        show_action = QAction("Show / hide", self)
        show_action.triggered.connect(self._toggle_visibility)
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.request_refresh)
        settings_action = QAction("Settings…", self)
        settings_action.triggered.connect(self._open_settings)
        self._notifications_action = QAction("Notifications", self)
        self._notifications_action.setCheckable(True)
        self._notifications_action.setChecked(self._config.notifications_enabled)
        self._notifications_action.toggled.connect(self._set_notifications_enabled)
        self._sound_action = QAction("Notification sound", self)
        self._sound_action.setCheckable(True)
        self._sound_action.setChecked(self._config.notification_sound)
        self._sound_action.setEnabled(self._config.notifications_enabled)
        self._sound_action.toggled.connect(self._set_notification_sound)
        history_action = QAction("Notification history…", self)
        history_action.triggered.connect(self._open_history)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(refresh_action)
        menu.addAction(settings_action)
        menu.addAction(self._notifications_action)
        menu.addAction(self._sound_action)
        menu.addAction(history_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._toggle_visibility()

    def _set_notifications_enabled(self, enabled: bool) -> None:
        self._config.notifications_enabled = bool(enabled)
        if self._sound_action is not None:
            self._sound_action.setEnabled(self._config.notifications_enabled)
        self._config.save()

    def _set_notification_sound(self, enabled: bool) -> None:
        self._config.notification_sound = bool(enabled)
        self._config.save()

    def _open_history(self) -> None:
        dialog = NotificationHistoryDialog(self._history, self)
        dialog.exec()
        dialog.deleteLater()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self._config,
            self,
            diagnostics_provider=self._diagnostics_text,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_settings(dialog)
        dialog.deleteLater()

    def _apply_settings(self, dialog: SettingsDialog) -> None:
        previous_low = self._config.low_quota_percent
        dialog.apply_to(self._config)
        self._config.save()
        self._timer.setInterval(self._config.poll_seconds * 1000)
        if self._notifications_action is not None:
            self._notifications_action.blockSignals(True)
            self._notifications_action.setChecked(
                self._config.notifications_enabled
            )
            self._notifications_action.blockSignals(False)
        if self._sound_action is not None:
            self._sound_action.blockSignals(True)
            self._sound_action.setChecked(self._config.notification_sound)
            self._sound_action.setEnabled(self._config.notifications_enabled)
            self._sound_action.blockSignals(False)
        self._alerts.low_quota_percent = self._config.low_quota_percent
        self._alerts.set_muted_agents(self._config.muted_agents)
        if self._config.low_quota_percent != previous_low:
            # Re-seed on the next snapshot instead of alerting for conditions
            # that were already present when the threshold changed.
            self._alerts.reset()
        self._apply_window_appearance()
        self._set_collapsed(self._config.collapsed, save=False)
        if dialog.reset_position_requested():
            self.reset_position(save=False)
            self._config.save()
        self._render()
        self.request_refresh()

    def _make_icon(self, color: str) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(3, 3, 26, 26)
            painter.setBrush(QColor(theme.BACKGROUND))
            painter.drawEllipse(10, 10, 12, 12)
        finally:
            painter.end()
        return QIcon(pixmap)

    # -- refresh / render ----------------------------------------------

    def _poll(self) -> None:
        # A slow poll must not queue a backlog of timer refreshes; wait for the
        # next tick after the current snapshot arrives.
        if not self._refresh_busy:
            self.request_refresh()

    def request_refresh(self) -> None:
        """Ask the worker for a snapshot without blocking the GUI thread."""
        if self._shutting_down:
            return
        if self._refresh_busy:
            self._refresh_pending = True
            return
        self._refresh_busy = True
        self._refresh_started_monotonic = time.monotonic()
        self._slow_refresh_logged = False
        self._update_footer()
        self.refreshRequested.emit()

    def _apply_snapshot(self, snapshot: Snapshot) -> None:
        if self._shutting_down:
            return
        self._refresh_busy = False
        self._refresh_started_monotonic = None
        self._refresh_error = None
        self._last_snapshot_at = snapshot.generated_at
        self._snapshot = snapshot
        for error in snapshot.errors:
            if error not in self._logged_errors:
                logger.warning("Adapter error: %s", error)
        self._logged_errors = set(snapshot.errors)
        self._render()
        self._update_tray()
        alerts = self._alerts.update(
            snapshot, notify=self._config.notifications_enabled
        )
        self._show_alerts(alerts)
        self._run_pending()

    def _refresh_failed(self, message: str) -> None:
        if self._shutting_down:
            return
        self._refresh_busy = False
        self._refresh_started_monotonic = None
        self._refresh_error = message
        logger.warning("Refresh failed: %s", message)
        self._update_footer()
        self._run_pending()

    def _run_pending(self) -> None:
        if self._refresh_pending and not self._shutting_down:
            self._refresh_pending = False
            self.request_refresh()

    def _age_tick(self) -> None:
        if self._shutting_down:
            return
        if self._refresh_busy:
            elapsed = self._refresh_elapsed()
            if elapsed >= SLOW_REFRESH_SECONDS and not self._slow_refresh_logged:
                logger.warning(
                    "Snapshot refresh has been running for %.0f seconds", elapsed
                )
                self._slow_refresh_logged = True
        self._update_footer()

    def _refresh_elapsed(self) -> float:
        if self._refresh_started_monotonic is None:
            return 0.0
        return max(0.0, time.monotonic() - self._refresh_started_monotonic)

    def _snapshot_age_seconds(self) -> float | None:
        if self._last_snapshot_at is None:
            return None
        base = self._last_snapshot_at
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - base).total_seconds())

    def _refresh_status(self) -> tuple[str, str]:
        if self._refresh_busy:
            elapsed = self._refresh_elapsed()
            if elapsed >= SLOW_REFRESH_SECONDS:
                return (
                    f"refresh slow ({int(elapsed)}s)",
                    theme.WAITING,
                )
            return "refreshing…", theme.FAINT
        age = self._snapshot_age_seconds()
        if self._refresh_error:
            if age is None:
                return "refresh failed", theme.RATE_LIMITED
            return (
                f"refresh failed · last update {format_age(age)}",
                theme.RATE_LIMITED,
            )
        if age is None:
            return "starting…", theme.FAINT
        stale_after = max(
            MIN_STALE_SECONDS, self._config.poll_seconds * 2.0 + 5.0
        )
        if age >= stale_after:
            return (
                f"stale · last update {format_age(age)}",
                theme.WAITING,
            )
        return f"updated {format_age(age)}", theme.FAINT

    def _diagnostics_text(self) -> str:
        return build_diagnostics(
            version=__version__,
            config=self._config,
            snapshot=self._snapshot,
            last_snapshot_at=self._last_snapshot_at,
            refresh_busy=self._refresh_busy,
            refresh_seconds=(
                self._refresh_elapsed() if self._refresh_busy else None
            ),
            refresh_error=self._refresh_error,
            history_count=len(self._history),
        )

    def _show_alerts(self, alerts: list[Alert]) -> None:
        if self._tray is None or not alerts:
            return
        for alert in alerts[:3]:
            self._tray.showMessage(
                alert.title,
                alert.message,
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )
        self._history.append_many(alerts)
        if self._config.notification_sound:
            play_notification_sound()

    def _render(self) -> None:
        scroll_position = self._scroll.verticalScrollBar().value()
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Detach immediately so findChildren() and accessibility trees
                # do not see stale cards while deferred deletion is pending.
                widget.setParent(None)
                widget.deleteLater()

        filtered = filter_sessions(
            self._snapshot.sessions,
            SessionFilter(self._filter_mode, self._search.text()),
            self._config.low_quota_percent,
        )
        projects = aggregate_projects(filtered)
        if projects:
            self._cards_layout.addWidget(ProjectSection(projects))
        groups = group_sessions(filtered)
        for group in groups:
            container = QWidget()
            container.setObjectName("groupContainer")
            group_layout = QVBoxLayout(container)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(6)

            collapsed = group.agent in self._config.collapsed_groups
            attention = sum(
                1
                for session in group.sessions
                if needs_attention(session, self._config.low_quota_percent)
            )
            header = GroupHeader(group, collapsed, attention)
            header.toggled.connect(self._toggle_group)
            group_layout.addWidget(header)
            if not collapsed:
                for session in group.sessions:
                    group_layout.addWidget(SessionCard(session))
            self._cards_layout.addWidget(container)

        if not groups:
            if self._snapshot.sessions:
                self._add_filter_empty()
            else:
                empty = QLabel(
                    "No recent sessions detected.\n"
                    "Start Claude Code, Codex or OpenCode and it will appear here."
                )
                empty.setObjectName("empty")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty.setWordWrap(True)
                self._cards_layout.addWidget(empty)

        self._cards_layout.addStretch(1)
        self._update_summary(filtered)
        self._update_footer(len(filtered))
        # Layout geometry settles on the next event-loop turn; restore the
        # user's scroll position after the new cards have been measured.
        QTimer.singleShot(0, lambda: self._restore_scroll(scroll_position))

    def _add_filter_empty(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 18, 0, 18)
        layout.setSpacing(4)
        label = QLabel("No sessions match the current filters.")
        label.setObjectName("empty")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        clear = QPushButton("Clear filters")
        clear.setObjectName("filterClear")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._clear_filters)
        layout.addWidget(label)
        layout.addWidget(clear, 0, Qt.AlignmentFlag.AlignHCenter)
        self._cards_layout.addWidget(container)

    def _update_summary(self, filtered) -> None:
        total = len(self._snapshot.sessions)
        if not total:
            self._summary.setText("no sessions")
            return
        visible = len(filtered)
        running = sum(
            1
            for session in filtered
            if session.state is SessionState.RUNNING
        )
        limited = sum(
            1
            for session in filtered
            if session.state is SessionState.RATE_LIMITED
        )
        if self._filters_active():
            bits = [f"{visible}/{total} shown"]
            if running:
                bits.append(f"{running} running")
            if limited:
                bits.append(f"{limited} limited")
        else:
            bits = [f"{running} running" if running else "no active runs"]
            if limited:
                bits.append(f"{limited} limited")
        self._summary.setText(" · ".join(bits))

    def _restore_scroll(self, position: int) -> None:
        if not self._shutting_down:
            self._scroll.verticalScrollBar().setValue(position)

    def _update_footer(self, visible: int | None = None) -> None:
        total = len(self._snapshot.sessions)
        if visible is None:
            visible = len(
                filter_sessions(
                    self._snapshot.sessions,
                    SessionFilter(self._filter_mode, self._search.text()),
                    self._config.low_quota_percent,
                )
            )
        if total and self._filters_active():
            sessions = f"{visible}/{total} sessions"
        else:
            sessions = f"{total} sessions"
        status, color = self._refresh_status()
        footer = f"{sessions} · {status}"
        errors = list(self._snapshot.errors)
        if self._refresh_error:
            errors.append(f"refresh: {self._refresh_error}")
        if errors:
            footer += " · " + " · ".join(errors)
            color = theme.RATE_LIMITED
        self._footer.setText(footer)
        self._footer.setToolTip(footer)
        self._footer.setStyleSheet(f"color: {color};")

    def _update_tray(self) -> None:
        if self._tray is None:
            return
        if self._snapshot.rate_limited_count:
            color = theme.RATE_LIMITED
        elif self._snapshot.running_count:
            color = theme.RUNNING
        else:
            color = theme.IDLE
        self._tray.setIcon(self._make_icon(color))
        self._tray.setToolTip(
            f"AI Token Widget · {self._snapshot.running_count} running · "
            f"{len(self._snapshot.sessions)} sessions"
        )

    # -- window behaviour ----------------------------------------------

    def _set_collapsed(self, collapsed: bool, save: bool = True) -> None:
        self._config.collapsed = bool(collapsed)
        self._body.setVisible(not self._config.collapsed)
        self._collapse_button.setText(
            "+" if self._config.collapsed else "−"
        )
        self.resize(
            self.width(),
            74 if self._config.collapsed else self._config.window_height,
        )
        if save:
            self._config.save()

    def toggle_collapsed(self) -> None:
        self._set_collapsed(not self._config.collapsed)

    def _apply_window_appearance(self) -> None:
        self.setWindowOpacity(self._config.opacity)
        visible = self.isVisible()
        self.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint,
            self._config.always_on_top,
        )
        if visible:
            self.show()

    def reset_position(self, save: bool = True) -> None:
        self._config.window_x = None
        self._config.window_y = None
        x, y = self._default_position(self.width(), self.height())
        self.move(x, y)
        if save:
            self._config.save()

    def _toggle_visibility(self) -> None:
        if self.isVisible():
            self._hide_to_tray()
        else:
            self.reveal()

    def reveal(self) -> None:
        if self._shutting_down:
            return
        self.show()
        self.raise_()
        self.activateWindow()

    def _hide_to_tray(self) -> None:
        self._save_state()
        if self._tray is not None:
            self.hide()
        else:
            self._quit()

    def _save_state(self) -> None:
        self._config.window_x = self.x()
        self._config.window_y = self.y()
        self._config.window_width = self.width()
        if self._body.isVisible():
            self._config.window_height = self.height()
        self._config.save()

    def shutdown(self) -> bool:
        """Stop timers and the refresh thread before the process exits.

        Returns ``True`` when the worker is no longer running, so the caller
        can close adapters without racing an in-flight read.
        """
        if self._shutting_down:
            return not self._worker_thread.isRunning()
        self._shutting_down = True
        self._refresh_pending = False
        self._timer.stop()
        self._age_timer.stop()
        stopped = True
        if self._worker_thread.isRunning():
            self._worker_thread.quit()
            stopped = self._worker_thread.wait(8000)
            if not stopped:
                logger.warning("Refresh worker did not stop within 8 seconds")
        return stopped

    def quit(self) -> None:
        """Quit the widget; used by the installer's ``--quit`` handshake."""
        self._quit()

    def _quit(self) -> None:
        self._quitting = True
        self._save_state()
        if self._tray is not None:
            self._tray.hide()
        self.shutdown()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self._quitting:
            self._save_state()
            super().closeEvent(event)
            return
        if self._tray is not None:
            event.ignore()
            self._hide_to_tray()
            return
        # Without a tray icon, closing must quit: the app does not use
        # quitOnLastWindowClosed because the widget normally hides instead.
        self._quitting = True
        self._save_state()
        self.shutdown()
        event.accept()
        QApplication.quit()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.isVisible():
            self._config.window_x = self.x()
            self._config.window_y = self.y()


__all__ = ["WidgetWindow"]
