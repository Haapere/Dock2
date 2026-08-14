"""Konfiguration von FokusRadar.

Die Einstellungen liegen in einer TOML-Datei (Standard:
``%APPDATA%\\FokusRadar\\config.toml`` unter Windows, sonst
``~/.config/fokusradar/config.toml``). Fehlt die Datei, gelten die Vorgaben aus
diesem Modul — FokusRadar ist also ohne vorherige Einrichtung startklar.

Für Phase 1 sind nur die Abschnitte ``[erfassung]`` und ``[speicher]``
relevant; die Regeldateien ``categories.yaml``/``exclusions.yaml`` aus dem
Bauplan kommen in Phase 2 bzw. 3 dazu.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_TEMPLATE = """\
# FokusRadar — Konfiguration
# Alle Werte sind optional; fehlende Einträge nutzen die Vorgabe.

[erfassung]
# Abstand zwischen zwei Abfragen des aktiven Fensters, in Sekunden (2-5 empfohlen)
intervall_sekunden = 3
# Ab dieser Zeit ohne Maus-/Tastatureingabe gilt die Zeit als Pause
idle_schwelle_sekunden = 300
# Abstand, in dem das Aktivitätslevel (Idle-Sekunden, Eingabe-Frequenz) gespeichert wird
aktivitaets_intervall_sekunden = 60
# Eingabe-Ereignisse zählen (nur die Anzahl, keine Tasteninhalte — kein Keylogging).
# "auto" = einschalten, wenn pynput installiert ist; true/false erzwingen.
eingaben_zaehlen = "auto"
# Fenstertitel mitspeichern. false = nur Prozessnamen (datensparsamer)
fenstertitel_speichern = true

[speicher]
# Pfad zur SQLite-Datenbank; leer = Standardpfad im Benutzerprofil
datenbank = ""

[analyse]
# Ab dieser Dauer gilt ein zusammenhängender Block als Fokus-Session
fokus_mindestdauer_sekunden = 600
# Kurze Abstecher bis zu dieser Länge unterbrechen eine Fokus-Session nicht
unterbrechung_toleranz_sekunden = 60
# Ab so vielen Fensterwechseln pro Stunde weist die Auswertung darauf hin
wechsel_schwelle_pro_stunde = 40
# Ab diesem Anteil Ablenkungszeit (0.2 = 20 %) weist die Auswertung darauf hin
ablenkung_schwelle_anteil = 0.2
# Regeldatei mit den Kategorien; leer = categories.yaml neben dieser Datei
kategorien_datei = ""

[dashboard]
# Adresse der lokalen Weboberfläche (fokusradar dashboard)
host = "127.0.0.1"
port = 8760
"""


@dataclass(frozen=True)
class CaptureConfig:
    """Einstellungen der Erfassungsschleife."""

    interval_seconds: float = 3.0
    idle_threshold_seconds: float = 300.0
    activity_interval_seconds: float = 60.0
    count_input_events: bool | str = "auto"
    store_window_titles: bool = True


@dataclass(frozen=True)
class AnalysisConfig:
    """Einstellungen der lokalen Auswertung (Phase 2)."""

    focus_minimum_seconds: float = 600.0
    interruption_tolerance_seconds: float = 60.0
    switch_rate_threshold: float = 40.0
    distraction_share_threshold: float = 0.2
    categories_path: Path | None = None
    #: Ab so vielen Aufrufen mit kurzer Verweildauer gilt eine App als „Zappel-App".
    short_visit_count: int = 8
    short_visit_seconds: float = 60.0


@dataclass(frozen=True)
class DashboardConfig:
    """Einstellungen der lokalen Weboberfläche (Phase 2)."""

    host: str = "127.0.0.1"
    port: int = 8760


@dataclass(frozen=True)
class Config:
    """Gesamte Konfiguration inklusive Herkunft der Datei."""

    capture: CaptureConfig = field(default_factory=CaptureConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    database_path: Path = field(default_factory=lambda: default_database_path())
    source: Path | None = None

    @property
    def categories_path(self) -> Path:
        """Pfad der Regeldatei: aus der Konfiguration oder neben ihr."""
        if self.analysis.categories_path is not None:
            return self.analysis.categories_path
        base = self.source.parent if self.source is not None else default_config_path().parent
        return base / "categories.yaml"

    def with_overrides(
        self,
        *,
        database_path: Path | None = None,
        interval_seconds: float | None = None,
        idle_threshold_seconds: float | None = None,
    ) -> "Config":
        """Kopie mit Werten aus Kommandozeilen-Optionen."""
        capture = self.capture
        if interval_seconds is not None:
            capture = replace(capture, interval_seconds=interval_seconds)
        if idle_threshold_seconds is not None:
            capture = replace(capture, idle_threshold_seconds=idle_threshold_seconds)
        return replace(
            self,
            capture=capture,
            database_path=database_path or self.database_path,
        )


def _app_data_dir() -> Path:
    """Verzeichnis für veränderliche Daten (Datenbank)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "FokusRadar"
        return Path.home() / "AppData" / "Local" / "FokusRadar"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "fokusradar"
    return Path.home() / ".local" / "share" / "fokusradar"


def _config_dir() -> Path:
    """Verzeichnis der Konfigurationsdatei."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "FokusRadar"
        return Path.home() / "AppData" / "Roaming" / "FokusRadar"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "fokusradar"
    return Path.home() / ".config" / "fokusradar"


def default_database_path() -> Path:
    """Standardpfad der lokalen Datenbank."""
    override = os.environ.get("FOKUSRADAR_DB")
    if override:
        return Path(override).expanduser()
    return _app_data_dir() / "fokusradar.db"


def default_config_path() -> Path:
    """Standardpfad der Konfigurationsdatei."""
    override = os.environ.get("FOKUSRADAR_CONFIG")
    if override:
        return Path(override).expanduser()
    return _config_dir() / "config.toml"


def _positive_number(section: dict[str, Any], key: str, fallback: float) -> float:
    value = section.get(key, fallback)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"'{key}' muss eine Zahl sein, gefunden: {value!r}")
    if value <= 0:
        raise ConfigError(f"'{key}' muss größer als 0 sein, gefunden: {value!r}")
    return float(value)


def _boolean(section: dict[str, Any], key: str, fallback: bool) -> bool:
    value = section.get(key, fallback)
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' muss true oder false sein, gefunden: {value!r}")
    return value


class ConfigError(ValueError):
    """Fehlerhafte Konfigurationsdatei."""


def load_config(path: Path | None = None) -> Config:
    """Konfiguration laden. Fehlt die Datei, gelten die Vorgabewerte."""
    config_path = Path(path).expanduser() if path else default_config_path()
    if not config_path.is_file():
        return Config()

    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path} ist kein gültiges TOML: {exc}") from exc

    capture_section = raw.get("erfassung", {})
    if not isinstance(capture_section, dict):
        raise ConfigError("Abschnitt [erfassung] muss eine Tabelle sein")
    storage_section = raw.get("speicher", {})
    if not isinstance(storage_section, dict):
        raise ConfigError("Abschnitt [speicher] muss eine Tabelle sein")

    count_input = capture_section.get("eingaben_zaehlen", "auto")
    if isinstance(count_input, str):
        if count_input.lower() != "auto":
            raise ConfigError(
                "'eingaben_zaehlen' muss true, false oder \"auto\" sein, "
                f"gefunden: {count_input!r}"
            )
        count_input = "auto"
    elif not isinstance(count_input, bool):
        raise ConfigError(
            f"'eingaben_zaehlen' muss true, false oder \"auto\" sein, gefunden: {count_input!r}"
        )

    capture = CaptureConfig(
        interval_seconds=_positive_number(capture_section, "intervall_sekunden", 3.0),
        idle_threshold_seconds=_positive_number(
            capture_section, "idle_schwelle_sekunden", 300.0
        ),
        activity_interval_seconds=_positive_number(
            capture_section, "aktivitaets_intervall_sekunden", 60.0
        ),
        count_input_events=count_input,
        store_window_titles=_boolean(capture_section, "fenstertitel_speichern", True),
    )

    database_raw = storage_section.get("datenbank", "")
    if not isinstance(database_raw, str):
        raise ConfigError("'datenbank' muss ein Pfad als Text sein")
    database_path = (
        Path(database_raw).expanduser() if database_raw.strip() else default_database_path()
    )

    analysis_section = raw.get("analyse", {})
    if not isinstance(analysis_section, dict):
        raise ConfigError("Abschnitt [analyse] muss eine Tabelle sein")
    categories_raw = analysis_section.get("kategorien_datei", "")
    if not isinstance(categories_raw, str):
        raise ConfigError("'kategorien_datei' muss ein Pfad als Text sein")
    share = _positive_number(analysis_section, "ablenkung_schwelle_anteil", 0.2)
    if share > 1:
        raise ConfigError(
            f"'ablenkung_schwelle_anteil' ist ein Anteil zwischen 0 und 1, "
            f"gefunden: {share!r}"
        )
    analysis = AnalysisConfig(
        focus_minimum_seconds=_positive_number(
            analysis_section, "fokus_mindestdauer_sekunden", 600.0
        ),
        interruption_tolerance_seconds=_positive_number(
            analysis_section, "unterbrechung_toleranz_sekunden", 60.0
        ),
        switch_rate_threshold=_positive_number(
            analysis_section, "wechsel_schwelle_pro_stunde", 40.0
        ),
        distraction_share_threshold=share,
        categories_path=(
            Path(categories_raw).expanduser() if categories_raw.strip() else None
        ),
    )

    dashboard_section = raw.get("dashboard", {})
    if not isinstance(dashboard_section, dict):
        raise ConfigError("Abschnitt [dashboard] muss eine Tabelle sein")
    host = dashboard_section.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host.strip():
        raise ConfigError(f"'host' muss eine Adresse als Text sein, gefunden: {host!r}")
    port = dashboard_section.get("port", 8760)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError(f"'port' muss zwischen 1 und 65535 liegen, gefunden: {port!r}")
    dashboard = DashboardConfig(host=host.strip(), port=port)

    return Config(
        capture=capture,
        analysis=analysis,
        dashboard=dashboard,
        database_path=database_path,
        source=config_path,
    )


def write_default_config(path: Path | None = None, *, overwrite: bool = False) -> Path:
    """Vorlage der Konfigurationsdatei anlegen und ihren Pfad zurückgeben."""
    config_path = Path(path).expanduser() if path else default_config_path()
    if config_path.exists() and not overwrite:
        raise FileExistsError(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    return config_path
