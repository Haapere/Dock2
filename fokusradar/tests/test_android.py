"""Tests des Android-Begleiters (Phase 5).

Geprüft werden die Gegenstelle (Prüfen und Übernehmen der Zahlen), der
Sync-Endpunkt des Dashboards samt Token-Schutz und der Befehl
``fokusradar android``. Ein echtes Handy braucht dafür niemand.
"""

from __future__ import annotations

import dataclasses
import os
from datetime import date, datetime, timezone

import pytest

from fokusradar.android import sync
from fokusradar.config import AndroidConfig, DashboardConfig
from fokusradar.processing.categories import Categorizer

HEUTE = date(2026, 8, 14)
SYNC_ZEIT = datetime(2026, 8, 14, 20, 30, tzinfo=timezone.utc)

REGELN = """
standard: rest

kategorien:
  - name: ablenkung
    zaehlt_als: ablenkung
    prozesse: [com.instagram.android]
  - name: rest
    zaehlt_als: neutral
    prozesse: ["com.android.*"]
"""


def nachricht(**anders) -> dict:
    """Eine gültige Übertragung, die einzelne Tests abwandeln können."""
    daten = {
        "geraet": "Pixel-7",
        "tage": [
            {
                "datum": HEUTE.isoformat(),
                "apps": [
                    {
                        "paket": "com.instagram.android",
                        "name": "Instagram",
                        "sekunden": 1830,
                        "oeffnungen": 24,
                    },
                    {
                        "paket": "com.android.settings",
                        "name": "Einstellungen",
                        "sekunden": 120,
                        "oeffnungen": 3,
                    },
                ],
            }
        ],
    }
    daten.update(anders)
    return daten


@pytest.fixture
def regeln() -> Categorizer:
    return Categorizer.from_yaml(REGELN)


# -- Token -------------------------------------------------------------------


def test_token_ist_lang_genug_und_jedes_mal_neu():
    erstes = sync.generate_token()
    assert len(erstes) >= 24
    assert erstes != sync.generate_token()


@pytest.mark.parametrize(
    "kopf, erwartet",
    [
        ("Bearer geheim", "geheim"),
        ("bearer geheim", "geheim"),
        ("  Bearer   geheim  ", "geheim"),
        ("geheim", "geheim"),
        (None, ""),
        ("", ""),
    ],
)
def test_token_aus_kopfzeile(kopf, erwartet):
    assert sync.token_from_header(kopf) == erwartet


def test_token_pruefung():
    assert sync.check_token("geheim", "geheim")
    assert sync.check_token("geheim", " geheim ")
    assert not sync.check_token("geheim", "falsch")
    assert not sync.check_token("geheim", None)
    # Ohne hinterlegtes Geheimnis kommt niemand herein — auch nicht mit leerem.
    assert not sync.check_token("", "")


# -- Übertragung lesen -------------------------------------------------------


def test_gueltige_uebertragung_wird_gelesen():
    anfrage = sync.parse_payload(nachricht())

    assert anfrage.device == "Pixel-7"
    assert len(anfrage.days) == 1
    assert anfrage.app_count == 2
    tag = anfrage.days[0]
    assert tag.day == HEUTE
    assert tag.seconds == 1950
    # Längste Nutzung zuerst — das ist die Reihenfolge, die zählt.
    assert tag.entries[0]["package"] == "com.instagram.android"
    assert tag.entries[0]["label"] == "Instagram"
    assert tag.entries[0]["opens"] == 24


def test_ungenutzte_apps_fallen_weg():
    anfrage = sync.parse_payload(
        nachricht(
            tage=[
                {
                    "datum": HEUTE.isoformat(),
                    "apps": [
                        {"paket": "com.beispiel.nie", "sekunden": 0, "oeffnungen": 0},
                        {"paket": "  ", "sekunden": 99},
                        {"paket": "com.beispiel.kurz", "sekunden": 0, "oeffnungen": 2},
                    ],
                }
            ]
        )
    )
    assert [eintrag["package"] for eintrag in anfrage.days[0].entries] == [
        "com.beispiel.kurz"
    ]


def test_zu_viele_apps_werden_gekappt():
    apps = [
        {"paket": f"com.beispiel.a{nummer}", "sekunden": nummer + 1}
        for nummer in range(sync.MAX_APPS_PER_DAY + 20)
    ]
    anfrage = sync.parse_payload(
        nachricht(tage=[{"datum": HEUTE.isoformat(), "apps": apps}])
    )
    eintraege = anfrage.days[0].entries
    assert len(eintraege) == sync.MAX_APPS_PER_DAY
    # Gekappt wird der kurze Schwanz, nicht die längste Nutzung.
    assert eintraege[0]["seconds"] == len(apps)


def test_lange_texte_werden_gekuerzt():
    anfrage = sync.parse_payload(
        nachricht(
            geraet="G" * 200,
            tage=[
                {
                    "datum": HEUTE.isoformat(),
                    "apps": [{"paket": "com.x", "name": "N" * 500, "sekunden": 5}],
                }
            ],
        )
    )
    assert len(anfrage.device) == sync.MAX_DEVICE_LENGTH
    assert len(anfrage.days[0].entries[0]["label"]) == sync.MAX_LABEL_LENGTH


@pytest.mark.parametrize(
    "daten, teil",
    [
        ("keine Zuordnung", "JSON-Objekt"),
        ({"tage": [{"datum": "2026-08-14"}]}, "geraet"),
        ({"geraet": "P", "tage": []}, "tage"),
        ({"geraet": "P", "tage": [{"apps": []}]}, "datum"),
        ({"geraet": "P", "tage": [{"datum": "vorgestern"}]}, "gültiges Datum"),
        ({"geraet": "P", "tage": [{"datum": "2026-08-14", "apps": {}}]}, "Liste"),
        (
            {
                "geraet": "P",
                "tage": [
                    {"datum": "2026-08-14", "apps": [{"paket": "x", "sekunden": "viel"}]}
                ],
            },
            "Zahl",
        ),
    ],
)
def test_fehlerhafte_uebertragung_wird_abgelehnt(daten, teil):
    with pytest.raises(sync.SyncError) as fehler:
        sync.parse_payload(daten)
    assert teil in str(fehler.value)
    assert fehler.value.status == 400


def test_zu_viele_tage_werden_abgelehnt():
    tage = [
        {"datum": date(2026, 1, 1).isoformat(), "apps": []}
        for _ in range(sync.MAX_DAYS + 1)
    ]
    with pytest.raises(sync.SyncError):
        sync.parse_payload(nachricht(tage=tage))


# -- Übernehmen --------------------------------------------------------------


def test_uebernehmen_speichert_und_kategorisiert(database, regeln):
    anfrage = sync.parse_payload(nachricht())
    bericht = sync.apply_sync(database, anfrage, categorizer=regeln, now=SYNC_ZEIT)

    assert bericht["gespeichert"] == 2
    assert bericht["tage"][0] == {
        "datum": HEUTE.isoformat(),
        "apps": 2,
        "sekunden": 1950,
    }

    eintraege = database.android_usage(day=HEUTE)
    assert [eintrag.category for eintrag in eintraege] == ["ablenkung", "rest"]
    assert database.android_day_seconds(HEUTE) == 1950
    assert database.android_devices() == [("Pixel-7", SYNC_ZEIT, HEUTE)]


def test_erneuter_sync_ersetzt_den_tag(database, regeln):
    sync.apply_sync(
        database, sync.parse_payload(nachricht()), categorizer=regeln, now=SYNC_ZEIT
    )
    zweite = nachricht(
        tage=[
            {
                "datum": HEUTE.isoformat(),
                "apps": [
                    {"paket": "com.instagram.android", "name": "Instagram",
                     "sekunden": 3600, "oeffnungen": 40}
                ],
            }
        ]
    )
    sync.apply_sync(
        database, sync.parse_payload(zweite), categorizer=regeln, now=SYNC_ZEIT
    )

    eintraege = database.android_usage(day=HEUTE)
    # Der neue Stand überschreibt, die übrigen Apps bleiben unangetastet stehen.
    assert eintraege[0].seconds == 3600
    assert eintraege[0].opens == 40
    assert len(eintraege) == 2


def test_zwei_geraete_zaehlen_getrennt(database, regeln):
    sync.apply_sync(
        database, sync.parse_payload(nachricht()), categorizer=regeln, now=SYNC_ZEIT
    )
    sync.apply_sync(
        database,
        sync.parse_payload(nachricht(geraet="Tablet")),
        categorizer=regeln,
        now=SYNC_ZEIT,
    )

    assert {name for name, _sync, _tag in database.android_devices()} == {
        "Pixel-7",
        "Tablet",
    }
    assert len(database.android_usage(day=HEUTE, device="Tablet")) == 2
    assert database.android_day_seconds(HEUTE) == 2 * 1950


# -- Endpunkt im Dashboard ---------------------------------------------------

pytest.importorskip("fastapi", reason="Dashboard-Tests brauchen FastAPI")
pytest.importorskip("httpx", reason="TestClient benötigt httpx")


def _client(config, regeln):
    from fastapi.testclient import TestClient

    from fokusradar.dashboard.app import create_app

    return TestClient(create_app(config, regeln), raise_server_exceptions=False)


@pytest.fixture
def sync_config(config):
    return dataclasses.replace(
        config, android=AndroidConfig(enabled=True, token="geheim-123")
    )


def test_endpunkt_gibt_es_nur_wenn_eingeschaltet(config, regeln):
    antwort = _client(config, regeln).post(
        "/api/android/nutzung",
        json=nachricht(),
        headers={"Authorization": "Bearer egal"},
    )
    assert antwort.status_code == 404


def test_ohne_token_kein_zugang(sync_config, regeln):
    client = _client(sync_config, regeln)
    assert client.post("/api/android/nutzung", json=nachricht()).status_code == 401
    assert (
        client.post(
            "/api/android/nutzung",
            json=nachricht(),
            headers={"Authorization": "Bearer falsch"},
        ).status_code
        == 401
    )


def test_eingeschaltet_ohne_hinterlegtes_token(config, regeln):
    offen = dataclasses.replace(config, android=AndroidConfig(enabled=True, token=""))
    antwort = _client(offen, regeln).get(
        "/api/android/status", headers={"Authorization": "Bearer irgendwas"}
    )
    assert antwort.status_code == 503
    assert "token-neu" in antwort.json()["detail"]


def test_sync_ueber_den_endpunkt(sync_config, regeln):
    client = _client(sync_config, regeln)
    kopf = {"Authorization": "Bearer geheim-123"}

    status = client.get("/api/android/status", headers=kopf)
    assert status.status_code == 200
    assert status.json()["status"] == "ok"

    antwort = client.post("/api/android/nutzung", json=nachricht(), headers=kopf)
    assert antwort.status_code == 200
    assert antwort.json()["gespeichert"] == 2
    assert antwort.json()["geraet"] == "Pixel-7"

    # Danach kennt der Statusaufruf das Gerät.
    assert client.get("/api/android/status", headers=kopf).json()["geraete"][0][
        "name"
    ] == "Pixel-7"

    seite = client.get(f"/tag/{HEUTE.isoformat()}")
    assert "Handy" in seite.text
    assert "Instagram" in seite.text


def test_unsinn_im_rumpf_wird_abgelehnt(sync_config, regeln):
    client = _client(sync_config, regeln)
    kopf = {"Authorization": "Bearer geheim-123"}

    assert client.post("/api/android/nutzung", json={"geraet": "P"}, headers=kopf).status_code == 400
    kaputt = client.post(
        "/api/android/nutzung",
        content=b"{kein json",
        headers={**kopf, "Content-Type": "application/json"},
    )
    assert kaputt.status_code == 400


def test_tagesansicht_ohne_handy_zeigt_keinen_abschnitt(config, regeln):
    seite = _client(config, regeln).get(f"/tag/{HEUTE.isoformat()}")
    assert "<h2>Handy</h2>" not in seite.text


# -- Kommandozeile -----------------------------------------------------------


def test_cli_android_zeigt_zustand(config, regeln, capsys):
    from fokusradar.cli import main
    from fokusradar.storage.db import Database

    with Database(config.database_path) as database:
        sync.apply_sync(
            database, sync.parse_payload(nachricht()), categorizer=regeln, now=SYNC_ZEIT
        )

    code = main(["--db", str(config.database_path), "android", "--tag", HEUTE.isoformat()])
    ausgabe = capsys.readouterr().out

    assert code == 0
    assert "Pixel-7" in ausgabe
    assert "Instagram" in ausgabe
    assert "nicht gesetzt" in ausgabe


def test_cli_android_token_neu_schreibt_in_die_konfiguration(tmp_path, capsys):
    from fokusradar.cli import main
    from fokusradar.config import DEFAULT_CONFIG_TEMPLATE, load_config

    datei = tmp_path / "config.toml"
    datei.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")

    assert main(["--config", str(datei), "android", "--token-neu"]) == 0
    ausgabe = capsys.readouterr().out

    frisch = load_config(datei)
    assert frisch.android.token
    assert frisch.android.token in ausgabe
    assert not frisch.android.ready  # aktiv bleibt aus, bis jemand es einschaltet

    # In der Datei steht jetzt ein Geheimnis — sie gehört nur noch dem Benutzer.
    if hasattr(os, "getuid"):  # unter Windows wirkungslos
        assert datei.stat().st_mode & 0o077 == 0


def test_token_schreiben_ohne_abschnitt(tmp_path):
    from fokusradar.cli import _token_schreiben
    from fokusradar.config import load_config

    datei = tmp_path / "config.toml"
    datei.write_text('[dashboard]\nport = 9000\n', encoding="utf-8")
    _token_schreiben(datei, "abc123")

    frisch = load_config(datei)
    assert frisch.android.token == "abc123"
    assert frisch.dashboard.port == 9000


def test_token_schreiben_bei_abschnitt_ohne_zeile(tmp_path):
    from fokusradar.cli import _token_schreiben
    from fokusradar.config import load_config

    datei = tmp_path / "config.toml"
    datei.write_text("[android]\naktiv = true\n\n[dashboard]\nport = 9000\n", encoding="utf-8")
    _token_schreiben(datei, "abc123")

    frisch = load_config(datei)
    assert frisch.android.ready
    assert frisch.android.token == "abc123"
    assert frisch.dashboard.port == 9000


def test_sync_adresse_nennt_den_endpunkt(config):
    from fokusradar.cli import _sync_adresse

    adresse = _sync_adresse(dataclasses.replace(config, dashboard=DashboardConfig()))
    assert adresse.startswith("http://")
    assert adresse.endswith(":8760/api/android/nutzung")

    # Eine feste Adresse aus der Konfiguration bleibt unverändert stehen.
    fest = _sync_adresse(
        dataclasses.replace(config, dashboard=DashboardConfig(host="192.168.1.5", port=9000))
    )
    assert fest == "http://192.168.1.5:9000/api/android/nutzung"
