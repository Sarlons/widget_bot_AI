"""Widget configuration stored outside the repository."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

logger = logging.getLogger("ai_token_widget.config")


def default_config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AITokenWidget"
    return Path.home() / ".config" / "ai-token-widget"


@dataclass
class Config:
    poll_seconds: int = 5
    max_session_age_hours: float = 24.0
    running_window_seconds: int = 90
    always_on_top: bool = True
    opacity: float = 0.97
    window_x: int | None = None
    window_y: int | None = None
    window_width: int = 360
    window_height: int = 560
    collapsed: bool = False
    notifications_enabled: bool = True
    notification_sound: bool = False
    low_quota_percent: int = 20
    muted_agents: list[str] = field(default_factory=list)
    collapsed_groups: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        target = path or (default_config_dir() / "config.json")
        if not target.exists():
            return cls()
        try:
            raw = json.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        allowed = {field.name for field in fields(cls)}
        values = {key: value for key, value in raw.items() if key in allowed}
        try:
            config = cls(**values)
            config.validate()
        except (TypeError, ValueError):
            return cls()
        return config

    def validate(self) -> None:
        self.poll_seconds = max(2, min(60, int(self.poll_seconds)))
        self.max_session_age_hours = max(1.0, min(168.0, float(self.max_session_age_hours)))
        self.running_window_seconds = max(30, min(600, int(self.running_window_seconds)))
        self.opacity = max(0.5, min(1.0, float(self.opacity)))
        self.window_width = max(320, min(520, int(self.window_width)))
        self.window_height = max(360, min(900, int(self.window_height)))
        self.low_quota_percent = max(1, min(50, int(self.low_quota_percent)))
        if not isinstance(self.always_on_top, bool):
            self.always_on_top = True
        if not isinstance(self.collapsed, bool):
            self.collapsed = False
        if not isinstance(self.notifications_enabled, bool):
            self.notifications_enabled = True
        if not isinstance(self.notification_sound, bool):
            self.notification_sound = False
        if not isinstance(self.muted_agents, (list, tuple)):
            self.muted_agents = []
        else:
            self.muted_agents = sorted(
                {
                    value
                    for value in self.muted_agents
                    if isinstance(value, str) and value
                }
            )
        if not isinstance(self.collapsed_groups, (list, tuple)):
            self.collapsed_groups = []
        else:
            self.collapsed_groups = sorted(
                {
                    value
                    for value in self.collapsed_groups
                    if isinstance(value, str) and value
                }
            )

    def save(self, path: Path | None = None) -> bool:
        target = path or (default_config_dir() / "config.json")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            temporary.replace(target)
        except OSError:
            logger.warning("Could not save widget configuration", exc_info=True)
            return False
        return True
