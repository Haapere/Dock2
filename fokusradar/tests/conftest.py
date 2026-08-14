"""Gemeinsame Attrappen für die Tests.

Die Erfassung wird durchgehend mit steuerbaren Backends und einer festen Uhr
getestet — damit laufen die Tests auf jedem System, auch ohne Bildschirm.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fokusradar.capture.base import WindowInfo
from fokusradar.config import CaptureConfig, Config
from fokusradar.storage.db import Database

START = datetime(2026, 8, 13, 8, 0, 0, tzinfo=timezone.utc)


class FakeWindowBackend:
    """Liefert das Fenster, das der Test gerade gesetzt hat."""

    name = "fake"

    def __init__(self, info: WindowInfo | None = None) -> None:
        self.info = info
        self.calls = 0

    def set(self, process_name: str | None, title: str | None = None) -> None:
        self.info = None if process_name is None else WindowInfo(process_name, title)

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str | None:
        return None

    def snapshot(self) -> WindowInfo | None:
        self.calls += 1
        return self.info


class FakeIdleBackend:
    """Meldet die Idle-Sekunden, die der Test vorgibt."""

    name = "fake"

    def __init__(self, seconds: float | None = 0.0) -> None:
        self.seconds = seconds

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str | None:
        return None

    def idle_seconds(self) -> float | None:
        return self.seconds


class FakeInputCounter:
    """Zählt, was der Test hineinschreibt."""

    name = "fake"

    def __init__(self, per_take: int = 7) -> None:
        self.per_take = per_take
        self.started = False

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str | None:
        return None

    def start(self) -> bool:
        self.started = True
        return True

    def stop(self) -> None:
        self.started = False

    def take(self) -> int:
        return self.per_take


class Clock:
    """Testuhr: schreitet nur voran, wenn der Test es sagt."""

    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def advance(self, seconds: float) -> datetime:
        self.now = self.now + timedelta(seconds=seconds)
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(
        capture=CaptureConfig(
            interval_seconds=1.0,
            idle_threshold_seconds=300.0,
            activity_interval_seconds=60.0,
            count_input_events=False,
        ),
        database_path=tmp_path / "fokusradar.db",
    )


@pytest.fixture
def database(config) -> Database:
    with Database(config.database_path) as db:
        yield db


class FakeScreenshotBackend:
    """Legt statt eines Bildschirmfotos eine Platzhalterdatei an."""

    name = "fake"

    def __init__(self, *, works: bool = True) -> None:
        self.works = works
        self.captures: list[Path] = []

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str | None:
        return None if self.works else "Attrappe soll scheitern"

    def capture(self, target: Path) -> Path | None:
        if not self.works:
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PNG-Attrappe")
        self.captures.append(target)
        return target


class FakeOcrBackend:
    """Liefert immer denselben erkannten Text."""

    name = "fake"

    def __init__(self, text: str | None = "Kostenstelle 4711\n\n   Angebot   ") -> None:
        self.result = text
        self.calls = 0

    def available(self) -> bool:
        return True

    def unavailable_reason(self) -> str | None:
        return None

    def text(self, image: Path) -> str | None:
        self.calls += 1
        return self.result
