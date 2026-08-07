"""Tests für CreatorDock.

Schwerpunkt liegt auf den Regeln, deren Versagen teuer wäre: Freigabe vor
Veröffentlichung, Wirkung eines Widerrufs und die beiden Umsatzgrenzen der
Kleinunternehmerregelung.
"""

from __future__ import annotations

import json

import pytest

from creatordock import (
    angebot,
    dashboard,
    drehs,
    fahrplan,
    finanzen,
    kalender,
    kanaele,
    persona,
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


def _alle_auflagen_bestaetigen(store: Store, dreh_id: str) -> None:
    dreh = store.finden("drehs", dreh_id)
    for auflage in angebot.auflagen_fuer_dreh(store, dreh):
        drehs.auflage_bestaetigen(store, dreh_id, auflage["schluessel"])


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
    drehs.status_setzen(store, d["id"], "gedreht")
    drehs.status_setzen(store, d["id"], "geschnitten")
    _alle_auflagen_bestaetigen(store, d["id"])
    drehs.status_setzen(store, d["id"], "veröffentlicht")
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
    drehs.status_setzen(store, d["id"], "gedreht")
    drehs.status_setzen(store, d["id"], "geschnitten")
    _alle_auflagen_bestaetigen(store, d["id"])
    drehs.status_setzen(store, d["id"], "veröffentlicht")

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


# --- Angebot: aus Zusagen werden Sperren ----------------------------------

def test_standardangebot_hat_sinnvolle_voreinstellungen(store):
    werte = angebot.standard(store)
    assert werte["gesicht"] == "ohne Gesicht"
    assert werte["begleitperson"] is True
    assert werte["sichtungsrecht"] is True
    assert werte["exklusivitaet"] is False  # schreckt erfahrene Darstellerinnen ab


def test_vereinbarung_ueberschreibt_nur_punktuell(store):
    p = partner_mod.anlegen(store, "Model_A")
    angebot.vereinbarung_setzen(store, p["id"], "gesicht", "mit Gesicht")
    werte = angebot.vereinbarung(store, p["id"])
    assert werte["gesicht"] == "mit Gesicht"
    assert werte["sichtungsrecht"] is True  # Standard bleibt
    assert angebot.standard(store)["gesicht"] == "ohne Gesicht"  # unberührt


def test_abweichungen_werden_ausgewiesen(store):
    p = partner_mod.anlegen(store, "Model_A")
    angebot.vereinbarung_setzen(store, p["id"], "gesicht", "mit Gesicht")
    ab = angebot.abweichungen(store, p["id"])
    assert len(ab) == 1
    assert ab[0]["standard"] == "ohne Gesicht"
    assert ab[0]["vereinbart"] == "mit Gesicht"


def test_zuruecksetzen_stellt_standard_wieder_her(store):
    p = partner_mod.anlegen(store, "Model_A")
    angebot.vereinbarung_setzen(store, p["id"], "gesicht", "mit Gesicht")
    angebot.vereinbarung_zuruecksetzen(store, p["id"], "gesicht")
    assert angebot.vereinbarung(store, p["id"])["gesicht"] == "ohne Gesicht"
    assert angebot.abweichungen(store, p["id"]) == []


def test_ungueltiger_wert_wird_abgelehnt(store):
    with pytest.raises(ValueError, match="nicht möglich"):
        angebot.standard_setzen(store, "gesicht", "vielleicht")


def test_gesichtslos_erzeugt_auflage(store):
    p = partner_mod.anlegen(store, "Model_A")
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    texte = [a["text"] for a in angebot.auflagen_fuer_dreh(store, d)]
    assert any("Gesicht kommt im gesamten Material nicht vor" in t for t in texte)


def test_mit_gesicht_erzeugt_keine_gesichts_auflage(store):
    p = partner_mod.anlegen(store, "Model_A")
    angebot.vereinbarung_setzen(store, p["id"], "gesicht", "mit Gesicht")
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    schluessel = [a["schluessel"] for a in angebot.auflagen_fuer_dreh(store, d)]
    assert "gesicht" not in schluessel


def test_veroeffentlichung_blockiert_bis_auflagen_bestaetigt(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    drehs.status_setzen(store, d["id"], "gedreht")
    drehs.status_setzen(store, d["id"], "geschnitten")

    with pytest.raises(ValueError, match="Auflagen sind noch nicht bestätigt"):
        drehs.status_setzen(store, d["id"], "veröffentlicht")
    assert d["status"] == "geschnitten"

    _alle_auflagen_bestaetigen(store, d["id"])
    drehs.status_setzen(store, d["id"], "veröffentlicht")
    assert d["status"] == "veröffentlicht"


def test_eine_offene_auflage_genuegt_zum_blockieren(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    drehs.status_setzen(store, d["id"], "gedreht")
    drehs.status_setzen(store, d["id"], "geschnitten")
    auflagen = angebot.auflagen_fuer_dreh(store, d)
    for auflage in auflagen[:-1]:
        drehs.auflage_bestaetigen(store, d["id"], auflage["schluessel"])
    with pytest.raises(ValueError, match=auflagen[-1]["text"][:25]):
        drehs.status_setzen(store, d["id"], "veröffentlicht")


def test_solo_dreh_erbt_auflagen_aus_dem_standard(store):
    d = drehs.anlegen(store, "2026-09-01", "Solo")
    schluessel = [a["schluessel"] for a in angebot.auflagen_fuer_dreh(store, d)]
    assert "wasserzeichen" in schluessel
    assert "metadaten_entfernt" in schluessel
    # Ohne Partnerin ergeben partnerbezogene Auflagen keinen Sinn.
    assert "sichtungsrecht" not in schluessel
    assert "gesicht" not in schluessel
    assert "kuenstlername_ihrs" not in schluessel


def test_auflage_zweier_partnerinnen_wird_zusammengefuehrt(store):
    a = partner_mod.anlegen(store, "Model_A")
    b = partner_mod.anlegen(store, "Model_B")
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[a["id"], b["id"]])
    gesicht = [x for x in angebot.auflagen_fuer_dreh(store, d) if x["schluessel"] == "gesicht"]
    assert len(gesicht) == 1
    assert set(gesicht[0]["fuer"]) == {"Model_A", "Model_B"}


def test_unbekannte_auflage_wird_abgelehnt(store):
    d = drehs.anlegen(store, "2026-09-01", "Solo")
    with pytest.raises(ValueError, match="keine Auflage"):
        drehs.auflage_bestaetigen(store, d["id"], "gibtsnicht")


def test_auflagen_marker_folgt_dem_aktuellen_wert(store):
    nach_schluessel = {e["schluessel"]: e for e in angebot.katalog(store)}
    assert nach_schluessel["gesicht"]["erzeugt_auflage"]        # "ohne Gesicht"
    assert not nach_schluessel["stimme"]["erzeugt_auflage"]     # "unverändert"
    assert not nach_schluessel["merkmale_abdecken"]["erzeugt_auflage"]

    angebot.standard_setzen(store, "stimme", "verzerrt")
    angebot.standard_setzen(store, "gesicht", "mit Gesicht")
    nach_schluessel = {e["schluessel"]: e for e in angebot.katalog(store)}
    assert nach_schluessel["stimme"]["erzeugt_auflage"]
    assert not nach_schluessel["gesicht"]["erzeugt_auflage"]


def test_angebotsblatt_enthaelt_die_zusagen(store):
    text = angebot.angebotsblatt(store)
    assert "Begleitperson darf mitkommen" in text
    assert "Gesicht im Bild: ohne Gesicht" in text
    # Abgeschaltete Ja/Nein-Zusagen tauchen nicht auf.
    assert "Exklusivität verlangt" not in text


# --- Persona --------------------------------------------------------------

def test_steckbrief_und_identitaet(store):
    persona.steckbrief_setzen(store, "nische", "Amateur, echtes Paar")
    persona.identitaet_setzen(store, "wasserzeichen", "@testname")
    assert persona.steckbrief(store)["nische"] == "Amateur, echtes Paar"
    assert persona.identitaet(store)["wasserzeichen"] == "@testname"


def test_unbekanntes_feld_wird_abgelehnt(store):
    with pytest.raises(ValueError, match="Unbekanntes Steckbrief-Feld"):
        persona.steckbrief_setzen(store, "quatsch", "x")


def test_namenskandidat_mit_vergebenem_handle_ist_nicht_waehlbar(store):
    kanaele.anlegen(store, "OnlyFans", zweck="Paid-Plattform")
    kanaele.anlegen(store, "X/Twitter", zweck="NSFW-Reichweite")
    k = persona.name_vorschlagen(store, "TestName")
    persona.name_pruefung_setzen(store, k["id"], "OnlyFans", "frei")
    persona.name_pruefung_setzen(store, k["id"], "X/Twitter", "vergeben")

    with pytest.raises(ValueError, match="vergeben"):
        persona.name_waehlen(store, k["id"])


def test_name_waehlen_setzt_kuenstlername_und_wasserzeichen(store):
    kanaele.anlegen(store, "OnlyFans", zweck="Paid-Plattform")
    k = persona.name_vorschlagen(store, "TestName")
    persona.name_pruefung_setzen(store, k["id"], "OnlyFans", "frei")
    persona.name_waehlen(store, k["id"])

    assert store.laden()["projekt"]["kuenstlername"] == "TestName"
    assert persona.identitaet(store)["wasserzeichen"] == "TestName"
    assert persona.namensuebersicht(store)[0]["favorit"]


def test_doppelter_namenskandidat_wird_abgelehnt(store):
    persona.name_vorschlagen(store, "TestName")
    with pytest.raises(ValueError, match="bereits auf der Liste"):
        persona.name_vorschlagen(store, "testname")


def test_bio_haelt_das_zeichenlimit_ein(store):
    store.laden()["projekt"]["kuenstlername"] = "TestName"
    persona.steckbrief_setzen(store, "nische", "x" * 200)
    persona.steckbrief_setzen(store, "alleinstellung", "y" * 200)
    bio = persona.bio_vorschlag(store, "TikTok")  # 80 Zeichen
    assert bio["zeichen"] <= 80
    assert bio["passt"]
    assert bio["text"].endswith("…")


def test_sfw_plattform_bekommt_keine_expliziten_bausteine(store):
    store.laden()["projekt"]["kuenstlername"] = "TestName"
    persona.steckbrief_setzen(store, "alleinstellung", "GEHEIMER-EXPLIZITER-TEXT")
    assert "GEHEIMER" not in persona.bio_vorschlag(store, "Instagram")["text"]
    assert "GEHEIMER" in persona.bio_vorschlag(store, "OnlyFans")["text"]


def test_plattform_ohne_regeln_wird_abgelehnt(store):
    with pytest.raises(ValueError, match="keine Regeln hinterlegt"):
        persona.bio_vorschlag(store, "MySpace")


def test_fortschritt_zaehlt_offene_punkte(store):
    leer = persona.fortschritt(store)
    assert leer["erledigt"] == 0
    assert "Künstlername ist noch nicht festgelegt" in leer["offen"]

    store.laden()["projekt"]["kuenstlername"] = "TestName"
    for schluessel, _, _ in persona.STECKBRIEF_FELDER:
        persona.steckbrief_setzen(store, schluessel, "ausgefüllt")
    for schluessel, _, _ in persona.IDENTITAET_FELDER:
        persona.identitaet_setzen(store, schluessel, "ausgefüllt")
    voll = persona.fortschritt(store)
    assert voll["anteil"] == 100
    assert voll["offen"] == []


def test_dashboard_warnt_ohne_kuenstlername(store):
    warnungen = dashboard.warnungen(store, stichtag="2026-08-07")
    assert any("kein Künstlername" in w["text"] for w in warnungen)


def test_dashboard_warnt_bei_offenen_auflagen(store):
    p = partner_mod.anlegen(store, "Model_A")
    _voll_vetten(store, p["id"])
    d = drehs.anlegen(store, "2026-09-01", "Test", partner_ids=[p["id"]])
    drehs.status_setzen(store, d["id"], "gedreht")
    drehs.status_setzen(store, d["id"], "geschnitten")
    warnungen = dashboard.warnungen(store, stichtag="2026-08-07")
    assert any("offene Auflagen" in w["text"] for w in warnungen)


# --- Vorlagen aus echten Daten -------------------------------------------

def test_release_uebernimmt_die_vereinbarung(store):
    store.laden()["projekt"]["kuenstlername"] = "TestName"
    p = partner_mod.anlegen(store, "Model_A")
    angebot.vereinbarung_setzen(store, p["id"], "stimme", "verzerrt")
    angebot.vereinbarung_setzen(store, p["id"], "merkmale_abdecken", True)

    text = vorlagen.rendern(store, "model-release", partner_id=p["id"])
    assert "Das Gesicht des Models wird nicht aufgenommen" in text
    assert "Die Stimme des Models wird verzerrt" in text
    assert "Tattoos, Narben" in text


def test_release_ohne_partnerin_nutzt_den_standard(store):
    store.laden()["projekt"]["kuenstlername"] = "TestName"
    angebot.standard_setzen(store, "gesicht", "mit Gesicht")
    text = vorlagen.rendern(store, "model-release")
    assert "darf im Material erkennbar sein" in text


def test_anzeige_zieht_das_angebot(store):
    angebot.standard_setzen(store, "zahlung_am_drehtag", True)
    text = vorlagen.rendern(store, "anzeige")
    assert "Auszahlung am Drehtag" in text


def test_angebotsblatt_vorlage_rendert(store):
    text = vorlagen.rendern(store, "angebot")
    assert "Was du selbst entscheidest" in text
    assert "Gesicht im Bild" in text
    assert "keine Rechtsberatung" in text


def test_wasserzeichen_kommt_aus_der_identitaet(store):
    store.laden()["projekt"]["kuenstlername"] = "TestName"
    persona.identitaet_setzen(store, "wasserzeichen", "@marke")
    assert '"@marke"' in vorlagen.rendern(store, "model-release")


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
    assert "Angebot an Partnerinnen" in inhalt
    assert "Persona" in inhalt


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
