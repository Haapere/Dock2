"""Lokales Dashboard (FastAPI + Jinja2).

Läuft auf ``localhost`` und zeigt die Auswertung aus der lokalen Datenbank:
Tagesübersicht, Wochentrend und die aktuellen Vorschläge. Kein Internetzugriff,
keine externen Skripte oder Schriften — die Seite funktioniert offline.

Start über ``fokusradar dashboard``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fokusradar import __version__, timeutil
from fokusradar.config import Config
from fokusradar.processing.analysis import DayAnalysis, analyze_day, last_days, store_analysis
from fokusradar.processing.categories import Categorizer
from fokusradar.processing.exclusions import ExclusionError, ExclusionList
from fokusradar.storage.db import Database

TEMPLATE_DIR = Path(__file__).parent / "templates"
WEEK_LENGTH = 7

# Der Import steht bewusst auf Modulebene: FastAPI löst die Typannotationen der
# Endpunkte über die Modul-Namen auf — ein Import innerhalb der Funktion würde
# ``Request`` fälschlich zu einem Query-Parameter machen.
try:  # pragma: no cover - hängt an der Installation
    from fastapi import FastAPI, Form, Request
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.templating import Jinja2Templates

    FASTAPI_VERFUEGBAR = True
except ImportError:  # pragma: no cover
    FASTAPI_VERFUEGBAR = False


class DashboardUnavailable(RuntimeError):
    """FastAPI/Jinja2 sind nicht installiert."""


# -- Aufbereitung (ohne Web-Framework, dadurch direkt testbar) ---------------


def _percent(part: float, whole: float) -> float:
    return part / whole * 100 if whole else 0.0


def day_context(
    database: Database, categorizer: Categorizer, config: Config, day: date
) -> dict[str, Any]:
    """Alle Werte der Tagesansicht aufbereiten."""
    analysis = analyze_day(database, categorizer, day, config.analysis)
    store_analysis(database, analysis)

    kategorien = [
        {
            "name": name,
            "art": categorizer.kind_of(name),
            "sekunden": seconds,
            "dauer": timeutil.format_duration(seconds),
            "anteil": _percent(seconds, analysis.total_seconds),
        }
        for name, seconds in sorted(
            analysis.category_seconds.items(), key=lambda item: -item[1]
        )
    ]
    apps = [
        {
            "prozess": app.process_name,
            "kategorie": app.category,
            "art": categorizer.kind_of(app.category),
            "dauer": timeutil.format_duration(app.seconds),
            "aufrufe": app.events,
            "anteil": _percent(app.seconds, analysis.total_seconds),
        }
        for app in analysis.apps[:12]
    ]
    sessions = [
        {
            "von": timeutil.to_local(session.start).strftime("%H:%M"),
            "bis": timeutil.to_local(session.end).strftime("%H:%M"),
            "dauer": timeutil.format_duration(session.focus_seconds),
            "unterbrechungen": session.interruptions,
            "programm": session.main_process,
        }
        for session in analysis.focus_sessions
    ]

    heute = timeutil.parse_day("heute")
    return {
        "titel": f"Tag {day.isoformat()}",
        "version": __version__,
        "tag": day,
        "tag_iso": day.isoformat(),
        "vortag": (day - timedelta(days=1)).isoformat(),
        "folgetag": (day + timedelta(days=1)).isoformat() if day < heute else None,
        "ist_heute": day == heute,
        "analyse": analysis,
        "kennzahlen": _kennzahlen(analysis),
        "kategorien": kategorien,
        "apps": apps,
        "sessions": sessions,
        "zeitstrahl": timeline_segments(database, categorizer, day),
        "vorschlaege": database.suggestions(day=day),
    }


def _kennzahlen(analysis: DayAnalysis) -> list[dict[str, str]]:
    """Die fünf Kennzahlen über der Tagesansicht."""
    return [
        {"label": "Erfasste Zeit", "wert": timeutil.format_duration(analysis.total_seconds)},
        {"label": "Fokuszeit", "wert": f"{analysis.focus_share * 100:.0f} %",
         "zusatz": timeutil.format_duration(analysis.focus_seconds)},
        {"label": "Längster Block", "wert": timeutil.format_duration(analysis.longest_focus_seconds)},
        {"label": "Wechsel/Stunde", "wert": f"{analysis.switches_per_hour:.0f}",
         "zusatz": f"{analysis.switches} gesamt"},
        {"label": "Ablenkung", "wert": f"{analysis.distraction_share * 100:.0f} %",
         "zusatz": timeutil.format_duration(analysis.distraction_seconds)},
    ]


def timeline_segments(
    database: Database, categorizer: Categorizer, day: date
) -> dict[str, Any]:
    """Balken für den Tagesstrahl: je Fensternutzung ein Abschnitt."""
    events = database.window_events(day=day, ascending=True)
    events = [event for event in events if event.effective_seconds > 0]
    if not events:
        return {"segmente": [], "stunden": [], "von": None, "bis": None}

    starts = [timeutil.to_local(event.started_at) for event in events]
    ends = [
        timeutil.to_local(event.started_at) + timedelta(seconds=event.effective_seconds)
        for event in events
    ]
    beginn = min(starts).replace(minute=0, second=0, microsecond=0)
    ende = max(ends)
    ende = (ende + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    spanne = max((ende - beginn).total_seconds(), 1)

    segmente = []
    for event, start, stop in zip(events, starts, ends):
        links = (start - beginn).total_seconds() / spanne * 100
        breite = max((stop - start).total_seconds() / spanne * 100, 0.15)
        segmente.append(
            {
                "links": links,
                "breite": min(breite, 100 - links),
                "art": categorizer.kind_of(event.category),
                "titel": (
                    f"{start.strftime('%H:%M')}–{stop.strftime('%H:%M')} "
                    f"{event.process_name} ({event.category or 'ohne Kategorie'})"
                ),
            }
        )

    stunden = []
    marke = beginn
    while marke <= ende:
        stunden.append(
            {
                "links": (marke - beginn).total_seconds() / spanne * 100,
                "label": marke.strftime("%H"),
            }
        )
        marke += timedelta(hours=max(1, round(spanne / 3600 / 12)))

    return {
        "segmente": segmente,
        "stunden": stunden,
        "von": beginn.strftime("%H:%M"),
        "bis": ende.strftime("%H:%M"),
    }


def week_context(
    database: Database, categorizer: Categorizer, config: Config, end: date
) -> dict[str, Any]:
    """Werte der Wochenansicht aufbereiten."""
    tage = last_days(end, WEEK_LENGTH)
    analysen = [analyze_day(database, categorizer, tag, config.analysis) for tag in tage]
    for analyse in analysen:
        if analyse.has_data:
            store_analysis(database, analyse)
    hoechstwert = max((a.total_seconds for a in analysen), default=0)

    zeilen = []
    for analyse in analysen:
        neutral = max(
            analyse.total_seconds - analyse.focus_seconds - analyse.distraction_seconds, 0
        )
        zeilen.append(
            {
                "tag": analyse.day,
                "tag_iso": analyse.day.isoformat(),
                "wochentag": _WOCHENTAGE[analyse.day.weekday()],
                "gesamt": timeutil.format_duration(analyse.total_seconds),
                "breite": _percent(analyse.total_seconds, hoechstwert or 1),
                "fokus": _percent(analyse.focus_seconds, analyse.total_seconds or 1),
                "neutral": _percent(neutral, analyse.total_seconds or 1),
                "ablenkung": _percent(analyse.distraction_seconds, analyse.total_seconds or 1),
                "fokus_dauer": timeutil.format_duration(analyse.focus_seconds),
                "wechsel": f"{analyse.switches_per_hour:.0f}",
                "leer": not analyse.has_data,
            }
        )

    gesamt = sum(a.total_seconds for a in analysen)
    fokus = sum(a.focus_seconds for a in analysen)
    ablenkung = sum(a.distraction_seconds for a in analysen)
    return {
        "titel": "Wochentrend",
        "version": __version__,
        "tag_iso": end.isoformat(),
        "zeilen": zeilen,
        "kennzahlen": [
            {"label": "Erfasste Zeit", "wert": timeutil.format_duration(gesamt)},
            {"label": "Fokuszeit", "wert": f"{_percent(fokus, gesamt or 1):.0f} %",
             "zusatz": timeutil.format_duration(fokus)},
            {"label": "Ablenkung", "wert": f"{_percent(ablenkung, gesamt or 1):.0f} %",
             "zusatz": timeutil.format_duration(ablenkung)},
            {"label": "Tage mit Daten", "wert": str(sum(1 for a in analysen if a.has_data))},
        ],
        "vorschlaege": database.suggestions(),
    }


_WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def day_json(
    database: Database, categorizer: Categorizer, config: Config, day: date
) -> dict[str, Any]:
    """Maschinenlesbare Tageszusammenfassung (Grundlage für Phase 4/5)."""
    analysis = analyze_day(database, categorizer, day, config.analysis)
    return {
        "datum": day.isoformat(),
        "erfasste_sekunden": analysis.total_seconds,
        "fokus_sekunden": analysis.focus_seconds,
        "ablenkung_sekunden": analysis.distraction_seconds,
        "wechsel": analysis.switches,
        "wechsel_pro_stunde": round(analysis.switches_per_hour, 1),
        "laengster_fokusblock_sekunden": analysis.longest_focus_seconds,
        "kategorien_sekunden": analysis.category_seconds,
        "top_ablenkungen": analysis.top_distractions_json(),
        "fokus_sessions": [
            {
                "von": timeutil.to_local(session.start).isoformat(),
                "bis": timeutil.to_local(session.end).isoformat(),
                "fokus_sekunden": session.focus_seconds,
                "unterbrechungen": session.interruptions,
                "programm": session.main_process,
            }
            for session in analysis.focus_sessions
        ],
        "vorschlaege": analysis.suggestions,
    }


# -- Web-Anwendung ----------------------------------------------------------


def create_app(config: Config, categorizer: Categorizer | None = None):
    """FastAPI-Anwendung erzeugen."""
    if not FASTAPI_VERFUEGBAR:  # pragma: no cover - hängt an der Installation
        raise DashboardUnavailable(
            "Für das Dashboard werden FastAPI und Jinja2 benötigt:\n"
            '    pip install "fokusradar[dashboard]"'
        )

    rules = categorizer or Categorizer.load(config.categories_path)
    with Database.from_config(config) as vorbereitung:
        vorbereitung.seed_exclusions(ExclusionList.load_template(config.exclusions_path))
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    templates.env.filters["dauer"] = timeutil.format_duration
    app = FastAPI(title="FokusRadar", version=__version__, docs_url=None, redoc_url=None)

    def _database() -> Database:
        return Database.from_config(config)

    def _tag(datum: str | None) -> date:
        if not datum:
            return timeutil.parse_day("heute")
        try:
            return date.fromisoformat(datum)
        except ValueError:
            return timeutil.parse_day("heute")

    @app.get("/")
    def start():
        return RedirectResponse(f"/tag/{timeutil.parse_day('heute').isoformat()}")

    @app.get("/tag/{datum}", response_class=HTMLResponse)
    def tag(request: Request, datum: str):
        with _database() as database:
            context = day_context(database, rules, config, _tag(datum))
        return templates.TemplateResponse(request, "tag.html", context)

    @app.get("/woche", response_class=HTMLResponse)
    def woche(request: Request, bis: str | None = None):
        with _database() as database:
            context = week_context(database, rules, config, _tag(bis))
        return templates.TemplateResponse(request, "woche.html", context)

    @app.post("/vorschlag/{vorschlag_id}/erledigt")
    def vorschlag_erledigt(vorschlag_id: int, ziel: str = "/"):
        # Ziel kommt als Query-Parameter, damit das Dashboard ohne
        # python-multipart auskommt.
        with _database() as database:
            database.dismiss_suggestion(vorschlag_id)
        return RedirectResponse(ziel if ziel.startswith("/") else "/", status_code=303)

    @app.get("/ausschluss", response_class=HTMLResponse)
    def ausschluss(request: Request, meldung: str | None = None):
        with _database() as database:
            liste = database.exclusions()
        return templates.TemplateResponse(
            request,
            "ausschluss.html",
            {
                "titel": "Ausschlussliste",
                "version": __version__,
                "tag_iso": timeutil.parse_day("heute").isoformat(),
                "regeln": list(liste),
                "meldung": meldung,
                "vorlage": str(config.exclusions_path),
            },
        )

    @app.post("/ausschluss/hinzufuegen")
    def ausschluss_hinzufuegen(muster: str = Form(...), typ: str = Form("process")):
        muster = muster.strip()
        if not muster:
            return RedirectResponse("/ausschluss?meldung=leeres+Muster", status_code=303)
        try:
            with _database() as database:
                neu = database.add_exclusion(muster, typ)
        except ExclusionError as exc:
            return RedirectResponse(
                f"/ausschluss?meldung={quote(str(exc))}", status_code=303
            )
        meldung = (
            f"{muster} steht schon auf der Liste."
            if neu is None
            else f"{muster} aufgenommen — passende Fenster werden ab sofort nicht erfasst."
        )
        return RedirectResponse(f"/ausschluss?meldung={quote(meldung)}", status_code=303)

    @app.post("/ausschluss/{regel_id}/entfernen")
    def ausschluss_entfernen(regel_id: int):
        with _database() as database:
            entfernt = database.remove_exclusion(regel_id)
        meldung = "Muster entfernt." if entfernt else "Muster gab es nicht mehr."
        return RedirectResponse(f"/ausschluss?meldung={quote(meldung)}", status_code=303)

    @app.get("/api/tag/{datum}")
    def api_tag(datum: str):
        with _database() as database:
            return day_json(database, rules, config, _tag(datum))

    return app


def run_dashboard(
    config: Config,
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool = False,
) -> None:  # pragma: no cover - startet einen echten Server
    """Dashboard starten (blockiert bis Strg+C)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise DashboardUnavailable(
            "Für das Dashboard wird uvicorn benötigt:\n"
            '    pip install "fokusradar[dashboard]"'
        ) from exc

    app = create_app(config)
    host = host or config.dashboard.host
    port = port or config.dashboard.port
    adresse = f"http://{'localhost' if host in {'127.0.0.1', '0.0.0.0'} else host}:{port}/"
    print(f"FokusRadar-Dashboard: {adresse}")
    print("Beenden mit Strg+C.")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(adresse)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
