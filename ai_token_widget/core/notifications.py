"""Notification history and optional alert sound.

The history stores only the timestamp, title and message that were shown in the
tray. Alert keys are deliberately not stored because state-alert keys include
session ids; the history must stay safe to inspect next to the configuration.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .alerts import Alert
from .config import default_config_dir

logger = logging.getLogger("ai_token_widget.notifications")

MAX_RECORDS = 50
MAX_TITLE_CHARS = 200
MAX_MESSAGE_CHARS = 500


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass(frozen=True)
class NotificationRecord:
    created_at: datetime
    title: str
    message: str


class NotificationHistory:
    """Bounded, newest-first notification history persisted as JSON."""

    def __init__(
        self,
        path: Path | None = None,
        limit: int = MAX_RECORDS,
    ) -> None:
        self._path = Path(path) if path is not None else (
            default_config_dir() / "notifications.json"
        )
        self._limit = max(1, int(limit))
        self._records: deque[NotificationRecord] = deque(maxlen=self._limit)
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def __len__(self) -> int:
        return len(self._records)

    def records(self) -> tuple[NotificationRecord, ...]:
        return tuple(
            sorted(
                self._records,
                key=lambda record: record.created_at,
                reverse=True,
            )
        )

    @staticmethod
    def _record(alert: Alert, moment: datetime) -> NotificationRecord:
        return NotificationRecord(
            created_at=moment,
            title=alert.title[:MAX_TITLE_CHARS],
            message=alert.message[:MAX_MESSAGE_CHARS],
        )

    def append(
        self,
        alert: Alert,
        now: datetime | None = None,
    ) -> NotificationRecord:
        moment = _aware(now or datetime.now(timezone.utc))
        record = self._record(alert, moment)
        self._records.appendleft(record)
        self._save()
        return record

    def append_many(
        self,
        alerts: Iterable[Alert],
        now: datetime | None = None,
    ) -> int:
        """Append a poll's alerts once, preserving their priority order."""
        moment = _aware(now or datetime.now(timezone.utc))
        prepared = [self._record(alert, moment) for alert in alerts]
        for record in reversed(prepared):
            self._records.appendleft(record)
        if prepared:
            self._save()
        return len(prepared)

    def clear(self) -> None:
        self._records.clear()
        self._save()

    def _parse(self, item: object) -> NotificationRecord | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        message = item.get("message")
        created = item.get("created_at")
        if (
            not isinstance(title, str)
            or not isinstance(message, str)
            or not isinstance(created, str)
        ):
            return None
        try:
            moment = datetime.fromisoformat(created)
        except (TypeError, ValueError):
            return None
        return NotificationRecord(
            _aware(moment),
            title[:MAX_TITLE_CHARS],
            message[:MAX_MESSAGE_CHARS],
        )

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Could not read notification history: %s",
                type(exc).__name__,
            )
            return
        if not isinstance(raw, list):
            return
        parsed: list[NotificationRecord] = []
        for item in raw:
            record = self._parse(item)
            if record is not None:
                parsed.append(record)
        parsed.sort(key=lambda record: record.created_at, reverse=True)
        self._records.extend(parsed[: self._limit])

    def _save(self) -> None:
        payload = [
            {
                "created_at": record.created_at.isoformat(timespec="seconds"),
                "title": record.title,
                "message": record.message,
            }
            for record in self.records()
        ]
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(self._path)
        except OSError:
            logger.warning("Could not save notification history", exc_info=True)


def play_notification_sound() -> bool:
    """Play the Windows notification sound, returning whether it was requested."""
    try:
        import winsound
    except ImportError:
        return False
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except (AttributeError, OSError, RuntimeError):
        return False
    return True


__all__ = [
    "MAX_RECORDS",
    "NotificationHistory",
    "NotificationRecord",
    "play_notification_sound",
]
