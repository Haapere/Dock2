"""Tests der lokalen Auswertung."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from fokusradar.capture.base import WindowInfo
from fokusradar.config import AnalysisConfig
from fokusradar.processing.analysis import analyze_day, last_days, store_analysis
from fokusradar.processing.categories import Categorizer

REGELN = """
standard: rest

kategorien:
  - name: arbeit
    zaehlt_als: fokus
    prozesse: [code.exe]
  - name: ablenkung
    zaehlt_als: ablenkung
    prozesse: [steam.exe]
    titel: [youtube]
  - name: rest
    zaehlt_als: neutral
    prozesse: [slack.exe, firefox.exe]
"""


@pytest.fixture
def regeln() -> Categorizer:
    return Categorizer.from_yaml(REGELN)


@pytest.fixture
def tag():
    """Ein fester Tag; Beginn 09:00 Ortszeit."""
    return (datetime.now().astimezone() - timedelta(days=1)).date()


def _beginn(tag) -> datetime:
    return datetime.combine(tag, time(9, 0)).astimezone()


def eintragen(database, tag, verlauf: list[tuple[int, int, str, str | None]]) -> None:
    """Verlauf als Fensternutzungen speichern.

    Jeder Eintrag: (Minuten nach 09:00, Dauer in Sekunden, Prozess, Titel).
    """
    start = _beginn(tag)
    for versatz, dauer, prozess, titel in verlauf:
        beginn = start + timedelta(minutes=versatz)
        event_id = database.open_window_event(WindowInfo(prozess, titel), beginn)
        database.close_window_event(event_id, beginn + timedelta(seconds=dauer))


def test_kennzahlen_eines_tages(database, regeln, tag):
    eintragen(
        database,
        tag,
        [
            (0, 3600, "code.exe", "main.py"),          # 60 min Fokus
            (60, 900, "firefox.exe", "Doku – YouTube"),  # 15 min Ablenkung
            (75, 300, "slack.exe", "#team"),             # 5 min neutral
        ],
    )
    analyse = analyze_day(database, regeln, tag)

    assert analyse.total_seconds == 4800
    assert analyse.focus_seconds == 3600
    assert analyse.distraction_seconds == 900
    assert analyse.switches == 3
    assert analyse.category_seconds == {"arbeit": 3600, "ablenkung": 900, "rest": 300}
    assert round(analyse.focus_share, 3) == 0.75
    assert analyse.active_minutes == 80
    assert [app.process_name for app in analyse.apps] == [
        "code.exe",
        "firefox.exe",
        "slack.exe",
    ]
    assert [app.process_name for app in analyse.top_distractions] == ["firefox.exe"]


def test_kategorien_werden_rueckwirkend_gespeichert(database, regeln, tag):
    eintragen(database, tag, [(0, 600, "code.exe", None)])
    # Vor der Auswertung steht noch keine Kategorie in der Datenbank.
    assert database.window_events(day=tag)[0].category is None

    analyze_day(database, regeln, tag)
    assert database.window_events(day=tag)[0].category == "arbeit"


def test_kurze_unterbrechung_teilt_die_fokus_session_nicht(database, regeln, tag):
    eintragen(
        database,
        tag,
        [
            (0, 1800, "code.exe", None),      # 30 min
            (30, 30, "slack.exe", "#team"),   # 30 s Blick in den Chat
            (31, 1740, "code.exe", None),     # weitere 29 min
        ],
    )
    analyse = analyze_day(database, regeln, tag)

    assert len(analyse.focus_sessions) == 1
    session = analyse.focus_sessions[0]
    assert session.focus_seconds == 3540  # nur die Editor-Zeit zählt
    assert session.interruptions == 1
    assert session.main_process == "code.exe"


def test_lange_unterbrechung_trennt_die_sessions(database, regeln, tag):
    eintragen(
        database,
        tag,
        [
            (0, 1200, "code.exe", None),                  # 20 min
            (20, 1200, "firefox.exe", "Doku – YouTube"),  # 20 min Ablenkung
            (40, 1200, "code.exe", None),                 # 20 min
        ],
    )
    analyse = analyze_day(database, regeln, tag)

    assert [s.focus_seconds for s in analyse.focus_sessions] == [1200, 1200]
    assert analyse.longest_focus_seconds == 1200


def test_zu_kurze_bloecke_sind_keine_fokus_session(database, regeln, tag):
    eintragen(database, tag, [(0, 300, "code.exe", None), (30, 300, "code.exe", None)])
    analyse = analyze_day(database, regeln, tag)

    assert analyse.focus_sessions == []
    assert analyse.focus_seconds == 600  # als Fokuszeit zählt es trotzdem


def test_mindestdauer_ist_einstellbar(database, regeln, tag):
    eintragen(database, tag, [(0, 300, "code.exe", None)])
    streng = analyze_day(database, regeln, tag, AnalysisConfig())
    locker = analyze_day(
        database, regeln, tag, AnalysisConfig(focus_minimum_seconds=120)
    )

    assert streng.focus_sessions == []
    assert len(locker.focus_sessions) == 1


def test_leerer_tag_liefert_nullwerte(database, regeln, tag):
    analyse = analyze_day(database, regeln, tag)

    assert not analyse.has_data
    assert analyse.total_seconds == 0
    assert analyse.switches_per_hour == 0.0
    assert analyse.focus_share == 0.0
    assert analyse.suggestions == []


def test_vorschlag_bei_vielen_wechseln(database, regeln, tag):
    verlauf = [(minute, 55, "code.exe", None) for minute in range(0, 120)]
    eintragen(database, tag, verlauf)
    analyse = analyze_day(database, regeln, tag)

    assert analyse.switches_per_hour > 40
    assert any("Fensterwechsel pro Stunde" in text for text in analyse.suggestions)


def test_vorschlag_bei_viel_ablenkung(database, regeln, tag):
    eintragen(
        database,
        tag,
        [
            (0, 3600, "code.exe", None),
            (60, 3600, "firefox.exe", "Doku – YouTube"),
        ],
    )
    analyse = analyze_day(database, regeln, tag)

    ablenkung = [text for text in analyse.suggestions if "Ablenkungen" in text]
    assert ablenkung and "firefox.exe" in ablenkung[0]


def test_vorschlag_bei_haeufigen_kurzbesuchen(database, regeln, tag):
    verlauf = [(0, 3600, "code.exe", None)]
    verlauf += [(60 + i * 2, 20, "slack.exe", "#team") for i in range(12)]
    verlauf += [(120, 3600, "code.exe", None)]
    eintragen(database, tag, verlauf)
    analyse = analyze_day(database, regeln, tag)

    assert any("slack.exe" in text and "geöffnet" in text for text in analyse.suggestions)


def test_lob_bei_gutem_tag(database, regeln, tag):
    eintragen(database, tag, [(0, 7200, "code.exe", None), (120, 1200, "slack.exe", None)])
    analyse = analyze_day(database, regeln, tag)

    assert analyse.suggestions and "Guter Tag" in analyse.suggestions[0]


def test_hoechstens_drei_vorschlaege(database, regeln, tag):
    verlauf = [(minute, 55, "steam.exe", None) for minute in range(0, 180)]
    eintragen(database, tag, verlauf)
    analyse = analyze_day(database, regeln, tag)

    assert 0 < len(analyse.suggestions) <= 3


def test_kurze_tage_bekommen_keine_vorschlaege(database, regeln, tag):
    eintragen(database, tag, [(0, 600, "steam.exe", None)])
    assert analyze_day(database, regeln, tag).suggestions == []


def test_zusammenfassung_wird_gespeichert_und_aktualisiert(database, regeln, tag):
    eintragen(
        database,
        tag,
        [(0, 3600, "code.exe", None), (60, 3600, "firefox.exe", "Doku – YouTube")],
    )
    analyse = analyze_day(database, regeln, tag)
    store_analysis(database, analyse)

    gespeichert = database.daily_summary(tag)
    assert gespeichert["total_active_minutes"] == 120
    assert gespeichert["category_breakdown"] == {"arbeit": 3600, "ablenkung": 3600}
    assert gespeichert["top_distractions"][0]["prozess"] == "firefox.exe"

    vorschlaege = database.suggestions(day=tag)
    assert vorschlaege and all(v.source == "local" for v in vorschlaege)

    # Zweiter Lauf: keine Dubletten, keine zweite Zeile in daily_summaries.
    store_analysis(database, analyze_day(database, regeln, tag))
    assert len(database.suggestions(day=tag)) == len(vorschlaege)
    assert database.table_counts()["daily_summaries"] == 1


def test_weggeklickte_vorschlaege_kommen_nicht_zurueck(database, regeln, tag):
    eintragen(
        database,
        tag,
        [(0, 3600, "code.exe", None), (60, 3600, "firefox.exe", "Doku – YouTube")],
    )
    store_analysis(database, analyze_day(database, regeln, tag))
    erster = database.suggestions(day=tag)[0]
    assert database.dismiss_suggestion(erster.id)

    store_analysis(database, analyze_day(database, regeln, tag))
    offen = database.suggestions(day=tag)
    assert erster.text not in [v.text for v in offen]
    assert erster.text in [v.text for v in database.suggestions(day=tag, include_dismissed=True)]


def test_letzte_tage_sind_aufsteigend(tag):
    tage = last_days(tag, 7)
    assert len(tage) == 7
    assert tage[-1] == tag
    assert tage == sorted(tage)


def test_laufende_nutzung_zaehlt_mit_ihrer_bisherigen_zeit(database, regeln, tag):
    """Das gerade aktive Fenster darf in der Auswertung nicht mit 0 auftauchen."""
    beginn = _beginn(tag)
    event_id = database.open_window_event(WindowInfo("code.exe", "main.py"), beginn)
    database.touch_window_event(event_id, beginn + timedelta(seconds=1500))

    analyse = analyze_day(database, regeln, tag)
    assert analyse.total_seconds == 1500
    assert analyse.focus_seconds == 1500
    assert [app.seconds for app in analyse.apps] == [1500]
    assert database.app_totals(tag)[0].seconds == 1500
