"""Kommandozeile für CreatorDock.

Ohne Argument startet die grafische Oberfläche — das ist der Normalfall. Die
Unterbefehle sind für alle da, die lieber tippen, und für Automatisierung.
"""

from __future__ import annotations

import argparse
import sys

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
    webapp,
)
from creatordock import partnerinnen as partner_mod
from creatordock.store import ABLAGE_HINWEIS, Store


def _store(args) -> Store:
    return Store(getattr(args, "daten", None))


# --- Befehle --------------------------------------------------------------

def cmd_gui(args) -> int:
    store = _store(args)
    if not store.existiert:
        print("Erster Start — es wird ein neuer Datenbestand angelegt.")
        seed.befuellen(store, kuenstlername=args.kuenstlername or "")
        store.speichern()
        print(f"Datenordner: {store.ordner}\n{ABLAGE_HINWEIS}\n")
    webapp.serve(store, port=args.port, open_browser=not args.kein_browser)
    return 0


def cmd_init(args) -> int:
    store = _store(args)
    schon_da = store.existiert
    angelegt = seed.befuellen(store, kuenstlername=args.kuenstlername or "")
    pfad = store.speichern()
    print(("Datenbestand aktualisiert: " if schon_da else "Datenbestand angelegt: ") + str(pfad))
    print(
        f"  {angelegt['budget']} Budgetposten, {angelegt['kanaele']} Kanäle, "
        f"{angelegt['fahrplan']} Aufgaben"
    )
    print(f"\n{ABLAGE_HINWEIS}")
    return 0


def cmd_status(args) -> int:
    store = _store(args)
    if not store.existiert:
        print("Noch kein Datenbestand. Zuerst 'creatordock init' ausführen.")
        return 1
    lage = dashboard.lagebild(store)
    p, f = lage["partnerinnen"], lage["finanzen"]
    name = lage["projekt"]["kuenstlername"] or "(ohne Künstlername)"
    print(f"CreatorDock — {name}, Stand {lage['projekt']['jahr']}")
    print(f"  Datenordner:    {store.ordner}")
    print(f"  Partnerinnen:   {p['freigegeben']} freigegeben, {p['im_vetting']} im Vetting, "
          f"{p['widerrufen']} widerrufen")
    pipeline = ", ".join(f"{k} {v}" for k, v in lage["drehs"]["pipeline"].items())
    print(f"  Drehs:          {pipeline}"
          + (f" (gesperrt: {lage['drehs']['gesperrt']})" if lage["drehs"]["gesperrt"] else ""))
    print(f"  Kalender:       {lage['kalender']['gesamt']} Slots")
    print(f"  Finanzen:       Einnahmen {f['einnahmen']:.2f} €, Ausgaben {f['ausgaben']:.2f} €, "
          f"Gewinn {f['gewinn']:.2f} €")
    print(f"  Rücklage:       {f['ruecklage']:.2f} € ({f['ruecklage_satz']*100:.0f} %)")
    ku = lage["kleinunternehmer"]
    print(f"  Kleinunternehmer: {'ja' if ku['anwendbar'] else 'NEIN'} — "
          f"Umsatz {ku['laufender_umsatz']:.2f} €")
    print(f"  Aufgaben:       {lage['fahrplan']['offen']} offen, "
          f"{lage['fahrplan']['ueberfaellig']} überfällig")

    if lage["warnungen"]:
        print(f"\nOffene Risiken ({len(lage['warnungen'])}):")
        for meldung in lage["warnungen"]:
            marke = {"kritisch": "!!", "warnung": " !", "hinweis": "  "}[meldung["stufe"]]
            print(f"  {marke} [{meldung['bereich']}] {meldung['text']}")
    else:
        print("\nKeine offenen Risiken.")
    return 0


def cmd_partnerin(args) -> int:
    store = _store(args)
    if args.aktion == "liste":
        zeilen = partner_mod.uebersicht(store)
        if not zeilen:
            print("Keine Partnerinnen erfasst.")
            return 0
        for z in zeilen:
            marke = "OK " if z["freigegeben"] else "-- "
            print(f"{marke}{z['id']:<4} {z['pseudonym']:<18} {z['status']:<12} "
                  f"{z['erledigt']}/{z['gesamt']}")
            for offen in z["offen"]:
                print(f"        offen: {offen}")
        return 0

    if args.aktion == "neu":
        eintrag = partner_mod.anlegen(store, args.pseudonym, quelle=args.quelle or "")
        store.speichern()
        print(f"{eintrag['id']}: {eintrag['pseudonym']} angelegt.")
        print("Offene Schritte:")
        for _, label, _ in partner_mod.GATES:
            print(f"  - {label}")
        return 0

    if args.aktion == "gate":
        partner_mod.gate_setzen(store, args.id, args.gate, erfuellt=not args.zuruecknehmen)
        store.speichern()
        partnerin = store.finden("partnerinnen", args.id)
        offen = partner_mod.offene_gates(partnerin)
        print(f"{partnerin['pseudonym']}: Status {partnerin['status']}, "
              f"{len(offen)} Schritt(e) offen.")
        return 0

    if args.aktion == "widerruf":
        partnerin = partner_mod.widerrufen(store, args.id, grund=args.grund or "")
        store.speichern()
        print(f"Widerruf für {partnerin['pseudonym']} erfasst. Alle zugehörigen Drehs "
              "sind gesperrt.")
        return 0

    print("Unbekannte Aktion.")
    return 2


def cmd_dreh(args) -> int:
    store = _store(args)
    if args.aktion == "liste":
        for z in drehs.uebersicht(store):
            marke = "GESPERRT" if z["gesperrt"] else ("frei" if z["startklar"] else "blockiert")
            print(f"{z['id']:<4} {z['datum']}  {z['status']:<14} {marke:<10} {z['titel']}")
            for block in z["blockiert_durch"]:
                print(f"        {block['pseudonym']}: {', '.join(block['gruende'])}")
        return 0

    if args.aktion == "neu":
        eintrag = drehs.anlegen(
            store, args.datum, titel=args.titel or "",
            partner_ids=args.partnerin or [], plattformen=args.plattform or [],
        )
        store.speichern()
        print(f"{eintrag['id']}: Dreh am {eintrag['datum']} geplant.")
        return 0

    if args.aktion == "status":
        eintrag = drehs.status_setzen(store, args.id, args.wert)
        store.speichern()
        print(f"{eintrag['id']} steht jetzt auf '{eintrag['status']}'.")
        return 0

    print("Unbekannte Aktion.")
    return 2


def cmd_angebot(args) -> int:
    store = _store(args)
    partner_id = args.partnerin
    if args.aktion == "zeigen":
        titel = f"Vereinbarung mit {store.finden('partnerinnen', partner_id)['pseudonym']}" \
            if partner_id else "Standardangebot"
        print(f"{titel}\n")
        letzte = ""
        for eintrag in angebot.katalog(store, partner_id):
            if eintrag["kategorie"] != letzte:
                letzte = eintrag["kategorie"]
                print(f"  {letzte}")
            wert = eintrag["wert"]
            anzeige = ("ja" if wert else "nein") if eintrag["typ"] == "ja_nein" else wert
            marken = []
            if eintrag["abweichend"]:
                marken.append("abweichend")
            if eintrag["erzeugt_auflage"]:
                marken.append("Auflage")
            zusatz = f"  [{', '.join(marken)}]" if marken else ""
            print(f"    {eintrag['schluessel']:<28} {anzeige}{zusatz}")
        return 0

    if args.aktion == "setzen":
        wert: object = args.wert
        if wert in ("ja", "nein"):
            wert = wert == "ja"
        if partner_id:
            angebot.vereinbarung_setzen(store, partner_id, args.schluessel, wert)
        else:
            angebot.standard_setzen(store, args.schluessel, wert)
        store.speichern()
        print(f"'{args.schluessel}' gesetzt auf: {args.wert}")
        return 0

    if args.aktion == "blatt":
        print(angebot.angebotsblatt(store, partner_id))
        return 0

    print("Unbekannte Aktion.")
    return 2


def cmd_persona(args) -> int:
    store = _store(args)
    if args.aktion == "status":
        stand = persona.fortschritt(store)
        print(f"Identitätsaufbau: {stand['erledigt']} von {stand['gesamt']} "
              f"({stand['anteil']} %)")
        print(f"  Künstlername: {stand['kuenstlername'] or '— noch keiner —'}")
        if stand["offen"]:
            print("\n  Offen:")
            for punkt in stand["offen"]:
                print(f"    - {punkt}")
        print("\n  Stufenplan:")
        for name, zeitraum, schritte in persona.AUFBAU_PHASEN:
            print(f"    {name} ({zeitraum})")
            for schritt in schritte:
                print(f"      - {schritt}")
        return 0

    if args.aktion == "setzen":
        if args.schluessel in {s for s, _, _ in persona.IDENTITAET_FELDER}:
            persona.identitaet_setzen(store, args.schluessel, args.wert or "")
        else:
            persona.steckbrief_setzen(store, args.schluessel, args.wert or "")
        store.speichern()
        print(f"'{args.schluessel}' gespeichert.")
        return 0

    if args.aktion == "namen":
        zeilen = persona.namensuebersicht(store)
        if not zeilen:
            print("Noch keine Namenskandidaten. Anlegen mit: persona name --name \"...\"")
            return 0
        for kandidat in zeilen:
            marke = "*" if kandidat["favorit"] else " "
            print(f"{marke}{kandidat['id']:<4} {kandidat['name']:<22} "
                  f"frei {kandidat['frei']}, vergeben {kandidat['vergeben']}, "
                  f"offen {kandidat['offen']}")
            for plattform, status in (kandidat.get("geprueft") or {}).items():
                if status != "offen":
                    print(f"        {plattform}: {status}")
        return 0

    if args.aktion == "name":
        kandidat = persona.name_vorschlagen(store, args.name)
        store.speichern()
        print(f"{kandidat['id']}: '{kandidat['name']}' aufgenommen. "
              "Verfügbarkeit je Plattform prüfen und eintragen.")
        return 0

    if args.aktion == "bios":
        for bio in persona.alle_bios(store):
            marke = "" if bio["passt"] else "  ZU LANG"
            print(f"\n{bio['plattform']} ({bio['zeichen']}/{bio['limit']} Zeichen){marke}")
            print(f"  Inhalt: {bio['inhalt']}")
            print(f"  {bio['text']}")
            for hinweis in bio["hinweise"]:
                print(f"    ! {hinweis}")
        return 0

    print("Unbekannte Aktion.")
    return 2


def cmd_buchen(args) -> int:
    store = _store(args)
    eintrag = finanzen.buchen(
        store, args.datum, args.beschreibung, args.kategorie,
        einnahme=args.einnahme or 0, ausgabe=args.ausgabe or 0, beleg=args.beleg or "",
    )
    store.speichern()
    art = "Einnahme" if eintrag["einnahme"] else "Ausgabe"
    betrag = eintrag["einnahme"] or eintrag["ausgabe"]
    print(f"{eintrag['id']}: {art} {betrag:.2f} € am {eintrag['datum']} gebucht.")
    return 0


def cmd_finanzen(args) -> int:
    store = _store(args)
    jahr = args.jahr or int(store.laden()["projekt"].get("start", "2026")[:4])
    euer = finanzen.euer(store, jahr)
    print(f"Einnahmen-Überschuss-Rechnung {jahr}")
    print(f"  Einnahmen: {euer['einnahmen']:>12.2f} €")
    print(f"  Ausgaben:  {euer['ausgaben']:>12.2f} €")
    print(f"  Gewinn:    {euer['gewinn']:>12.2f} €")
    if euer["je_kategorie"]:
        print("\n  Nach Kategorie:")
        for kategorie, summe in euer["je_kategorie"].items():
            print(f"    {kategorie:<22} {summe:>10.2f} €")
    ku = finanzen.kleinunternehmer_status(
        finanzen.jahresumsatz(store, jahr), store.laden()["projekt"].get("vorjahresumsatz", 0.0)
    )
    print(f"\n  Kleinunternehmerregelung: {'anwendbar' if ku['anwendbar'] else 'NICHT anwendbar'}")
    for hinweis in ku["hinweise"]:
        print(f"    {hinweis}")
    return 0


def cmd_kalender(args) -> int:
    store = _store(args)
    if args.aktion == "planen":
        neu = kalender.planen(store, args.start, wochen=args.wochen, ersetzen=args.ersetzen)
        store.speichern()
        print(f"{len(neu)} Slots angelegt.")
        return 0
    for slot in kalender.uebersicht(store, ab=args.ab):
        print(f"{slot['datum']} {slot.get('wochentag',''):<3} {slot['typ']:<7} "
              f"{slot.get('kanal',''):<12} {slot.get('status',''):<14} {slot.get('thema','')}")
    return 0


def cmd_aufgabe(args) -> int:
    store = _store(args)
    if args.aktion == "liste":
        for a in fahrplan.uebersicht(store, nur_offen=not args.alle):
            marke = "!" if a["ueberfaellig"] else " "
            print(f"{marke}{a['id']:<4} {a.get('faellig','—'):<12} {a['prioritaet']:<8} "
                  f"{a['bereich']:<12} {a['titel']}")
        return 0
    if args.aktion == "erledigt":
        aufgabe = fahrplan.status_setzen(store, args.id, "erledigt")
        store.speichern()
        print(f"Erledigt: {aufgabe['titel']}")
        return 0
    print("Unbekannte Aktion.")
    return 2


def cmd_vorlage(args) -> int:
    store = _store(args)
    if not args.name:
        for eintrag in vorlagen.namen():
            print(f"  {eintrag['schluessel']:<16} {eintrag['titel']}")
        return 0
    text = vorlagen.rendern(store, args.name, partner_id=args.partnerin)
    if args.out:
        from pathlib import Path
        ziel = Path(args.out).expanduser()
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")
        print(f"Vorlage geschrieben: {ziel}")
    else:
        print(text)
    return 0


def cmd_bericht(args) -> int:
    store = _store(args)
    ziel = args.out or (store.ordner / "statusbericht.html")
    pfad = report.erzeugen(store, ziel)
    print(f"Bericht geschrieben: {pfad}")
    return 0


def cmd_kanaele(args) -> int:
    store = _store(args)
    for kanal in kanaele.uebersicht(store):
        marken = []
        if kanal.get("angelegt"):
            marken.append("angelegt")
        if kanal.get("zwei_faktor"):
            marken.append("2FA")
        if kanal.get("verifiziert"):
            marken.append("verifiziert")
        print(f"{kanal['id']:<4} {kanal['plattform']:<24} {kanal['zweck']:<20} "
              f"{kanal.get('handle','') or '—':<18} {', '.join(marken) or '—'}")
    opsec = kanaele.opsec_status(store)
    print(f"\nOPSEC-Setup: {opsec['setup_erledigt']} von {opsec['setup_gesamt']} erledigt.")
    for punkt in opsec["punkte"]:
        haken = "x" if punkt["erledigt"] else " "
        art = "vor jedem Upload" if punkt["art"] == "pro_upload" else "einmalig"
        print(f"  [{haken}] {punkt['label']}  ({art})")
    return 0


# --- Parser ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creatordock",
        description="Lokale Projektzentrale für das Content-Creator-Projekt.",
    )
    parser.add_argument(
        "--daten", help="Abweichender Datenordner (sonst ~/CreatorDock-Daten)"
    )
    unter = parser.add_subparsers(dest="befehl")

    p = unter.add_parser("gui", help="Grafische Oberfläche starten (Standard)")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--kein-browser", action="store_true", dest="kein_browser")
    p.add_argument("--kuenstlername", default="")
    p.set_defaults(func=cmd_gui)

    p = unter.add_parser("init", help="Datenbestand mit dem Konzept-Fahrplan anlegen")
    p.add_argument("--kuenstlername", default="")
    p.set_defaults(func=cmd_init)

    p = unter.add_parser("status", help="Lagebild und offene Risiken")
    p.set_defaults(func=cmd_status)

    p = unter.add_parser("partnerin", help="Onboarding und Freigaben")
    p.add_argument("aktion", choices=["liste", "neu", "gate", "widerruf"])
    p.add_argument("--pseudonym")
    p.add_argument("--quelle")
    p.add_argument("--id")
    p.add_argument("--gate", choices=list(partner_mod.GATE_SCHLUESSEL))
    p.add_argument("--zuruecknehmen", action="store_true")
    p.add_argument("--grund")
    p.set_defaults(func=cmd_partnerin)

    p = unter.add_parser("dreh", help="Drehplanung")
    p.add_argument("aktion", choices=["liste", "neu", "status"])
    p.add_argument("--datum")
    p.add_argument("--titel")
    p.add_argument("--partnerin", action="append", help="ID, mehrfach möglich")
    p.add_argument("--plattform", action="append")
    p.add_argument("--id")
    p.add_argument("--wert", choices=list(drehs.STATUS_REIHENFOLGE))
    p.set_defaults(func=cmd_dreh)

    p = unter.add_parser("angebot", help="Was du Partnerinnen zusagst")
    p.add_argument("aktion", choices=["zeigen", "setzen", "blatt"], nargs="?", default="zeigen")
    p.add_argument("--partnerin", help="ID — dann gilt es nur für sie")
    p.add_argument("--schluessel")
    p.add_argument("--wert")
    p.set_defaults(func=cmd_angebot)

    p = unter.add_parser("persona", help="Social-Media-Identität aufbauen")
    p.add_argument("aktion", choices=["status", "setzen", "namen", "name", "bios"],
                   nargs="?", default="status")
    p.add_argument("--schluessel")
    p.add_argument("--wert")
    p.add_argument("--name")
    p.set_defaults(func=cmd_persona)

    p = unter.add_parser("buchen", help="Einnahme oder Ausgabe erfassen")
    p.add_argument("datum")
    p.add_argument("beschreibung")
    p.add_argument("kategorie", choices=list(finanzen.KATEGORIEN))
    p.add_argument("--einnahme", type=float)
    p.add_argument("--ausgabe", type=float)
    p.add_argument("--beleg")
    p.set_defaults(func=cmd_buchen)

    p = unter.add_parser("finanzen", help="EÜR und Kleinunternehmer-Status")
    p.add_argument("--jahr", type=int)
    p.set_defaults(func=cmd_finanzen)

    p = unter.add_parser("kalender", help="Content-Kalender")
    p.add_argument("aktion", choices=["liste", "planen"], nargs="?", default="liste")
    p.add_argument("--start")
    p.add_argument("--wochen", type=int, default=6)
    p.add_argument("--ersetzen", action="store_true")
    p.add_argument("--ab")
    p.set_defaults(func=cmd_kalender)

    p = unter.add_parser("aufgabe", help="Fahrplan")
    p.add_argument("aktion", choices=["liste", "erledigt"], nargs="?", default="liste")
    p.add_argument("--id")
    p.add_argument("--alle", action="store_true")
    p.set_defaults(func=cmd_aufgabe)

    p = unter.add_parser("kanaele", help="Kanal-Register und OPSEC-Checkliste")
    p.set_defaults(func=cmd_kanaele)

    p = unter.add_parser("vorlage", help="Textvorlage ausgeben")
    p.add_argument("name", nargs="?", choices=list(vorlagen.VORLAGEN))
    p.add_argument("--partnerin", help="ID — setzt ihre Vereinbarung ein")
    p.add_argument("--out")
    p.set_defaults(func=cmd_vorlage)

    p = unter.add_parser("bericht", help="HTML-Statusbericht erzeugen")
    p.add_argument("--out")
    p.set_defaults(func=cmd_bericht)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "befehl", None):
        # Ohne Unterbefehl: Oberfläche starten — der bequeme Standardweg.
        args = parser.parse_args(["gui", *(argv or [])])

    # Pflichtangaben je Aktion prüfen, die argparse allein nicht abdeckt.
    fehlend = _fehlende_pflichtfelder(args)
    if fehlend:
        parser.error(f"Für diese Aktion fehlt: {', '.join(fehlend)}")

    try:
        return int(args.func(args) or 0)
    except (ValueError, KeyError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


def _fehlende_pflichtfelder(args) -> list[str]:
    befehl, aktion = getattr(args, "befehl", ""), getattr(args, "aktion", "")
    erwartet = {
        ("partnerin", "neu"): ["pseudonym"],
        ("partnerin", "gate"): ["id", "gate"],
        ("partnerin", "widerruf"): ["id"],
        ("dreh", "neu"): ["datum"],
        ("dreh", "status"): ["id", "wert"],
        ("kalender", "planen"): ["start"],
        ("aufgabe", "erledigt"): ["id"],
        ("angebot", "setzen"): ["schluessel", "wert"],
        ("persona", "setzen"): ["schluessel"],
        ("persona", "name"): ["name"],
    }.get((befehl, aktion), [])
    return [f"--{feld}" for feld in erwartet if not getattr(args, feld, None)]


if __name__ == "__main__":
    raise SystemExit(main())
