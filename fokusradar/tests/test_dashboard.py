"""Tests des lokalen Dashboards."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from fokusradar.capture.base import WindowInfo
from fokusradar.dashboard.app import day_context, day_json, week_context
from fokusradar.processing.categories import Categorizer

REGELN = """
standard: rest

kategorien:
  - name: arbeit
    zaehlt_als: fokus
    prozesse: [code.exe]
  - name: ablenkung
    zaehlt_als: ablenkung
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
    return (datetime.now().astimezone() - timedelta(days=1)).date()


@pytest.fixture
def gefuellte_db(database, tag):
    start = datetime.combine(tag, time(9, 0)).astimezone()
    verlauf = [
        (0, 3600, "code.exe", "main.py"),
        (60, 900, "firefox.exe", "Doku – YouTube"),
        (75, 2700, "code.exe", "test.py"),
    ]
    for versatz, dauer, prozess, titel in verlauf:
        beginn = start + timedelta(minutes=versatz)
        event_id = database.open_window_event(WindowInfo(prozess, titel), beginn)
        database.close_window_event(event_id, beginn + timedelta(seconds=dauer))
    return database


def test_tagesansicht_hat_alle_bausteine(gefuellte_db, regeln, config, tag):
    context = day_context(gefuellte_db, regeln, config, tag)

    assert context["tag_iso"] == tag.isoformat()
    assert context["analyse"].has_data
    assert [k["label"] for k in context["kennzahlen"]][0] == "Erfasste Zeit"
    assert {k["name"] for k in context["kategorien"]} == {"arbeit", "ablenkung"}
    assert context["apps"][0]["prozess"] == "code.exe"
    assert len(context["sessions"]) == 2  # durch die 15-Minuten-Ablenkung getrennt
    assert context["zeitstrahl"]["segmente"]
    assert all(0 <= s["links"] <= 100 for s in context["zeitstrahl"]["segmente"])
    assert context["vorschlaege"]  # wurden beim Aufruf gespeichert


def test_tagesansicht_ohne_daten(database, regeln, config, tag):
    context = day_context(database, regeln, config, tag)

    assert not context["analyse"].has_data
    assert context["zeitstrahl"]["segmente"] == []
    assert context["vorschlaege"] == []


def test_wochenansicht_deckt_sieben_tage_ab(gefuellte_db, regeln, config, tag):
    context = week_context(gefuellte_db, regeln, config, tag)

    assert len(context["zeilen"]) == 7
    assert context["zeilen"][-1]["tag"] == tag
    assert not context["zeilen"][-1]["leer"]
    assert context["zeilen"][0]["leer"]
    letzte = context["zeilen"][-1]
    assert 0 <= letzte["fokus"] <= 100
    assert round(letzte["fokus"] + letzte["neutral"] + letzte["ablenkung"]) == 100


def test_json_schnittstelle(gefuellte_db, regeln, config, tag):
    daten = day_json(gefuellte_db, regeln, config, tag)

    assert daten["datum"] == tag.isoformat()
    assert daten["erfasste_sekunden"] == 7200
    assert daten["fokus_sekunden"] == 6300
    assert daten["ablenkung_sekunden"] == 900
    assert daten["kategorien_sekunden"]["arbeit"] == 6300
    assert daten["top_ablenkungen"][0]["prozess"] == "firefox.exe"
    assert len(daten["fokus_sessions"]) == 2


# -- Web-Oberfläche ---------------------------------------------------------

fastapi = pytest.importorskip("fastapi", reason="Dashboard-Extra nicht installiert")
pytest.importorskip("httpx", reason="TestClient benötigt httpx")


@pytest.fixture
def client(gefuellte_db, regeln, config, tmp_path):
    from fastapi.testclient import TestClient

    from fokusradar.dashboard.app import create_app

    gefuellte_db.close()  # die App öffnet die Datenbank selbst
    return TestClient(create_app(config, regeln))


def test_seiten_werden_ausgeliefert(client, tag):
    startseite = client.get("/")
    assert startseite.status_code == 200
    assert "FokusRadar" in startseite.text

    tagesseite = client.get(f"/tag/{tag.isoformat()}")
    assert tagesseite.status_code == 200
    assert "code.exe" in tagesseite.text
    assert "Fokus-Sessions" in tagesseite.text

    wochenseite = client.get(f"/woche?bis={tag.isoformat()}")
    assert wochenseite.status_code == 200
    assert "Die letzten sieben Tage" in wochenseite.text


def test_unsinniges_datum_faellt_auf_heute_zurueck(client):
    antwort = client.get("/tag/kein-datum")
    assert antwort.status_code == 200


def test_json_endpunkt(client, tag):
    antwort = client.get(f"/api/tag/{tag.isoformat()}")
    assert antwort.status_code == 200
    assert antwort.json()["erfasste_sekunden"] == 7200


def test_vorschlag_kann_weggeklickt_werden(client, config, tag):
    from fokusradar.storage.db import Database

    client.get(f"/tag/{tag.isoformat()}")  # legt die Vorschläge des Tages an
    with Database(config.database_path) as database:
        offen = database.suggestions(day=tag)
    assert offen

    antwort = client.post(
        f"/vorschlag/{offen[0].id}/erledigt",
        data={"ziel": f"/tag/{tag.isoformat()}"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303

    with Database(config.database_path) as database:
        assert offen[0].text not in [v.text for v in database.suggestions(day=tag)]


# -- Ausschlussliste im Dashboard -------------------------------------------


def test_ausschlussseite_zeigt_und_pflegt_muster(client, config):
    from fokusradar.storage.db import Database

    seite = client.get("/ausschluss")
    assert seite.status_code == 200
    assert "Ausschlussliste" in seite.text
    assert "keepass" in seite.text.lower()  # aus der Startvorlage übernommen

    antwort = client.post(
        "/ausschluss/hinzufuegen",
        data={"muster": "tresor.exe", "typ": "process"},
        follow_redirects=True,
    )
    assert antwort.status_code == 200
    assert "tresor.exe" in antwort.text

    with Database.from_config(config) as database:
        regel = [r for r in database.exclusions() if r.pattern == "tresor.exe"][0]

    entfernt = client.post(f"/ausschluss/{regel.id}/entfernen", follow_redirects=True)
    assert "Muster entfernt" in entfernt.text
    with Database.from_config(config) as database:
        assert not database.exclusions().excludes("tresor.exe")


def test_leeres_muster_wird_abgewiesen(client, config):
    from fokusradar.storage.db import Database

    with Database.from_config(config) as database:
        vorher = len(database.exclusions())

    antwort = client.post(
        "/ausschluss/hinzufuegen", data={"muster": "   ", "typ": "process"},
        follow_redirects=True,
    )
    assert antwort.status_code == 200
    with Database.from_config(config) as database:
        assert len(database.exclusions()) == vorher


def test_ungueltiger_mustertyp_bleibt_folgenlos(client, config):
    from fokusradar.storage.db import Database

    antwort = client.post(
        "/ausschluss/hinzufuegen", data={"muster": "x.exe", "typ": "quatsch"},
        follow_redirects=True,
    )
    assert antwort.status_code == 200
    with Database.from_config(config) as database:
        assert not database.exclusions().excludes("x.exe")
