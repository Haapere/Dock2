"""Tests der Kategorisierung."""

from __future__ import annotations

import pytest

from fokusradar.processing.categories import (
    DEFAULT_CATEGORIES_YAML,
    Categorizer,
    CategoryError,
    write_default_categories,
)

REGELN = """
standard: rest

kategorien:
  - name: arbeit
    zaehlt_als: fokus
    prozesse: [code.exe, "pycharm*.exe"]
    titel: [stack overflow]

  - name: ablenkung
    zaehlt_als: ablenkung
    prozesse: [steam.exe]
    titel: [youtube, "*tiktok*"]

  - name: rest
    zaehlt_als: neutral
    prozesse: [firefox.exe]
"""


@pytest.fixture
def regeln() -> Categorizer:
    return Categorizer.from_yaml(REGELN)


def test_prozess_und_platzhalter(regeln):
    assert regeln.categorize("code.exe") == "arbeit"
    assert regeln.categorize("PyCharm64.exe") == "arbeit"  # Groß-/Kleinschreibung egal
    assert regeln.categorize("steam.exe") == "ablenkung"
    assert regeln.categorize("firefox.exe") == "rest"


def test_unbekanntes_programm_bekommt_die_standardkategorie(regeln):
    assert regeln.categorize("irgendwas.exe") == "rest"


def test_titel_schlaegt_prozess(regeln):
    # Derselbe Browser landet je nach Inhalt in verschiedenen Kategorien.
    assert regeln.categorize("firefox.exe", "Katzenvideos – YouTube") == "ablenkung"
    assert regeln.categorize("firefox.exe", "sqlite wal – Stack Overflow") == "arbeit"
    assert regeln.categorize("firefox.exe", "Wetterbericht") == "rest"


def test_titelmuster_mit_platzhalter(regeln):
    assert regeln.categorize("firefox.exe", "Startseite | TikTok | Neu") == "ablenkung"


def test_art_der_kategorie(regeln):
    assert regeln.is_focus("arbeit")
    assert regeln.is_distraction("ablenkung")
    assert regeln.kind_of("rest") == "neutral"
    assert regeln.kind_of(None) == "neutral"
    assert regeln.kind_of("gibtsnicht") == "neutral"


def test_eingebaute_regeln_sind_gueltig():
    regeln = Categorizer.default_rules()
    assert regeln.categorize("code.exe") == "entwicklung"
    assert regeln.categorize("chrome.exe", "Doku – YouTube") == "ablenkung"
    assert regeln.categorize("slack.exe") == "kommunikation"
    assert regeln.categorize("völlig.unbekannt") == regeln.default
    assert "fokus" in {c.kind for c in regeln.categories}


def test_datei_wird_geladen_und_fehlende_datei_faellt_zurueck(tmp_path):
    pfad = tmp_path / "categories.yaml"
    pfad.write_text(REGELN, encoding="utf-8")

    aus_datei = Categorizer.load(pfad)
    assert aus_datei.source == pfad
    assert aus_datei.names == ["arbeit", "ablenkung", "rest"]

    eingebaut = Categorizer.load(tmp_path / "gibtsnicht.yaml")
    assert eingebaut.source is None
    assert eingebaut.names == Categorizer.default_rules().names


@pytest.mark.parametrize(
    "inhalt, teil",
    [
        ("kategorien: []\n", "fehlt oder ist leer"),
        ("kategorien:\n  - zaehlt_als: fokus\n", "ohne gültigen 'name'"),
        ("kategorien:\n  - name: a\n    zaehlt_als: quatsch\n", "zaehlt_als"),
        ("kategorien:\n  - name: a\n    prozesse: nichtsliste\n", "muss eine Liste sein"),
        ("kategorien:\n  - name: a\n    prozesse: [1]\n", "kein gültiges Muster"),
        ("standard: fehlt\nkategorien:\n  - name: a\n", "vorhandene Kategorie"),
        ("kategorien: [\n", "kein gültiges YAML"),
        ("- eine\n- liste\n", "Zuordnung auf oberster Ebene"),
    ],
)
def test_fehlerhafte_regeln_melden_klartext(inhalt, teil):
    with pytest.raises(CategoryError) as fehler:
        Categorizer.from_yaml(inhalt)
    assert teil in str(fehler.value)


def test_regeldatei_anlegen(tmp_path):
    pfad = write_default_categories(tmp_path / "categories.yaml")
    assert pfad.read_text(encoding="utf-8") == DEFAULT_CATEGORIES_YAML
    with pytest.raises(FileExistsError):
        write_default_categories(pfad)
    write_default_categories(pfad, overwrite=True)


def test_beispieldatei_entspricht_den_eingebauten_regeln():
    from pathlib import Path

    beispiel = Path(__file__).resolve().parent.parent / "config" / "categories.yaml"
    assert beispiel.read_text(encoding="utf-8") == DEFAULT_CATEGORIES_YAML
