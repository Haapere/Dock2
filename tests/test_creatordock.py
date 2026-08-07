"""Tests für CreatorDock.

Schwerpunkt liegt auf den Regeln, deren Versagen teuer wäre: Freigabe vor
Veröffentlichung, Wirkung eines Widerrufs und die beiden Umsatzgrenzen der
Kleinunternehmerregelung.
"""

from __future__ import annotations

import json

import pytest

from creatordock import (
    dashboard,
    drehs,
    fahrplan,
    finanzen,
    kalender,
    kanaele,
    report,
    seed,
    vorlagen,
)
from creatordock import partnerinnen as partner_mod
from creatordock.store import Store


@pytest.fixture()
def store(tmp_path) -> Store:
    return Store(tmp_path / "daten")


def _voll_vetten(store: Store, kennung: str) -> None:
    for schluessel in partner_mod.GATE_SCHLUESSEL:
        partner_mod.gate_setzen(store, kennung, schluessel)


# --- Speicher -------------------------------------------------------------

def test_speichern_und_neu_laden(store, tmp_path):
    partner_mod.anlegen(store, "Model_A", quelle="Anzeige")
    store.speichern()

    frisch = Store(tmp_path / "daten")
    assert len(frisch.sammlung("partnerinnen")) == 1
    assert frisch.sammlung("partnerinnen")[0]["pseudonym"] == "Model_A"


def test_ids_laufen_hoch(store):
    a = partner_mod.anlegen(store, "A")
    b = partner_mod.anlegen(store, "B")
    assert (a["id"], b["id"]) == ("P1", "P2")


def test_doppeltes_pseudonym_wird_abgelehnt(store):
    partner_mod.anlegen(store, "Model_A")
    with pytest.raises(ValueError, match="bereits vergeben"):
        partner_mod.anlegen(store, "model_a")


def test_sicherung_wird_angelegt(store):
    partner_mod.anlegen(store, "A")
    store.speichern()
    partner_mod.anlegen(store, "B")
    store.speichern()
    assert store.datei.with_suffix(".json.bak").is_file()


def test_beschaedigte_datei_meldet_klar(store):
    store.speichern()
    store.datei.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ValueError, match="beschädigt"):
        Store(store.ordner).laden()


# --- Vetting --------------------------------------------------------------

def test_freigabe_erst_wenn_alle_schritte_erledigt(store):
    p = partner_mod.anlegen(store, "Model_A")
    assert not partner_mod.ist_freigegeben(p)

    for schluessel in partner_mod.GATE_SCHLUESSEL[:-1]:
        partner_mod.gate_setzen(store, p["id"], schluessel)
    assert not partner_mod.ist_freigegeben(p)
    assert p["status"] == partner_mod.STATUS_VETTING

    partner_mod.gate_setzen(store, p["id"], partner_mod.GATE_SCHLUESSEL[-1])
    assert partner_mod.ist_freigegeben(p)
    assert p["status"] == partner_mod.STATUS_FREIGEGEBEN


def test_zuruecknehmen_eines_schritts_entzieht_freigabe(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    partner_mod.gate_setzen(store, p["id"], "release", erfuellt=False)
    assert not partner_mod.ist_freigegeben(p)
    assert "Model-Release / Vertrag unterschrieben" in partner_mod.offene_gates(p)


def test_unbekannter_schritt_wird_abgelehnt(store):
    p = partner_mod.anlegen(store, "Model_A")
    with pytest.raises(ValueError, match="Unbekannter Schritt"):
        partner_mod.gate_setzen(store, p["id"], "gibtsnicht")


def test_abgelaufener_sti_nachweis(store):
    p = partner_mod.anlegen(store, "Model_A")
    partner_mod.sti_gueltigkeit_setzen(store, p["id"], "2020-01-01")
    assert partner_mod.sti_abgelaufen(p)
    partner_mod.sti_gueltigkeit_setzen(store, p["id"], "2099-01-01")
    assert not partner_mod.sti_abgelaufen(p)


# --- Drehs: die eigentliche Schutzregel -----------------------------------

def test_dreh_ohne_freigabe_laesst_sich_nicht_weiterschalten(store):
    p = partner_mod.anlegen(store, "Model_A")
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    with pytest.raises(ValueError, match="Freigabe fehlt"):
        drehs.status_setzen(store, d["id"], "gedreht")
    assert d["status"] == "geplant"


def test_dreh_mit_freigabe_laeuft_durch(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    for status in ("gedreht", "geschnitten", "veröffentlicht"):
        drehs.status_setzen(store, d["id"], status)
    assert d["status"] == "veröffentlicht"
    assert "veroeffentlicht_am" in d


def test_solo_dreh_braucht_keine_freigabe(store):
    d = drehs.anlegen(store, "2026-09-01", "Solo-Test")
    drehs.status_setzen(store, d["id"], "gedreht")
    assert d["status"] == "gedreht"


def test_abgelaufener_sti_blockiert_den_dreh(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    partner_mod.sti_gueltigkeit_setzen(store, p["id"], "2020-01-01")
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    with pytest.raises(ValueError, match="STI-Nachweis abgelaufen"):
        drehs.status_setzen(store, d["id"], "gedreht")


def test_dreh_mit_unbekannter_partnerin_wird_abgelehnt(store):
    with pytest.raises(KeyError):
        drehs.anlegen(store, "2026-09-01", "Test", partner_ids=["P99"])


# --- Widerruf -------------------------------------------------------------

def test_widerruf_sperrt_alle_drehs(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d1 = drehs.anlegen(store, "2026-09-01", "Eins", partner_ids=[p["id"]])
    d2 = drehs.anlegen(store, "2026-09-08", "Zwei", partner_ids=[p["id"]])
    drehs.status_setzen(store, d1["id"], "gedreht")

    partner_mod.widerrufen(store, p["id"], datum="2026-09-10", grund="Meinung geändert")

    assert d1["gesperrt"] and d2["gesperrt"]
    assert not partner_mod.ist_freigegeben(p)
    with pytest.raises(ValueError, match="gesperrt"):
        drehs.status_setzen(store, d1["id"], "veröffentlicht")


def test_widerruf_nach_veroeffentlichung_erzeugt_aufgabe_mit_frist(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Eins", partner_ids=[p["id"]])
    for status in ("gedreht", "geschnitten", "veröffentlicht"):
        drehs.status_setzen(store, d["id"], status)

    vorher = len(store.sammlung("fahrplan"))
    partner_mod.widerrufen(store, p["id"], datum="2026-09-10")
    aufgaben = store.sammlung("fahrplan")

    assert len(aufgaben) == vorher + 1
    neu = aufgaben[-1]
    assert "zurückziehen" in neu["titel"]
    assert neu["prioritaet"] == "hoch"
    assert neu["faellig"] == "2026-09-17"  # 7 Tage Frist


def test_widerruf_blockiert_weitere_gates(store):
    p = partner_mod.anlegen(store, "Model_A")
    partner_mod.widerrufen(store, p["id"])
    with pytest.raises(ValueError, match="hat widerrufen"):
        partner_mod.gate_setzen(store, p["id"], "release")


def test_widerruf_zuruecknehmen_stellt_freigabe_wieder_her(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Eins", partner_ids=[p["id"]])
    partner_mod.widerrufen(store, p["id"])
    partner_mod.widerruf_zuruecknehmen(store, p["id"])

    assert not d["gesperrt"]
    assert partner_mod.ist_freigegeben(p)


# --- Finanzen -------------------------------------------------------------

def test_buchung_braucht_passende_kategorie(store):
    with pytest.raises(ValueError, match="Ausgabe-Kategorie"):
        finanzen.buchen(store, "2026-08-01", "Falsch", "Ausrüstung", einnahme=100)
    with pytest.raises(ValueError, match="Einnahme-Kategorie"):
        finanzen.buchen(store, "2026-08-01", "Falsch", "Einnahme Plattform", ausgabe=100)


def test_buchung_ohne_betrag_wird_abgelehnt(store):
    with pytest.raises(ValueError, match="Betrag fehlt"):
        finanzen.buchen(store, "2026-08-01", "Leer", "Ausrüstung")


def test_journal_rechnet_saldo_fort(store):
    finanzen.buchen(store, "2026-08-01", "Licht-Set", "Ausrüstung", ausgabe=129)
    finanzen.buchen(store, "2026-08-20", "OnlyFans Payout", "Einnahme Plattform", einnahme=340)
    zeilen = finanzen.journal(store, 2026)
    assert [z["saldo"] for z in zeilen] == [-129.0, 211.0]


def test_euer_summiert_das_jahr(store):
    finanzen.buchen(store, "2026-08-01", "Licht", "Ausrüstung", ausgabe=129)
    finanzen.buchen(store, "2026-08-20", "Payout", "Einnahme Plattform", einnahme=340)
    finanzen.buchen(store, "2025-12-01", "Vorjahr", "Einnahme Plattform", einnahme=999)
    euer = finanzen.euer(store, 2026)
    assert (euer["einnahmen"], euer["ausgaben"], euer["gewinn"]) == (340.0, 129.0, 211.0)


def test_monatsuebersicht_kumuliert(store):
    finanzen.buchen(store, "2026-08-20", "Payout", "Einnahme Plattform", einnahme=340)
    finanzen.buchen(store, "2026-09-20", "Payout", "Einnahme Plattform", einnahme=260)
    monate = {m["monat"]: m for m in finanzen.monatsuebersicht(store, 2026, 0.25)}
    assert monate["2026-08"]["umsatz_kumuliert"] == 340.0
    assert monate["2026-09"]["umsatz_kumuliert"] == 600.0
    assert monate["2026-09"]["ruecklage"] == 65.0


def test_kleinunternehmer_beide_grenzen():
    ok = finanzen.kleinunternehmer_status(10_000, 0)
    assert ok["anwendbar"] and not ok["warnung"]

    # Vorjahr über 25.000 € schließt die Regelung für dieses Jahr aus.
    vorjahr = finanzen.kleinunternehmer_status(5_000, 30_000)
    assert not vorjahr["anwendbar"]
    assert any("Vorjahresumsatz" in h for h in vorjahr["hinweise"])

    # Laufendes Jahr über 100.000 € beendet sie sofort.
    laufend = finanzen.kleinunternehmer_status(120_000, 0)
    assert not laufend["anwendbar"]
    assert any("sofort" in h for h in laufend["hinweise"])


def test_kleinunternehmer_warnt_vor_der_grenze():
    nah = finanzen.kleinunternehmer_status(21_000, 0)
    assert nah["anwendbar"] and nah["warnung"]
    assert nah["bis_grenze_vorjahr"] == 4_000.0


# --- Kalender -------------------------------------------------------------

def test_kalender_legt_rhythmus_an(store):
    neu = kalender.planen(store, "2026-08-03", wochen=2)  # ein Montag
    assert len(neu) == 8  # 2 Wochen × (3 Teaser + 1 Paid)
    teaser = [s for s in neu if s["typ"] == "teaser"]
    assert {s["wochentag"] for s in teaser} == {"Mo", "Mi", "Fr"}
    assert all(s["typ"] == "paid" for s in neu if s["wochentag"] == "So")


def test_kalender_legt_keine_doppelten_slots_an(store):
    kalender.planen(store, "2026-08-03", wochen=2)
    nochmal = kalender.planen(store, "2026-08-03", wochen=2)
    assert nochmal == []


def test_kalender_ueberspringt_tage_vor_dem_start(store):
    # Startet an einem Mittwoch — der Montag derselben Woche fällt weg.
    neu = kalender.planen(store, "2026-08-05", wochen=1)
    assert all(s["datum"] >= "2026-08-05" for s in neu)


def test_slot_status_wird_geprueft(store):
    slots = kalender.planen(store, "2026-08-03", wochen=1)
    with pytest.raises(ValueError, match="Unbekannter Status"):
        kalender.slot_aktualisieren(store, slots[0]["id"], status="irgendwas")


# --- Kanäle und OPSEC -----------------------------------------------------

def test_opsec_leitet_zweifaktor_aus_den_kanaelen_ab(store):
    kanaele.anlegen(store, "OnlyFans", zweck="Paid-Plattform", angelegt=True,
                    zwei_faktor=True, email="projekt@example.org")
    kanaele.anlegen(store, "X/Twitter", zweck="NSFW-Reichweite", angelegt=True,
                    zwei_faktor=False, email="projekt@example.org")
    status = kanaele.opsec_status(store)
    assert status["kanaele_ohne_2fa"] == ["X/Twitter"]


def test_doppelter_kanal_wird_abgelehnt(store):
    kanaele.anlegen(store, "Fansly", zweck="Paid-Plattform")
    with pytest.raises(ValueError, match="bereits im Register"):
        kanaele.anlegen(store, "fansly", zweck="Paid-Plattform")


def test_zweiter_account_auf_derselben_plattform_ist_erlaubt(store):
    kanaele.anlegen(store, "Reddit", zweck="NSFW-Reichweite", handle="@haupt")
    kanaele.anlegen(store, "Reddit", zweck="NSFW-Reichweite", handle="@zweit")
    assert len(store.sammlung("kanaele")) == 2


def test_unbekannter_zweck_wird_abgelehnt(store):
    with pytest.raises(ValueError, match="Unbekannter Zweck"):
        kanaele.anlegen(store, "Irgendwas", zweck="Quatsch")


# --- Fahrplan -------------------------------------------------------------

def test_ueberfaellige_aufgaben_stehen_oben(store):
    fahrplan.anlegen(store, "Später", faellig="2099-01-01", prioritaet="hoch")
    fahrplan.anlegen(store, "Überfällig", faellig="2020-01-01", prioritaet="niedrig")
    zeilen = fahrplan.uebersicht(store, stichtag="2026-08-07")
    assert zeilen[0]["titel"] == "Überfällig"
    assert zeilen[0]["ueberfaellig"]


def test_erledigte_aufgabe_gilt_nicht_als_ueberfaellig(store):
    a = fahrplan.anlegen(store, "Alt", faellig="2020-01-01")
    fahrplan.status_setzen(store, a["id"], "erledigt")
    zeilen = fahrplan.uebersicht(store, stichtag="2026-08-07")
    assert not zeilen[0]["ueberfaellig"]


# --- Startdaten, Dashboard, Vorlagen, Bericht -----------------------------

def test_seed_legt_konzeptdaten_an(store):
    angelegt = seed.befuellen(store, kuenstlername="Testname")
    assert angelegt["budget"] == len(seed.AUSRUESTUNG)
    assert angelegt["fahrplan"] == len(seed.FAHRPLAN)
    assert angelegt["kanaele"] == len(kanaele.STANDARD_KANAELE)
    assert store.laden()["projekt"]["kuenstlername"] == "Testname"


def test_seed_ist_wiederholbar(store):
    seed.befuellen(store)
    zweiter = seed.befuellen(store)
    assert zweiter == {"budget": 0, "kanaele": 0, "fahrplan": 0}


def test_lagebild_meldet_blockierten_dreh(store):
    p = partner_mod.anlegen(store, "Model_A")
    drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    lage = dashboard.lagebild(store, stichtag="2026-08-07")
    assert lage["drehs"]["blockiert"] == 1
    assert any("nicht freigegeben" in w["text"] for w in lage["warnungen"])


def test_lagebild_meldet_widerruf_als_kritisch(store):
    p = partner_mod.anlegen(store, "Model_A")
    partner_mod.widerrufen(store, p["id"])
    warnungen = dashboard.warnungen(store, stichtag="2026-08-07")
    assert warnungen[0]["stufe"] == "kritisch"


def test_vorlagen_werden_gefuellt(store):
    store.laden()["projekt"]["kuenstlername"] = "Testname"
    text = vorlagen.rendern(store, "model-release")
    assert "Testname" in text
    assert "{" not in text.replace("{{", "")  # keine offenen Platzhalter
    assert "keine Rechtsberatung" in text


def test_alle_vorlagen_rendern(store):
    seed.befuellen(store, kuenstlername="Testname")
    for schluessel in vorlagen.VORLAGEN:
        assert len(vorlagen.rendern(store, schluessel)) > 200


def test_bericht_wird_geschrieben(store, tmp_path):
    seed.befuellen(store, kuenstlername="Testname")
    finanzen.buchen(store, "2026-08-20", "Payout", "Einnahme Plattform", einnahme=340)
    ziel = report.erzeugen(store, tmp_path / "bericht.html")
    inhalt = ziel.read_text(encoding="utf-8")
    assert inhalt.startswith("<!doctype html>")
    assert "Testname" in inhalt
    assert "Statusbericht" in inhalt


def test_bericht_maskiert_html_sonderzeichen(store, tmp_path):
    partner_mod.anlegen(store, "<script>alert(1)</script>")
    inhalt = report.erzeugen(store, tmp_path / "b.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in inhalt
    assert "&lt;script&gt;" in inhalt


# --- Web-API --------------------------------------------------------------

@pytest.fixture()
def api(store, monkeypatch):
    """Bindet die API-Funktionen an einen Test-Store."""
    from creatordock import webapp
    monkeypatch.setattr(webapp, "_STORE", store)
    return webapp


def test_api_legt_partnerin_an(api, store):
    """Die Formulardaten enthalten 'pseudonym' — das darf nicht doppelt ankommen."""
    ergebnis = api.api_partnerin_anlegen(
        {"pseudonym": "Model_A", "quelle": "Anzeige", "aktenzeichen": "2026-001"}
    )
    assert [z["pseudonym"] for z in ergebnis["zeilen"]] == ["Model_A"]
    assert store.sammlung("partnerinnen")[0]["quelle"] == "Anzeige"


def test_api_legt_kanal_an(api, store):
    ergebnis = api.api_kanal_anlegen(
        {"plattform": "Fansly", "zweck": "Paid-Plattform", "handle": "@test"}
    )
    assert any(k["plattform"] == "Fansly" for k in ergebnis["zeilen"])


def test_api_schreibt_jede_aenderung_auf_die_platte(api, store):
    api.api_partnerin_anlegen({"pseudonym": "Model_A"})
    frisch = Store(store.ordner)
    assert len(frisch.sammlung("partnerinnen")) == 1


def test_api_start_liefert_alle_auswahllisten(api):
    daten = api.api_start({})
    for schluessel in ("gates", "kategorien", "plattformen", "dreh_status",
                       "slot_status", "bereiche", "prioritaeten", "zwecke", "vorlagen"):
        assert daten[schluessel], f"{schluessel} ist leer"


def test_api_meldet_gesperrten_dreh(api, store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    partner_mod.widerrufen(store, p["id"])
    with pytest.raises(ValueError, match="gesperrt"):
        api.api_dreh_status({"id": d["id"], "status": "veröffentlicht"})


def test_datenbank_bleibt_json_serialisierbar(store):
    seed.befuellen(store, kuenstlername="Testname")
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    kalender.planen(store, "2026-08-03", wochen=1)
    finanzen.buchen(store, "2026-08-20", "Payout", "Einnahme Plattform", einnahme=340)
    json.dumps(store.laden())  # wirft, falls etwas nicht serialisierbar ist
