"""Lokale Weboberfläche für CreatorDock.

Startet einen Webserver aus der Python-Standardbibliothek und öffnet die
Oberfläche im Browser. Standardmäßig lauscht er **nur auf 127.0.0.1** — die
Daten in dieser App sind zu sensibel, um sie versehentlich ins WLAN zu stellen.

Aufruf:  creatordock gui
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

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
from creatordock.store import ABLAGE_HINWEIS, Store

_STORE: Store | None = None


def _store() -> Store:
    if _STORE is None:  # pragma: no cover - wird von serve() immer gesetzt
        raise RuntimeError("Kein Datenspeicher gesetzt.")
    return _STORE


def _speichern():
    _store().speichern()


def _load_index_html() -> str:
    return (files("creatordock") / "web" / "index.html").read_text(encoding="utf-8")


# --- API ------------------------------------------------------------------

def api_start(_body: dict) -> dict:
    """Alles, was die Oberfläche beim Laden braucht."""
    store = _store()
    return {
        "lage": dashboard.lagebild(store),
        "projekt": store.laden()["projekt"],
        "gates": partner_mod.gate_liste(),
        "kategorien": {
            "einnahme": list(finanzen.EINNAHME_KATEGORIEN),
            "ausgabe": list(finanzen.AUSGABE_KATEGORIEN),
        },
        "plattformen": list(drehs.PLATTFORMEN),
        "dreh_status": list(drehs.STATUS_REIHENFOLGE),
        "slot_status": list(kalender.SLOT_STATUS),
        "bereiche": list(fahrplan.BEREICHE),
        "prioritaeten": list(fahrplan.PRIORITAETEN),
        "zwecke": list(kanaele.ZWECKE),
        "vorlagen": vorlagen.namen(),
        "angebot_kategorien": list(angebot.KATEGORIEN),
        "persona_felder": persona.felder(),
        "pruef_status": list(persona.PRUEF_STATUS),
        "ablage_hinweis": ABLAGE_HINWEIS,
        "datenordner": str(store.ordner),
    }


def api_lage(_body: dict) -> dict:
    return dashboard.lagebild(_store())


def api_projekt_speichern(body: dict) -> dict:
    projekt = _store().laden()["projekt"]
    for feld in ("kuenstlername", "kontakt", "notizen"):
        if feld in body:
            projekt[feld] = str(body[feld] or "").strip()
    if "ruecklage_satz" in body:
        satz = float(body["ruecklage_satz"])
        if not 0 <= satz <= 1:
            raise ValueError("Der Rücklage-Satz muss zwischen 0 und 1 liegen (0,25 = 25 %).")
        projekt["ruecklage_satz"] = satz
    if "vorjahresumsatz" in body:
        projekt["vorjahresumsatz"] = max(0.0, float(body["vorjahresumsatz"] or 0))
    _speichern()
    return {"projekt": projekt, "lage": dashboard.lagebild(_store())}


def api_seed(body: dict) -> dict:
    angelegt = seed.befuellen(_store(), kuenstlername=str(body.get("kuenstlername", "")))
    _speichern()
    return {"angelegt": angelegt, "lage": dashboard.lagebild(_store())}


# Partnerinnen

def api_partnerinnen(_body: dict) -> dict:
    return {"zeilen": partner_mod.uebersicht(_store()), "gates": partner_mod.gate_liste()}


def api_partnerin_anlegen(body: dict) -> dict:
    felder = dict(body)
    pseudonym = felder.pop("pseudonym", "")  # sonst doppelt belegtes Argument
    partner_mod.anlegen(_store(), pseudonym, **felder)
    _speichern()
    return api_partnerinnen({})


def api_partnerin_gate(body: dict) -> dict:
    partner_mod.gate_setzen(
        _store(),
        body["id"],
        body["gate"],
        erfuellt=bool(body.get("erfuellt", True)),
        datum=body.get("datum"),
        notiz=body.get("notiz", ""),
    )
    _speichern()
    return api_partnerinnen({})


def api_partnerin_sti(body: dict) -> dict:
    partner_mod.sti_gueltigkeit_setzen(_store(), body["id"], body["gueltig_bis"])
    _speichern()
    return api_partnerinnen({})


def api_partnerin_widerruf(body: dict) -> dict:
    if body.get("zuruecknehmen"):
        partner_mod.widerruf_zuruecknehmen(_store(), body["id"])
    else:
        partner_mod.widerrufen(
            _store(), body["id"], datum=body.get("datum"), grund=body.get("grund", "")
        )
    _speichern()
    return {**api_partnerinnen({}), "lage": dashboard.lagebild(_store())}


def api_partnerin_ablehnen(body: dict) -> dict:
    partner_mod.ablehnen(_store(), body["id"], grund=body.get("grund", ""))
    _speichern()
    return api_partnerinnen({})


# Drehs

def api_drehs(_body: dict) -> dict:
    return {"zeilen": drehs.uebersicht(_store())}


def api_dreh_anlegen(body: dict) -> dict:
    drehs.anlegen(
        _store(),
        datum=body.get("datum", ""),
        titel=body.get("titel", ""),
        partner_ids=body.get("partner_ids", []),
        plattformen=body.get("plattformen", []),
        notizen=body.get("notizen", ""),
    )
    _speichern()
    return api_drehs({})


def api_dreh_status(body: dict) -> dict:
    drehs.status_setzen(_store(), body["id"], body["status"])
    _speichern()
    return {**api_drehs({}), "lage": dashboard.lagebild(_store())}


def api_dreh_loeschen(body: dict) -> dict:
    _store().loeschen("drehs", body["id"])
    _speichern()
    return api_drehs({})


def api_dreh_auflage(body: dict) -> dict:
    drehs.auflage_bestaetigen(
        _store(), body["id"], body["schluessel"], bool(body.get("erfuellt", True))
    )
    _speichern()
    return {**api_drehs({}), "lage": dashboard.lagebild(_store())}


# Angebot

def api_angebot(body: dict) -> dict:
    partner_id = body.get("partner_id") or None
    return {
        "partner_id": partner_id,
        "katalog": angebot.katalog(_store(), partner_id),
        "blatt": angebot.angebotsblatt(_store(), partner_id),
        "abweichungen": angebot.abweichungen(_store(), partner_id) if partner_id else [],
    }


def api_angebot_setzen(body: dict) -> dict:
    partner_id = body.get("partner_id") or None
    if partner_id:
        angebot.vereinbarung_setzen(_store(), partner_id, body["schluessel"], body["wert"])
    else:
        angebot.standard_setzen(_store(), body["schluessel"], body["wert"])
    _speichern()
    return api_angebot({"partner_id": partner_id})


def api_angebot_zuruecksetzen(body: dict) -> dict:
    partner_id = body["partner_id"]
    angebot.vereinbarung_zuruecksetzen(_store(), partner_id, body["schluessel"])
    _speichern()
    return api_angebot({"partner_id": partner_id})


# Persona

def api_persona(_body: dict) -> dict:
    store = _store()
    return {
        "steckbrief": persona.steckbrief(store),
        "identitaet": persona.identitaet(store),
        "namen": persona.namensuebersicht(store),
        "bios": persona.alle_bios(store),
        "fortschritt": persona.fortschritt(store),
    }


def api_persona_setzen(body: dict) -> dict:
    if body.get("bereich") == "identitaet":
        persona.identitaet_setzen(_store(), body["schluessel"], body.get("wert", ""))
    else:
        persona.steckbrief_setzen(_store(), body["schluessel"], body.get("wert", ""))
    _speichern()
    return api_persona({})


def api_name_vorschlagen(body: dict) -> dict:
    persona.name_vorschlagen(_store(), body.get("name", ""))
    _speichern()
    return api_persona({})


def api_name_pruefung(body: dict) -> dict:
    persona.name_pruefung_setzen(_store(), body["id"], body["plattform"], body["status"])
    _speichern()
    return api_persona({})


def api_name_waehlen(body: dict) -> dict:
    persona.name_waehlen(_store(), body["id"])
    _speichern()
    return {**api_persona({}), "lage": dashboard.lagebild(_store())}


def api_name_loeschen(body: dict) -> dict:
    _store().loeschen("namenskandidaten", body["id"])
    _speichern()
    return api_persona({})


# Kalender

def api_kalender(body: dict) -> dict:
    return {
        "zeilen": kalender.uebersicht(_store(), ab=body.get("ab"), bis=body.get("bis")),
        "auslastung": kalender.auslastung(_store()),
    }


def api_kalender_planen(body: dict) -> dict:
    neu = kalender.planen(
        _store(),
        start=body.get("start", ""),
        wochen=int(body.get("wochen", 6)),
        ersetzen=bool(body.get("ersetzen", False)),
    )
    _speichern()
    return {**api_kalender({}), "neu": len(neu)}


def api_kalender_slot(body: dict) -> dict:
    kennung = body.pop("id")
    kalender.slot_aktualisieren(_store(), kennung, **body)
    _speichern()
    return api_kalender({})


# Finanzen

def api_finanzen(body: dict) -> dict:
    store = _store()
    projekt = store.laden()["projekt"]
    jahr = int(body.get("jahr") or dashboard.lagebild(store)["projekt"]["jahr"])
    umsatz = finanzen.jahresumsatz(store, jahr)
    return {
        "jahr": jahr,
        "journal": finanzen.journal(store, jahr),
        "euer": finanzen.euer(store, jahr),
        "monate": finanzen.monatsuebersicht(store, jahr, projekt.get("ruecklage_satz", 0.25)),
        "kleinunternehmer": finanzen.kleinunternehmer_status(
            umsatz, projekt.get("vorjahresumsatz", 0.0)
        ),
        "budget": finanzen.budget_uebersicht(store),
    }


def api_buchen(body: dict) -> dict:
    finanzen.buchen(
        _store(),
        datum=body.get("datum", ""),
        beschreibung=body.get("beschreibung", ""),
        kategorie=body.get("kategorie", ""),
        einnahme=body.get("einnahme", 0),
        ausgabe=body.get("ausgabe", 0),
        beleg=body.get("beleg", ""),
    )
    _speichern()
    return api_finanzen({"jahr": body.get("jahr")})


def api_buchung_loeschen(body: dict) -> dict:
    _store().loeschen("buchungen", body["id"])
    _speichern()
    return api_finanzen({"jahr": body.get("jahr")})


def api_budget(body: dict) -> dict:
    store = _store()
    posten = store.finden("budget", body["id"])
    posten["beschafft"] = bool(body.get("beschafft", True))
    _speichern()
    return {"budget": finanzen.budget_uebersicht(store)}


# Kanäle und OPSEC

def api_kanaele(_body: dict) -> dict:
    return {"zeilen": kanaele.uebersicht(_store()), "opsec": kanaele.opsec_status(_store())}


def api_kanal_anlegen(body: dict) -> dict:
    felder = dict(body)
    plattform = felder.pop("plattform", "")  # sonst doppelt belegtes Argument
    kanaele.anlegen(_store(), plattform, **felder)
    _speichern()
    return api_kanaele({})


def api_kanal_aktualisieren(body: dict) -> dict:
    kennung = body.pop("id")
    kanaele.aktualisieren(_store(), kennung, **body)
    _speichern()
    return api_kanaele({})


def api_opsec(body: dict) -> dict:
    kanaele.opsec_setzen(_store(), body["schluessel"], bool(body.get("erledigt", True)))
    _speichern()
    return api_kanaele({})


# Fahrplan

def api_fahrplan(body: dict) -> dict:
    return {
        "zeilen": fahrplan.uebersicht(_store(), nur_offen=bool(body.get("nur_offen"))),
        "kennzahlen": fahrplan.kennzahlen(_store()),
    }


def api_aufgabe_anlegen(body: dict) -> dict:
    fahrplan.anlegen(
        _store(),
        titel=body.get("titel", ""),
        bereich=body.get("bereich", "Produktion"),
        faellig=body.get("faellig", ""),
        prioritaet=body.get("prioritaet", "mittel"),
        notiz=body.get("notiz", ""),
    )
    _speichern()
    return api_fahrplan({})


def api_aufgabe_status(body: dict) -> dict:
    fahrplan.status_setzen(_store(), body["id"], body["status"])
    _speichern()
    return api_fahrplan({})


# Vorlagen und Bericht

def api_vorlage(body: dict) -> dict:
    partner_id = body.get("partner_id") or None
    return {
        "schluessel": body.get("schluessel"),
        "partner_id": partner_id,
        "text": vorlagen.rendern(_store(), body.get("schluessel", ""), partner_id=partner_id),
    }


def api_bericht(body: dict) -> dict:
    ziel = _store().ordner / (body.get("dateiname") or "statusbericht.html")
    pfad = report.erzeugen(_store(), ziel)
    return {"pfad": str(pfad)}


_POST_ROUTES = {
    "/api/start": api_start,
    "/api/lage": api_lage,
    "/api/projekt": api_projekt_speichern,
    "/api/seed": api_seed,
    "/api/partnerinnen": api_partnerinnen,
    "/api/partnerin/anlegen": api_partnerin_anlegen,
    "/api/partnerin/gate": api_partnerin_gate,
    "/api/partnerin/sti": api_partnerin_sti,
    "/api/partnerin/widerruf": api_partnerin_widerruf,
    "/api/partnerin/ablehnen": api_partnerin_ablehnen,
    "/api/drehs": api_drehs,
    "/api/dreh/anlegen": api_dreh_anlegen,
    "/api/dreh/status": api_dreh_status,
    "/api/dreh/loeschen": api_dreh_loeschen,
    "/api/dreh/auflage": api_dreh_auflage,
    "/api/angebot": api_angebot,
    "/api/angebot/setzen": api_angebot_setzen,
    "/api/angebot/zuruecksetzen": api_angebot_zuruecksetzen,
    "/api/persona": api_persona,
    "/api/persona/setzen": api_persona_setzen,
    "/api/name/vorschlagen": api_name_vorschlagen,
    "/api/name/pruefung": api_name_pruefung,
    "/api/name/waehlen": api_name_waehlen,
    "/api/name/loeschen": api_name_loeschen,
    "/api/kalender": api_kalender,
    "/api/kalender/planen": api_kalender_planen,
    "/api/kalender/slot": api_kalender_slot,
    "/api/finanzen": api_finanzen,
    "/api/buchen": api_buchen,
    "/api/buchung/loeschen": api_buchung_loeschen,
    "/api/budget": api_budget,
    "/api/kanaele": api_kanaele,
    "/api/kanal/anlegen": api_kanal_anlegen,
    "/api/kanal/aktualisieren": api_kanal_aktualisieren,
    "/api/opsec": api_opsec,
    "/api/fahrplan": api_fahrplan,
    "/api/aufgabe/anlegen": api_aufgabe_anlegen,
    "/api/aufgabe/status": api_aufgabe_status,
    "/api/vorlage": api_vorlage,
    "/api/bericht": api_bericht,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # Konsole ruhig halten
        pass

    def _json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html = _load_index_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/favicon.ico":
            self.send_response(204)  # kein Icon — spart einen 404 in der Konsole
            self.end_headers()
        else:
            self._json({"error": "Nicht gefunden"}, status=404)

    def do_POST(self) -> None:
        handler = _POST_ROUTES.get(self.path)
        if handler is None:
            self._json({"error": "Nicht gefunden"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            roh = self.rfile.read(length) if length else b"{}"
            body = json.loads(roh or b"{}")
            self._json(handler(body))
        except KeyError as exc:
            self._json({"error": f"Nicht gefunden: {exc}"}, status=404)
        except (ValueError, TypeError) as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 — dem Nutzer eine Meldung geben
            self._json({"error": f"Unerwarteter Fehler: {exc}"}, status=500)


def serve(
    store: Store,
    host: str = "127.0.0.1",
    port: int = 8770,
    open_browser: bool = True,
) -> None:
    """Startet die Oberfläche. Bewusst nur lokal erreichbar."""
    global _STORE
    _STORE = store
    store.laden()

    server = None
    for kandidat in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, kandidat), Handler)
            port = kandidat
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"Kein freier Port im Bereich {port}–{port + 20} gefunden.")

    url = f"http://{host}:{port}/"
    print(f"CreatorDock läuft auf {url}")
    print(f"Datenordner: {store.ordner}")
    print("\nDie Oberfläche ist nur auf diesem Rechner erreichbar.")
    print("Zum Beenden Strg+C drücken.\n")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCreatorDock beendet.")
    finally:
        server.server_close()
