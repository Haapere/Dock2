"""Tests der Konfiguration."""

from __future__ import annotations

from pathlib import Path

import pytest

from fokusradar.config import (
    Config,
    ConfigError,
    default_config_path,
    default_database_path,
    load_config,
    write_default_config,
)


def test_ohne_datei_gelten_vorgabewerte(tmp_path):
    config = load_config(tmp_path / "gibtsnicht.toml")
    assert config.source is None
    assert config.capture.interval_seconds == 3.0
    assert config.capture.idle_threshold_seconds == 300.0
    assert config.capture.store_window_titles is True


def test_werte_werden_gelesen(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[erfassung]
intervall_sekunden = 5
idle_schwelle_sekunden = 120
aktivitaets_intervall_sekunden = 30
eingaben_zaehlen = false
fenstertitel_speichern = false

[speicher]
datenbank = "daten/eigene.db"
""",
        encoding="utf-8",
    )
    config = load_config(path)

    assert config.source == path
    assert config.capture.interval_seconds == 5.0
    assert config.capture.idle_threshold_seconds == 120.0
    assert config.capture.activity_interval_seconds == 30.0
    assert config.capture.count_input_events is False
    assert config.capture.store_window_titles is False
    assert config.database_path == Path("daten/eigene.db")


def test_leerer_datenbankpfad_faellt_auf_vorgabe_zurueck(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[speicher]\ndatenbank = ""\n', encoding="utf-8")
    assert load_config(path).database_path == default_database_path()


@pytest.mark.parametrize(
    "inhalt, teil",
    [
        ("[erfassung]\nintervall_sekunden = 0\n", "größer als 0"),
        ("[erfassung]\nintervall_sekunden = \"schnell\"\n", "muss eine Zahl sein"),
        ("[erfassung]\nfenstertitel_speichern = 1\n", "true oder false"),
        ("[erfassung]\neingaben_zaehlen = \"vielleicht\"\n", "true, false"),
        ("[erfassung]\nintervall_sekunden = \n", "kein gültiges TOML"),
    ],
)
def test_fehlerhafte_werte_melden_klartext(tmp_path, inhalt, teil):
    path = tmp_path / "config.toml"
    path.write_text(inhalt, encoding="utf-8")
    with pytest.raises(ConfigError) as fehler:
        load_config(path)
    assert teil in str(fehler.value)


def test_vorlage_anlegen_und_wieder_einlesen(tmp_path):
    path = write_default_config(tmp_path / "unterordner" / "config.toml")
    assert path.is_file()

    config = load_config(path)
    assert config.capture.interval_seconds == 3.0
    assert config.capture.count_input_events == "auto"

    with pytest.raises(FileExistsError):
        write_default_config(path)
    write_default_config(path, overwrite=True)  # ausdrücklich erlaubt


def test_kommandozeile_ueberschreibt_konfiguration(tmp_path):
    config = Config().with_overrides(
        database_path=tmp_path / "andere.db",
        interval_seconds=10.0,
        idle_threshold_seconds=60.0,
    )
    assert config.database_path == tmp_path / "andere.db"
    assert config.capture.interval_seconds == 10.0
    assert config.capture.idle_threshold_seconds == 60.0
    # Nicht überschriebene Werte bleiben unverändert.
    assert config.capture.activity_interval_seconds == 60.0


def test_umgebungsvariablen_setzen_die_pfade(tmp_path, monkeypatch):
    monkeypatch.setenv("FOKUSRADAR_DB", str(tmp_path / "env.db"))
    monkeypatch.setenv("FOKUSRADAR_CONFIG", str(tmp_path / "env.toml"))
    assert default_database_path() == tmp_path / "env.db"
    assert default_config_path() == tmp_path / "env.toml"


def test_beispieldatei_entspricht_der_vorlage():
    """config/fokusradar.example.toml muss zur eingebauten Vorlage passen."""
    from fokusradar.config import DEFAULT_CONFIG_TEMPLATE

    beispiel = Path(__file__).resolve().parent.parent / "config" / "fokusradar.example.toml"
    assert beispiel.read_text(encoding="utf-8") == DEFAULT_CONFIG_TEMPLATE
