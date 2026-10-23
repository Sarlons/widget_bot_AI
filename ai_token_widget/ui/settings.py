"""Modal settings dialog for notifications, thresholds, refresh and diagnostics."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.agents import AGENT_ORDER, agent_label
from ..core.config import Config, default_config_dir
from ..core.logging_setup import log_path
from . import theme


class SettingsDialog(QDialog):
    """Edit the subset of configuration that can be applied at runtime."""

    def __init__(
        self,
        config: Config,
        parent: QWidget | None = None,
        diagnostics_provider: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._diagnostics_provider = diagnostics_provider
        self._reset_position_requested = False
        self.setObjectName("settingsDialog")
        self.setWindowTitle("AI Token Widget settings")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(360)
        self.setStyleSheet(theme.STYLESHEET)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)

        title = QLabel("SETTINGS")
        title.setObjectName("title")
        outer.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        content.setObjectName("settingsContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(10)

        notifications = QGroupBox("Notifications")
        notification_layout = QVBoxLayout(notifications)
        notification_layout.setSpacing(8)

        self._notifications = QCheckBox("Show tray notifications")
        self._notifications.setChecked(config.notifications_enabled)
        self._notifications.setToolTip(
            "Quota, session-state and adapter-error tray notifications."
        )
        notification_layout.addWidget(self._notifications)

        self._sound = QCheckBox("Play a sound for new alerts")
        self._sound.setChecked(config.notification_sound)
        self._sound.setEnabled(config.notifications_enabled)
        self._sound.setToolTip(
            "Play the Windows notification sound once per poll when one or more "
            "new alerts are raised."
        )
        self._notifications.toggled.connect(self._sound.setEnabled)
        notification_layout.addWidget(self._sound)

        threshold = QHBoxLayout()
        threshold_label = QLabel("Low quota alert at")
        threshold_label.setObjectName("rowLabel")
        self._low_quota = QSpinBox()
        self._low_quota.setRange(1, 50)
        self._low_quota.setSuffix(" %")
        self._low_quota.setValue(config.low_quota_percent)
        self._low_quota.setToolTip(
            "Also controls the Issues filter and the red/amber quota bars."
        )
        threshold.addWidget(threshold_label)
        threshold.addStretch(1)
        threshold.addWidget(self._low_quota)
        notification_layout.addLayout(threshold)

        mute_label = QLabel("Mute alerts for")
        mute_label.setObjectName("rowLabel")
        notification_layout.addWidget(mute_label)

        mute_row = QHBoxLayout()
        mute_row.setSpacing(12)
        self._mutes: dict[str, QCheckBox] = {}
        for agent in AGENT_ORDER:
            box = QCheckBox(agent_label(agent))
            box.setChecked(agent in config.muted_agents)
            box.setToolTip(
                "Mute quota and session-state alerts for this provider. "
                "Adapter errors are always shown."
            )
            mute_row.addWidget(box)
            self._mutes[agent] = box
        mute_row.addStretch(1)
        notification_layout.addLayout(mute_row)

        mute_hint = QLabel("Adapter errors are always shown.")
        mute_hint.setObjectName("dialogHint")
        notification_layout.addWidget(mute_hint)
        content_layout.addWidget(notifications)

        refresh = QGroupBox("Refresh")
        refresh_layout = QHBoxLayout(refresh)
        refresh_label = QLabel("Poll interval")
        refresh_label.setObjectName("rowLabel")
        self._poll = QSpinBox()
        self._poll.setRange(2, 60)
        self._poll.setSuffix(" s")
        self._poll.setValue(config.poll_seconds)
        self._poll.setToolTip("How often sessions are re-read (2–60 seconds).")
        refresh_layout.addWidget(refresh_label)
        refresh_layout.addStretch(1)
        refresh_layout.addWidget(self._poll)
        content_layout.addWidget(refresh)

        window = QGroupBox("Window")
        window_layout = QVBoxLayout(window)
        window_layout.setSpacing(8)

        window_toggles = QHBoxLayout()
        window_toggles.setSpacing(16)
        self._always_on_top = QCheckBox("Always on top")
        self._always_on_top.setChecked(config.always_on_top)
        self._always_on_top.setToolTip(
            "Keep the widget above other windows. Disable it to let normal "
            "windows cover the widget."
        )
        self._start_collapsed = QCheckBox("Start collapsed")
        self._start_collapsed.setChecked(config.collapsed)
        self._start_collapsed.setToolTip(
            "Hide the session list now and when the widget starts again."
        )
        window_toggles.addWidget(self._always_on_top)
        window_toggles.addWidget(self._start_collapsed)
        window_toggles.addStretch(1)
        window_layout.addLayout(window_toggles)

        opacity_row = QHBoxLayout()
        opacity_label = QLabel("Opacity")
        opacity_label.setObjectName("rowLabel")
        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(50, 100)
        self._opacity.setValue(round(config.opacity * 100))
        self._opacity.setToolTip(
            "Window opacity from 50% to 100%. Lower values make the widget "
            "more transparent."
        )
        self._opacity_value = QLabel(f"{self._opacity.value()}%")
        self._opacity_value.setObjectName("rowValue")
        self._opacity_value.setMinimumWidth(34)
        self._opacity_value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._opacity.valueChanged.connect(
            lambda value: self._opacity_value.setText(f"{value}%")
        )
        opacity_row.addWidget(opacity_label)
        opacity_row.addWidget(self._opacity, 1)
        opacity_row.addWidget(self._opacity_value)
        window_layout.addLayout(opacity_row)

        reset_row = QHBoxLayout()
        reset_hint = QLabel("Move the widget back to the top-right corner.")
        reset_hint.setObjectName("dialogHint")
        reset_hint.setWordWrap(True)
        reset_row.addWidget(reset_hint, 1)
        self._reset_position = self._dialog_link("Reset position")
        self._reset_position.setToolTip(
            "Reset the saved window position when you press Save."
        )
        self._reset_position.clicked.connect(self._request_reset_position)
        reset_row.addWidget(self._reset_position)
        window_layout.addLayout(reset_row)
        content_layout.addWidget(window)

        diagnostics_row = QHBoxLayout()
        diagnostics_row.setSpacing(6)
        diagnostics_label = QLabel("Diagnostics")
        diagnostics_label.setObjectName("rowLabel")
        diagnostics_row.addWidget(diagnostics_label)
        diagnostics_row.addStretch(1)

        open_folder = self._dialog_link("Open folder")
        open_folder.setToolTip("Open the widget's data folder.")
        open_folder.clicked.connect(self._open_data_folder)
        diagnostics_row.addWidget(open_folder)

        open_log = self._dialog_link("Open log")
        open_log.setToolTip(
            "Open widget.log in the default editor, or the data folder if it "
            "does not exist yet."
        )
        open_log.clicked.connect(self._open_log)
        diagnostics_row.addWidget(open_log)

        self._copy_report = self._dialog_link("Copy report")
        self._copy_report.setToolTip(
            "Copy a sanitized report with counts, timings, settings and adapter "
            "errors. It never includes prompts or transcript text."
        )
        self._copy_report.setEnabled(diagnostics_provider is not None)
        self._copy_report.clicked.connect(self._copy_diagnostics)
        diagnostics_row.addWidget(self._copy_report)
        content_layout.addLayout(diagnostics_row)

        hint = QLabel(
            "Changes apply immediately. Window size and exact position stay in "
            "config.json; session age stays an advanced setting."
        )
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)
        content_layout.addWidget(hint)
        content_layout.addStretch(1)
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self._reset_copy_button)

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(500, max(380, available.width() - 40))
            height = min(680, max(480, available.height() - 80))
            self.resize(width, height)
        else:
            self.resize(500, 680)

    @staticmethod
    def _dialog_link(text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("dialogLink")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _open_data_folder(self) -> None:
        folder = default_config_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_log(self) -> None:
        target = log_path()
        if target.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
            return
        self._open_data_folder()

    def _copy_diagnostics(self) -> None:
        if self._diagnostics_provider is None:
            return
        QApplication.clipboard().setText(self._diagnostics_provider())
        self._copy_report.setText("Copied")
        self._copy_timer.start(1500)

    def _reset_copy_button(self) -> None:
        self._copy_report.setText("Copy report")

    def _request_reset_position(self) -> None:
        self._reset_position_requested = True
        self._reset_position.setText("Reset on Save")
        self._reset_position.setEnabled(False)

    def reset_position_requested(self) -> bool:
        return self._reset_position_requested

    def apply_to(self, config: Config) -> None:
        """Copy the edited values into ``config`` after Save."""
        config.notifications_enabled = self._notifications.isChecked()
        config.notification_sound = self._sound.isChecked()
        config.low_quota_percent = self._low_quota.value()
        config.poll_seconds = self._poll.value()
        config.always_on_top = self._always_on_top.isChecked()
        config.collapsed = self._start_collapsed.isChecked()
        config.opacity = self._opacity.value() / 100.0
        selected = {
            agent for agent, box in self._mutes.items() if box.isChecked()
        }
        # Preserve mutes for providers that are not present in this version's
        # checkbox list, so opening the dialog never drops future/unknown ids.
        unknown = set(config.muted_agents) - set(self._mutes)
        config.muted_agents = sorted(selected | unknown)
        config.validate()


__all__ = ["SettingsDialog"]
