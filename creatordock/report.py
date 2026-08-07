"""Statusbericht als eigenständige HTML-Datei (ohne externe Bibliotheken).

Der Bericht ist bewusst so gehalten, dass er auch ausgedruckt oder an einen
Steuerberater weitergegeben werden kann — er enthält deshalb **keine**
Pseudonym-fremden Daten und keine Aktenzeichen der verschlüsselten Ablage.
"""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from creatordock import dashboard, drehs, fahrplan, finanzen, kalender, kanaele
from creatordock import partnerinnen as partner_mod
from creatordock.store import Store

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       margin: 0; padding: 2rem 1.25rem 4rem; line-height: 1.55;
       background: #fbfbfd; color: #16181d; }
main { max-width: 60rem; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .2rem; }
h2 { font-size: 1.15rem; margin: 2.2rem 0 .6rem; padding-bottom: .3rem;
     border-bottom: 1px solid #dcdfe6; }
.meta { color: #6b7280; font-size: .85rem; margin-bottom: 1.5rem; }
table { border-collapse: collapse; width: 100%; font-size: .87rem; margin: .4rem 0 1rem; }
th, td { text-align: left; padding: .42rem .55rem; border-bottom: 1px solid #e6e8ec;
         vertical-align: top; }
th { background: #f2f3f6; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.kacheln { display: grid; grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
           gap: .7rem; margin: 1rem 0; }
.kachel { background: #fff; border: 1px solid #e2e5ea; border-radius: .55rem; padding: .7rem .8rem; }
.kachel .wert { font-size: 1.35rem; font-weight: 650; }
.kachel .label { font-size: .74rem; color: #6b7280; text-transform: uppercase;
                 letter-spacing: .04em; }
.warn { border-left: 3px solid; padding: .5rem .75rem; margin: .4rem 0; border-radius: .3rem;
        font-size: .88rem; background: #fff; }
.warn.kritisch { border-color: #c0392b; background: #fdf2f1; }
.warn.warnung  { border-color: #d98324; background: #fdf8f0; }
.warn.hinweis  { border-color: #6b7280; }
.pill { display: inline-block; padding: .08rem .45rem; border-radius: 999px;
        font-size: .75rem; border: 1px solid #cfd4dc; }
.ja { color: #1a7f47; font-weight: 600; }
.nein { color: #c0392b; font-weight: 600; }
.fuss { margin-top: 3rem; font-size: .8rem; color: #6b7280; border-top: 1px solid #dcdfe6;
        padding-top: .8rem; }
@media (prefers-color-scheme: dark) {
  body { background: #14161a; color: #e6e8ec; }
  th { background: #20242b; } .kachel, .warn { background: #1a1d23; border-color: #2c313a; }
  th, td { border-color: #2c313a; } h2 { border-color: #2c313a; }
  .warn.kritisch { background: #2a1a19; } .warn.warnung { background: #29221a; }
}
"""


def erzeugen(store: Store, ziel: str | Path, stichtag: str | None = None) -> Path:
    """Schreibt den Statusbericht und gibt den Pfad zurück."""
    ziel = Path(ziel).expanduser()
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(html_bericht(store, stichtag), encoding="utf-8")
    return ziel


def html_bericht(store: Store, stichtag: str | None = None) -> str:
    heute = stichtag or date.today().isoformat()
    lage = dashboard.lagebild(store, stichtag=heute)
    projekt = lage["projekt"]
    jahr = projekt["jahr"]

    teile = [
        "<!doctype html><html lang='de'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>CreatorDock — Statusbericht {heute}</title>",
        f"<style>{CSS}</style></head><body><main>",
        f"<h1>Statusbericht{_wenn(projekt['kuenstlername'], ' — ' + _e(projekt['kuenstlername']))}</h1>",
        f"<p class='meta'>Stand {heute} · Projektstart {_e(projekt['start'] or '—')} · "
        "erzeugt von CreatorDock, lokal auf diesem Rechner</p>",
    ]

    teile.append(_kacheln(lage))
    teile.append(_warnungen(lage["warnungen"]))
    teile.append(_partnerinnen(store))
    teile.append(_drehs(store))
    teile.append(_kalender(store, heute))
    teile.append(_finanzen(store, jahr, lage))
    teile.append(_kanaele(store))
    teile.append(_fahrplan(store, heute))

    teile.append(
        "<p class='fuss'>Dieser Bericht ersetzt keine Steuer- oder Rechtsberatung. "
        "Die Steuerrücklage ist ein Richtwert. Personenbezogene Dokumente "
        "(Ausweise, Verträge, Nachweise) sind bewusst nicht Teil dieses Berichts.</p>"
    )
    teile.append("</main></body></html>")
    return "".join(teile)


# --- Abschnitte -----------------------------------------------------------

def _kacheln(lage: dict) -> str:
    f = lage["finanzen"]
    kacheln = [
        ("Partnerinnen freigegeben", f"{lage['partnerinnen']['freigegeben']} / {lage['partnerinnen']['gesamt']}"),
        ("Drehs veröffentlicht", str(lage["drehs"]["pipeline"].get("veröffentlicht", 0))),
        ("Kalender-Slots", str(lage["kalender"]["gesamt"])),
        ("Einnahmen", _eur(f["einnahmen"])),
        ("Ausgaben", _eur(f["ausgaben"])),
        ("Gewinn", _eur(f["gewinn"])),
        ("Steuerrücklage", _eur(f["ruecklage"])),
        ("Aufgaben offen", str(lage["fahrplan"]["offen"])),
    ]
    inner = "".join(
        f"<div class='kachel'><div class='label'>{_e(label)}</div>"
        f"<div class='wert'>{_e(wert)}</div></div>"
        for label, wert in kacheln
    )
    return f"<div class='kacheln'>{inner}</div>"


def _warnungen(meldungen: list[dict]) -> str:
    if not meldungen:
        return "<h2>Offene Risiken</h2><p>Keine offenen Punkte.</p>"
    zeilen = "".join(
        f"<div class='warn {_e(m['stufe'])}'><strong>{_e(m['bereich'])}</strong> — {_e(m['text'])}</div>"
        for m in meldungen
    )
    return f"<h2>Offene Risiken ({len(meldungen)})</h2>{zeilen}"


def _partnerinnen(store: Store) -> str:
    zeilen = partner_mod.uebersicht(store)
    if not zeilen:
        return "<h2>Partnerinnen</h2><p>Noch keine erfasst.</p>"
    körper = "".join(
        "<tr>"
        f"<td>{_e(z['pseudonym'])}</td>"
        f"<td><span class='pill'>{_e(z['status'])}</span></td>"
        f"<td class='num'>{z['erledigt']} / {z['gesamt']}</td>"
        f"<td class='{'ja' if z['freigegeben'] else 'nein'}'>{'ja' if z['freigegeben'] else 'nein'}</td>"
        f"<td>{_e(', '.join(z['offen']) or '—')}</td>"
        "</tr>"
        for z in zeilen
    )
    return (
        "<h2>Partnerinnen und Vetting-Stand</h2>"
        "<table><thead><tr><th>Pseudonym</th><th>Status</th><th class='num'>Schritte</th>"
        f"<th>Freigabe</th><th>Offen</th></tr></thead><tbody>{körper}</tbody></table>"
    )


def _drehs(store: Store) -> str:
    zeilen = drehs.uebersicht(store)
    if not zeilen:
        return "<h2>Drehs</h2><p>Noch keine geplant.</p>"
    körper = "".join(
        "<tr>"
        f"<td>{_e(z['datum'])}</td><td>{_e(z['titel'])}</td>"
        f"<td>{_e(', '.join(z['partner']) or 'solo')}</td>"
        f"<td>{_e(', '.join(z['plattformen']) or '—')}</td>"
        f"<td><span class='pill'>{_e(z['status'])}</span>"
        f"{' <span class=nein>gesperrt</span>' if z['gesperrt'] else ''}</td>"
        f"<td class='{'ja' if z['startklar'] else 'nein'}'>{'ja' if z['startklar'] else 'nein'}</td>"
        "</tr>"
        for z in zeilen
    )
    return (
        "<h2>Drehs</h2>"
        "<table><thead><tr><th>Datum</th><th>Titel</th><th>Partnerinnen</th>"
        f"<th>Plattformen</th><th>Status</th><th>Startklar</th></tr></thead><tbody>{körper}</tbody></table>"
    )


def _kalender(store: Store, heute: str) -> str:
    zeilen = kalender.uebersicht(store, ab=heute)[:20]
    if not zeilen:
        return "<h2>Content-Kalender</h2><p>Keine anstehenden Slots.</p>"
    körper = "".join(
        "<tr>"
        f"<td>{_e(z.get('datum', ''))} {_e(z.get('wochentag', ''))}</td>"
        f"<td><span class='pill'>{_e(z.get('typ', ''))}</span></td>"
        f"<td>{_e(z.get('kanal', ''))}</td><td>{_e(z.get('thema', ''))}</td>"
        f"<td>{_e(z.get('status', ''))}</td>"
        "</tr>"
        for z in zeilen
    )
    return (
        "<h2>Content-Kalender (nächste Slots)</h2>"
        "<table><thead><tr><th>Termin</th><th>Typ</th><th>Kanal</th><th>Thema</th>"
        f"<th>Status</th></tr></thead><tbody>{körper}</tbody></table>"
    )


def _finanzen(store: Store, jahr: int, lage: dict) -> str:
    monate = [m for m in finanzen.monatsuebersicht(store, jahr, lage["finanzen"]["ruecklage_satz"])
              if m["umsatz"] or m["ausgaben"]]
    ku = lage["kleinunternehmer"]
    teile = [f"<h2>Finanzen {jahr}</h2>"]

    if monate:
        körper = "".join(
            "<tr>"
            f"<td>{_e(m['monat'])}</td><td class='num'>{_eur(m['umsatz'])}</td>"
            f"<td class='num'>{_eur(m['ausgaben'])}</td><td class='num'>{_eur(m['gewinn'])}</td>"
            f"<td class='num'>{_eur(m['ruecklage'])}</td>"
            f"<td class='num'>{_eur(m['umsatz_kumuliert'])}</td>"
            "</tr>"
            for m in monate
        )
        teile.append(
            "<table><thead><tr><th>Monat</th><th class='num'>Umsatz</th>"
            "<th class='num'>Ausgaben</th><th class='num'>Gewinn</th>"
            "<th class='num'>Rücklage</th><th class='num'>Umsatz kumuliert</th>"
            f"</tr></thead><tbody>{körper}</tbody></table>"
        )
    else:
        teile.append("<p>Noch keine Buchungen erfasst.</p>")

    teile.append(
        f"<p><strong>Kleinunternehmerregelung:</strong> "
        f"{'anwendbar' if ku['anwendbar'] else 'nicht mehr anwendbar'} — "
        f"laufender Umsatz {_eur(ku['laufender_umsatz'])}, "
        f"Vorjahr {_eur(ku['vorjahresumsatz'])} "
        f"(Grenzen: {_eur(ku['grenze_vorjahr'])} Vorjahr / {_eur(ku['grenze_laufend'])} laufend).</p>"
    )
    for hinweis in ku["hinweise"]:
        teile.append(f"<p class='meta'>{_e(hinweis)}</p>")

    budget = lage["budget"]
    if budget["posten"]:
        teile.append(
            f"<p><strong>Ausrüstungsbudget:</strong> noch offen "
            f"{_eur(budget['offen_von'])}–{_eur(budget['offen_bis'])} "
            f"({budget['offen_anzahl']} von {len(budget['posten'])} Posten).</p>"
        )
    return "".join(teile)


def _kanaele(store: Store) -> str:
    zeilen = kanaele.uebersicht(store)
    if not zeilen:
        return "<h2>Kanäle</h2><p>Noch keine erfasst.</p>"
    körper = "".join(
        "<tr>"
        f"<td>{_e(k.get('plattform', ''))}</td><td>{_e(k.get('handle', '') or '—')}</td>"
        f"<td>{_e(k.get('zweck', ''))}</td>"
        f"<td class='{'ja' if k.get('angelegt') else 'nein'}'>{'ja' if k.get('angelegt') else 'nein'}</td>"
        f"<td class='{'ja' if k.get('zwei_faktor') else 'nein'}'>{'ja' if k.get('zwei_faktor') else 'nein'}</td>"
        "</tr>"
        for k in zeilen
    )
    opsec = kanaele.opsec_status(store)
    return (
        "<h2>Kanäle und OPSEC</h2>"
        "<table><thead><tr><th>Plattform</th><th>Handle</th><th>Zweck</th>"
        f"<th>Angelegt</th><th>2FA</th></tr></thead><tbody>{körper}</tbody></table>"
        f"<p class='meta'>OPSEC-Setup: {opsec['setup_erledigt']} von "
        f"{opsec['setup_gesamt']} Punkten erledigt.</p>"
    )


def _fahrplan(store: Store, heute: str) -> str:
    zeilen = fahrplan.uebersicht(store, nur_offen=True, stichtag=heute)
    if not zeilen:
        return "<h2>Fahrplan</h2><p>Keine offenen Aufgaben.</p>"
    körper = "".join(
        "<tr>"
        f"<td>{_e(a.get('faellig', '') or '—')}{' ⚠' if a['ueberfaellig'] else ''}</td>"
        f"<td>{_e(a.get('titel', ''))}</td><td>{_e(a.get('bereich', ''))}</td>"
        f"<td><span class='pill'>{_e(a.get('prioritaet', ''))}</span></td>"
        f"<td>{_e(a.get('status', ''))}</td>"
        "</tr>"
        for a in zeilen
    )
    return (
        f"<h2>Fahrplan — offene Aufgaben ({len(zeilen)})</h2>"
        "<table><thead><tr><th>Fällig</th><th>Aufgabe</th><th>Bereich</th>"
        f"<th>Priorität</th><th>Status</th></tr></thead><tbody>{körper}</tbody></table>"
    )


def _e(wert) -> str:
    return html.escape(str(wert if wert is not None else ""))


def _eur(betrag) -> str:
    return f"{float(betrag or 0):,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")


def _wenn(bedingung, text: str) -> str:
    return text if bedingung else ""
