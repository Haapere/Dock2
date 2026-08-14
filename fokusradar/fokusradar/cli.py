"""Kommandozeile von FokusRadar.

    fokusradar track      # Erfassung starten (läuft im Vordergrund)
    fokusradar status     # Backends, Datenbank, laufende Sitzung
    fokusradar log        # Rohdaten: letzte Fensterwechsel
    fokusradar zeiten     # Zeit je Programm an einem Tag
    fokusradar aktivitaet # Messpunkte des Aktivitätslevels
    fokusradar auswerten  # Tagesauswertung mit Fokus, Ablenkung, Vorschlägen
    fokusradar kategorien # Regeln anzeigen und ausprobieren
    fokusradar ausschluss # Ausschlussliste pflegen (was nie erfasst wird)
    fokusradar screenshots      # erkannte Texte der Aufnahmen ansehen
    fokusradar verschluesseln   # Datenbank auf SQLCipher umstellen
    fokusradar cloud      # Vorschläge über die Claude-API holen
    fokusradar bild       # einzelnes Bildschirmfoto ansehen lassen
    fokusradar kosten     # Verbrauch und Kosten der Cloud-Analyse
    fokusradar android    # Begleiter auf dem Handy einrichten und ansehen
    fokusradar dashboard  # lokale Weboberfläche starten
    fokusradar config     # Konfiguration anzeigen oder anlegen
"""

from __future__ import annotations

import argparse
import json
import signal
import stat
import sys
import threading
from datetime import date
from pathlib import Path

from fokusradar import __version__, timeutil
from fokusradar.agent import Tracker
from fokusradar.android import sync as android_sync
from fokusradar.capture import create_screenshot_backend, create_window_backend
from fokusradar.capture.screenshots import screenshot_filename
from fokusradar.cloud import (
    PRICE_DATE,
    CloudAnalyzer,
    CloudError,
    build_day_payload,
    build_week_payload,
    collect_ocr_snippets,
    format_usd,
    price_for,
    vision,
)
from fokusradar.config import (
    Config,
    ConfigError,
    default_config_path,
    load_config,
    write_default_config,
)
from fokusradar.dashboard.app import DashboardUnavailable, run_dashboard
from fokusradar.processing.analysis import analyze_day, last_days, store_analysis
from fokusradar.processing.categories import (
    Categorizer,
    CategoryError,
    write_default_categories,
)
from fokusradar.processing.exclusions import (
    ExclusionError,
    ExclusionList,
    write_default_exclusions,
)
from fokusradar.storage import crypto
from fokusradar.storage.db import Database, DatabaseLocked


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fokusradar",
        description=(
            "FokusRadar — lokaler Aktivitäts-Monitor. Erfasst aktives Fenster und "
            "Aktivitätslevel in einer lokalen SQLite-Datenbank."
        ),
    )
    parser.add_argument("--version", action="version", version=f"FokusRadar {__version__}")
    parser.add_argument(
        "--config",
        type=Path,
        metavar="DATEI",
        help="Pfad zur Konfigurationsdatei (Vorgabe: Benutzerprofil)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        metavar="DATEI",
        help="Pfad zur Datenbank (überschreibt die Konfiguration)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    track = subparsers.add_parser("track", help="Erfassung starten")
    track.add_argument(
        "--intervall", type=float, metavar="SEK", help="Abstand zwischen zwei Abfragen"
    )
    track.add_argument(
        "--idle-schwelle",
        type=float,
        metavar="SEK",
        help="Ab dieser Zeit ohne Eingabe gilt die Zeit als Pause",
    )
    track.add_argument(
        "--dauer",
        type=float,
        metavar="SEK",
        help="nach dieser Zeit automatisch beenden (Vorgabe: bis Strg+C)",
    )
    track.add_argument(
        "-v", "--ausfuehrlich", action="store_true", help="jeden Fensterwechsel anzeigen"
    )
    track.set_defaults(func=_cmd_track)

    status = subparsers.add_parser("status", help="Zustand von Erfassung und Datenbank")
    status.set_defaults(func=_cmd_status)

    log = subparsers.add_parser("log", help="letzte Fensternutzungen anzeigen")
    log.add_argument("--tag", metavar="TAG", help="heute, gestern, -3 oder JJJJ-MM-TT")
    log.add_argument("--anzahl", type=int, default=20, metavar="N", help="Vorgabe: 20")
    log.set_defaults(func=_cmd_log)

    zeiten = subparsers.add_parser("zeiten", help="Zeit je Programm an einem Tag")
    zeiten.add_argument("--tag", default="heute", metavar="TAG", help="Vorgabe: heute")
    zeiten.add_argument("--anzahl", type=int, default=15, metavar="N", help="Vorgabe: 15")
    zeiten.set_defaults(func=_cmd_zeiten)

    aktivitaet = subparsers.add_parser(
        "aktivitaet", help="Messpunkte des Aktivitätslevels anzeigen"
    )
    aktivitaet.add_argument("--tag", default="heute", metavar="TAG", help="Vorgabe: heute")
    aktivitaet.add_argument("--anzahl", type=int, default=20, metavar="N", help="Vorgabe: 20")
    aktivitaet.set_defaults(func=_cmd_aktivitaet)

    auswerten = subparsers.add_parser(
        "auswerten", help="Tagesauswertung: Fokus, Ablenkung, Vorschläge"
    )
    auswerten.add_argument("--tag", default="heute", metavar="TAG", help="Vorgabe: heute")
    auswerten.add_argument(
        "--woche",
        action="store_true",
        help="zusätzlich den Trend der letzten sieben Tage zeigen",
    )
    auswerten.add_argument(
        "--nicht-speichern",
        action="store_true",
        help="Zusammenfassung und Vorschläge nur anzeigen, nicht speichern",
    )
    auswerten.set_defaults(func=_cmd_auswerten)

    kategorien = subparsers.add_parser(
        "kategorien", help="Regeln anzeigen oder eine Zuordnung ausprobieren"
    )
    kategorien.add_argument(
        "--test", metavar="PROZESS", help="Kategorie für diesen Prozessnamen bestimmen"
    )
    kategorien.add_argument("--titel", metavar="TITEL", help="Fenstertitel zum Test")
    kategorien.set_defaults(func=_cmd_kategorien)

    ausschluss = subparsers.add_parser(
        "ausschluss", help="Ausschlussliste anzeigen und pflegen"
    )
    ausschluss_teil = ausschluss.add_subparsers(dest="aktion")
    ausschluss.set_defaults(func=_cmd_ausschluss, aktion=None)
    ausschluss_teil.add_parser("liste", help="Muster anzeigen (Vorgabe)")
    hinzufuegen = ausschluss_teil.add_parser("hinzufuegen", help="Muster aufnehmen")
    hinzufuegen.add_argument("--prozess", metavar="MUSTER", help='z. B. "keepass*.exe"')
    hinzufuegen.add_argument("--titel", metavar="MUSTER", help='z. B. "online-banking"')
    entfernen = ausschluss_teil.add_parser("entfernen", help="Muster löschen")
    entfernen.add_argument("id", type=int, help="Nummer aus 'ausschluss liste'")
    pruefen = ausschluss_teil.add_parser("pruefen", help="Fenster gegen die Liste prüfen")
    pruefen.add_argument("prozess", help="Prozessname")
    pruefen.add_argument("--titel", metavar="TITEL", help="Fenstertitel")

    screenshots = subparsers.add_parser(
        "screenshots", help="Aufnahmen und erkannte Texte anzeigen"
    )
    screenshots.add_argument("--tag", metavar="TAG", help="heute, gestern, -3 oder JJJJ-MM-TT")
    screenshots.add_argument("--anzahl", type=int, default=10, metavar="N", help="Vorgabe: 10")
    screenshots.add_argument(
        "--text", action="store_true", help="den erkannten Text vollständig ausgeben"
    )
    screenshots.set_defaults(func=_cmd_screenshots)

    verschluesseln = subparsers.add_parser(
        "verschluesseln", help="vorhandene Datenbank auf SQLCipher umstellen"
    )
    verschluesseln.add_argument(
        "--ja", action="store_true", help="ohne Rückfrage durchführen"
    )
    verschluesseln.set_defaults(func=_cmd_verschluesseln)

    cloud = subparsers.add_parser(
        "cloud", help="Vorschläge über die Claude-API holen (Hybrid-Analyse)"
    )
    cloud.add_argument("--tag", default="heute", metavar="TAG", help="Vorgabe: heute")
    cloud.add_argument(
        "--woche", action="store_true", help="Wochenrückblick statt Tagesanalyse"
    )
    cloud.add_argument(
        "--zeigen",
        action="store_true",
        help="nur anzeigen, was gesendet würde — ohne Netzwerkzugriff",
    )
    cloud.add_argument(
        "--erneut",
        action="store_true",
        help="auch dann fragen, wenn für den Tag schon Cloud-Vorschläge vorliegen",
    )
    cloud.set_defaults(func=_cmd_cloud)

    bild = subparsers.add_parser(
        "bild", help="einzelnes Bildschirmfoto ansehen lassen (Bild-Analyse)"
    )
    bild.add_argument(
        "--datei", type=Path, metavar="PFAD", help="bestimmte Aufnahme statt der neuesten"
    )
    bild.add_argument(
        "--neu", action="store_true", help="jetzt eine Aufnahme machen und die nehmen"
    )
    bild.add_argument(
        "--zeigen",
        action="store_true",
        help="nur anzeigen, was hinausginge — ohne Netzwerkzugriff",
    )
    bild.add_argument(
        "--behalten",
        action="store_true",
        help="die Aufnahme nach der Analyse nicht löschen",
    )
    bild.set_defaults(func=_cmd_bild)

    kosten = subparsers.add_parser(
        "kosten", help="Verbrauch und Kosten der Cloud-Analyse anzeigen"
    )
    kosten.add_argument("--anzahl", type=int, default=10, metavar="N", help="Vorgabe: 10")
    kosten.set_defaults(func=_cmd_kosten)

    android = subparsers.add_parser(
        "android", help="Android-Begleiter einrichten und seine Zahlen ansehen"
    )
    android.add_argument("--tag", default="heute", metavar="TAG", help="Vorgabe: heute")
    android.add_argument(
        "--token-neu",
        action="store_true",
        dest="token_neu",
        help="neues Geheimnis erzeugen und in die Konfiguration schreiben",
    )
    android.add_argument(
        "--token-zeigen",
        action="store_true",
        dest="token_zeigen",
        help="Token im Klartext ausgeben (zum Abtippen am Handy)",
    )
    android.set_defaults(func=_cmd_android)

    dashboard = subparsers.add_parser("dashboard", help="lokale Weboberfläche starten")
    dashboard.add_argument("--host", metavar="ADRESSE", help="Vorgabe: 127.0.0.1")
    dashboard.add_argument("--port", type=int, metavar="PORT", help="Vorgabe: 8760")
    dashboard.add_argument(
        "--browser", action="store_true", help="Browser automatisch öffnen"
    )
    dashboard.set_defaults(func=_cmd_dashboard)

    config_cmd = subparsers.add_parser("config", help="Konfiguration anzeigen oder anlegen")
    config_cmd.add_argument(
        "--anlegen",
        action="store_true",
        help="Vorlage der Konfigurationsdatei schreiben",
    )
    config_cmd.set_defaults(func=_cmd_config)

    return parser


def _write_env_template(path: Path) -> Path:
    """Vorlage für den API-Schlüssel anlegen (Rechte 0600, kein Schlüssel drin)."""
    path = Path(path).expanduser()
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# API-Schlüssel für die Cloud-Analyse (Phase 4).\n"
        "# Schlüssel gibt es unter https://platform.claude.com/\n"
        "# Diese Datei gehört NICHT ins Repository.\n"
        "ANTHROPIC_API_KEY=\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - unter Windows wirkungslos
        pass
    return path


def _open_database(config: Config) -> Database:
    """Datenbank öffnen und beim ersten Mal die Ausschluss-Vorlage übernehmen."""
    database = Database.from_config(config)
    database.connect()
    uebernommen = database.seed_exclusions(
        ExclusionList.load_template(config.exclusions_path)
    )
    if uebernommen:
        print(
            f"Ausschlussliste angelegt: {uebernommen} Muster aus der Vorlage übernommen.",
            file=sys.stderr,
        )
    return database


def _resolve_config(args: argparse.Namespace) -> Config:
    config = load_config(args.config)
    return config.with_overrides(
        database_path=args.db,
        interval_seconds=getattr(args, "intervall", None),
        idle_threshold_seconds=getattr(args, "idle_schwelle", None),
    )


def _parse_day(value: str | None) -> date | None:
    if value is None:
        return None
    return timeutil.parse_day(value)


def _plural(anzahl: int, einzahl: str, mehrzahl: str) -> str:
    """„1 Aufruf" statt „1 Aufrufe"."""
    return f"{anzahl} {einzahl if anzahl == 1 else mehrzahl}"


def _shorten(text: str | None, width: int) -> str:
    if not text:
        return "—"
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


# -- Befehle ----------------------------------------------------------------


def _cmd_track(args: argparse.Namespace, config: Config) -> int:
    stop_event = threading.Event()

    def handle_signal(_signum: int, _frame: object) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handle_signal)
        except (ValueError, OSError):  # pragma: no cover - z. B. in Threads
            pass

    with _open_database(config) as database:
        tracker = Tracker(
            database,
            config,
            on_event=(lambda message: print(f"  {message}")) if args.ausfuehrlich else None,
        )
        print(f"FokusRadar {__version__} — Erfassung läuft. Beenden mit Strg+C.")
        print(f"Datenbank: {config.database_path}")
        for label, state in tracker.backend_report():
            print(f"  {label:<18} {state}")
        if not tracker.window_backend.available():
            print(
                "\nHinweis: Ohne Fenster-Backend werden keine Fensterwechsel erfasst.\n"
                "Unter Windows läuft die Erfassung ohne Zusatzpakete; unter Linux wird\n"
                "eine X11-Sitzung mit xdotool oder xprop benötigt.",
                file=sys.stderr,
            )
        print()

        stats = tracker.run(stop_event=stop_event, duration_seconds=args.dauer)

    print(
        f"\nBeendet — Abfragen: {stats.ticks}, Fensternutzungen: {stats.window_events}, "
        f"Messpunkte: {stats.activity_samples}, Pausen: {stats.idle_periods}"
    )
    return 0


def _cmd_status(args: argparse.Namespace, config: Config) -> int:
    print(f"FokusRadar {__version__}")
    print(f"Konfiguration: {config.source or 'Vorgabewerte (keine Datei gefunden)'}")
    print(f"Datenbank:     {config.database_path}", end="")
    if config.database_path.exists():
        size_kb = f"{config.database_path.stat().st_size / 1024:,.0f}".replace(",", ".")
        zustand = "verschlüsselt" if crypto.is_encrypted(config.database_path) else "Klartext"
        print(f"  ({size_kb} KB, {zustand})")
    else:
        print("  (noch nicht angelegt)")

    print("\nErfassung:")
    print(f"  Intervall          {config.capture.interval_seconds:g} s")
    print(f"  Idle-Schwelle      {config.capture.idle_threshold_seconds:g} s")
    print(f"  Aktivitäts-Takt    {config.capture.activity_interval_seconds:g} s")
    print(
        f"  Fenstertitel       {'werden gespeichert' if config.capture.store_window_titles else 'werden nicht gespeichert'}"
    )
    print(f"  Smart Pause bei    {', '.join(config.capture.pause_processes) or '—'}")
    if config.screenshots.enabled:
        print(
            f"  Screenshots        alle {config.screenshots.interval_seconds:g} s"
            f", OCR {'an' if config.screenshots.ocr else 'aus'}"
            f", Bild {'wird gelöscht' if config.screenshots.delete_image else 'bleibt liegen'}"
        )
    else:
        print("  Screenshots        aus")

    with _open_database(config) as database:
        tracker = Tracker(database, config)
        print("\nBackends:")
        for label, state in tracker.backend_report():
            print(f"  {label:<18} {state}")

        print("\nDatenbestand:")
        for table, count in database.table_counts().items():
            print(f"  {table:<18} {count:>8} Zeilen")

        analyzer = CloudAnalyzer(config)
        grund = analyzer.unavailable_reason()
        print(
            "\nCloud-Analyse:     "
            + (f"bereit ({config.cloud.model})" if grund is None else f"aus — {grund}")
        )
        summe = database.api_cost_summary()
        if summe["aufrufe"]:
            print(
                f"  {summe['aufrufe']} Aufrufe, geschätzt "
                f"{format_usd(summe['kosten_usd'])} — Details: fokusradar kosten"
            )

        liste = database.exclusions()
        print(
            f"\nAusschlussliste: {_plural(len(liste), 'Muster', 'Muster')}"
            + (" — 'fokusradar ausschluss liste' zeigt sie" if len(liste) else "")
        )

        current = database.current_window_event()
        if current is not None:
            running = timeutil.to_local(current.started_at).strftime("%H:%M:%S")
            print(
                f"\nLaufende Sitzung: {current.process_name} "
                f"({_shorten(current.window_title, 50)}) seit {running}"
            )
        days = database.tracked_days()
        if days:
            print(
                f"\nTage mit Daten: {len(days)} "
                f"({days[-1].isoformat()} bis {days[0].isoformat()})"
            )
        else:
            print("\nNoch keine Daten erfasst — mit 'fokusradar track' starten.")
    return 0


def _cmd_log(args: argparse.Namespace, config: Config) -> int:
    day = _parse_day(args.tag)
    with _open_database(config) as database:
        events = database.window_events(day=day, limit=args.anzahl)
    if not events:
        print("Keine Fensternutzungen gefunden.")
        return 0

    print(f"{'Beginn':<20} {'Dauer':>9}  {'Programm':<24} Fenstertitel")
    print("-" * 100)
    for event in reversed(events):
        started = timeutil.to_local(event.started_at).strftime("%Y-%m-%d %H:%M:%S")
        if event.is_open:
            duration = "läuft"
        else:
            duration = timeutil.format_duration(event.duration_seconds or 0)
        print(
            f"{started:<20} {duration:>9}  {_shorten(event.process_name, 24):<24} "
            f"{_shorten(event.window_title, 44)}"
        )
    return 0


def _cmd_zeiten(args: argparse.Namespace, config: Config) -> int:
    day = _parse_day(args.tag) or timeutil.parse_day("heute")
    with _open_database(config) as database:
        totals = database.app_totals(day, limit=args.anzahl)
        all_totals = database.app_totals(day)
    if not totals:
        print(f"Für {day.isoformat()} liegen keine Daten vor.")
        return 0

    total_seconds = sum(item.seconds for item in all_totals)
    print(f"Zeit je Programm am {day.isoformat()}")
    print(f"Erfasste Zeit gesamt: {timeutil.format_duration(total_seconds)}\n")

    longest = max(totals[0].seconds, 1)
    for item in totals:
        share = item.seconds / total_seconds * 100 if total_seconds else 0.0
        bar = "█" * max(1, round(item.seconds / longest * 24)) if item.seconds else ""
        print(
            f"{_shorten(item.process_name, 24):<24} "
            f"{timeutil.format_duration(item.seconds):>9} "
            f"{share:5.1f}%  {bar}"
        )
    if len(all_totals) > len(totals):
        print(f"\n… und {len(all_totals) - len(totals)} weitere Programme.")
    return 0


def _cmd_aktivitaet(args: argparse.Namespace, config: Config) -> int:
    day = _parse_day(args.tag) or timeutil.parse_day("heute")
    with _open_database(config) as database:
        samples = database.activity_samples(day=day, limit=args.anzahl)
    if not samples:
        print(f"Für {day.isoformat()} liegen keine Messpunkte vor.")
        return 0

    print(f"{'Zeitpunkt':<20} {'ohne Eingabe':>13} {'Eingaben':>9}")
    print("-" * 44)
    for sample in reversed(samples):
        moment = timeutil.to_local(sample.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        idle = (
            timeutil.format_duration(sample.idle_seconds)
            if sample.idle_seconds is not None
            else "—"
        )
        events = (
            str(sample.input_events_count) if sample.input_events_count is not None else "—"
        )
        print(f"{moment:<20} {idle:>13} {events:>9}")
    return 0


def _cmd_auswerten(args: argparse.Namespace, config: Config) -> int:
    day = _parse_day(args.tag) or timeutil.parse_day("heute")
    categorizer = Categorizer.load(config.categories_path)

    with _open_database(config) as database:
        analysis = analyze_day(database, categorizer, day, config.analysis)
        if not args.nicht_speichern:
            store_analysis(database, analysis)

        _print_day_analysis(analysis, categorizer)

        if args.woche:
            print("\nLetzte sieben Tage")
            print(f"{'Tag':<12} {'Erfasst':>9} {'Fokus':>9} {'Ablenkung':>10} {'Wechsel/h':>10}")
            print("-" * 54)
            for tag in last_days(day, 7):
                trend = analyze_day(database, categorizer, tag, config.analysis)
                if not trend.has_data:
                    print(f"{tag.isoformat():<12} {'—':>9} {'—':>9} {'—':>10} {'—':>10}")
                    continue
                print(
                    f"{tag.isoformat():<12} "
                    f"{timeutil.format_duration(trend.total_seconds):>9} "
                    f"{timeutil.format_duration(trend.focus_seconds):>9} "
                    f"{trend.distraction_share * 100:9.0f}% "
                    f"{trend.switches_per_hour:10.0f}"
                )
    return 0


def _print_day_analysis(analysis, categorizer: Categorizer) -> None:
    """Tagesauswertung als Text ausgeben."""
    dauer = timeutil.format_duration
    print(f"Auswertung für {analysis.day.isoformat()}")
    if not analysis.has_data:
        print("Für diesen Tag liegen keine Daten vor.")
        return

    print(
        f"  Erfasste Zeit    {dauer(analysis.total_seconds)}\n"
        f"  Fokuszeit        {dauer(analysis.focus_seconds)} "
        f"({analysis.focus_share * 100:.0f} %)\n"
        f"  Ablenkung        {dauer(analysis.distraction_seconds)} "
        f"({analysis.distraction_share * 100:.0f} %)\n"
        f"  Fensterwechsel   {analysis.switches} "
        f"({analysis.switches_per_hour:.0f} pro Stunde)\n"
        f"  Längster Block   {dauer(analysis.longest_focus_seconds)}"
    )

    print("\nKategorien")
    for name, seconds in sorted(analysis.category_seconds.items(), key=lambda item: -item[1]):
        anteil = seconds / analysis.total_seconds * 100 if analysis.total_seconds else 0
        art = categorizer.kind_of(name)
        markierung = {"fokus": "+", "ablenkung": "−"}.get(art, " ")
        bar = "█" * max(1, round(anteil / 4)) if seconds else ""
        print(f"  {markierung} {_shorten(name, 22):<22} {dauer(seconds):>9} {anteil:5.1f}%  {bar}")

    if analysis.focus_sessions:
        print("\nFokus-Sessions")
        for session in analysis.focus_sessions:
            von = timeutil.to_local(session.start).strftime("%H:%M")
            bis = timeutil.to_local(session.end).strftime("%H:%M")
            unterbrechungen = (
                ", " + _plural(session.interruptions, "Unterbrechung", "Unterbrechungen")
                if session.interruptions
                else ""
            )
            print(
                f"  {von}–{bis}  {dauer(session.focus_seconds):>9}  "
                f"{session.main_process}{unterbrechungen}"
            )
    else:
        print("\nFokus-Sessions: kein Block über der Mindestdauer.")

    if analysis.top_distractions:
        print("\nTop-Ablenkungen")
        for app in analysis.top_distractions:
            print(
                f"  {_shorten(app.process_name, 22):<22} {dauer(app.seconds):>9} "
                f"({_plural(app.events, 'Aufruf', 'Aufrufe')})"
            )

    if analysis.suggestions:
        print("\nVorschläge")
        for text in analysis.suggestions:
            print(f"  • {text}")


def _cmd_kategorien(args: argparse.Namespace, config: Config) -> int:
    categorizer = Categorizer.load(config.categories_path)

    if args.test:
        kategorie = categorizer.categorize(args.test, args.titel)
        print(f"Prozess: {args.test}")
        print(f"Titel:   {args.titel or '—'}")
        print(f"→ Kategorie: {kategorie} (zählt als {categorizer.kind_of(kategorie)})")
        return 0

    quelle = categorizer.source or "eingebaute Regeln"
    print(f"Regeln aus: {quelle}")
    print(f"Standard-Kategorie: {categorizer.default}\n")
    for category in categorizer.categories:
        print(f"{category.name}  (zählt als {category.kind})")
        if category.process_patterns:
            print(f"  Prozesse: {', '.join(category.process_patterns)}")
        if category.title_patterns:
            print(f"  Titel:    {', '.join(category.title_patterns)}")
    if categorizer.source is None:
        print(
            "\nEigene Regeln anlegen mit 'fokusradar config --anlegen' "
            "(schreibt auch categories.yaml)."
        )
    return 0


def _cmd_ausschluss(args: argparse.Namespace, config: Config) -> int:
    aktion = getattr(args, "aktion", None) or "liste"

    with _open_database(config) as database:
        if aktion == "hinzufuegen":
            eintraege = [
                (muster, typ)
                for muster, typ in ((args.prozess, "process"), (args.titel, "title"))
                if muster
            ]
            if not eintraege:
                print(
                    "Bitte --prozess oder --titel angeben, z. B.\n"
                    '  fokusradar ausschluss hinzufuegen --prozess "keepass*.exe"',
                    file=sys.stderr,
                )
                return 2
            for muster, typ in eintraege:
                neu = database.add_exclusion(muster, typ)
                if neu is None:
                    print(f"Steht schon auf der Liste: {muster}")
                else:
                    print(f"Aufgenommen (#{neu}): {muster}")
            return 0

        if aktion == "entfernen":
            if database.remove_exclusion(args.id):
                print(f"Muster #{args.id} entfernt.")
                return 0
            print(f"Es gibt kein Muster #{args.id}.", file=sys.stderr)
            return 1

        if aktion == "pruefen":
            regel = database.exclusions().matching_rule(args.prozess, args.titel)
            print(f"Prozess: {args.prozess}")
            print(f"Titel:   {args.titel or '—'}")
            if regel is None:
                print("→ wird erfasst (kein Muster greift)")
            else:
                print(f"→ wird NICHT erfasst — {regel.label}-Muster {regel.pattern!r}")
            return 0

        liste = database.exclusions()
        if liste.is_empty:
            print("Die Ausschlussliste ist leer — es wird alles erfasst.")
            return 0
        print(f"{'Nr.':>4}  {'Typ':<8} Muster")
        print("-" * 48)
        for regel in liste:
            print(f"{regel.id:>4}  {regel.label:<8} {regel.pattern}")
        print(
            f"\n{_plural(len(liste), 'Muster', 'Muster')} — passende Fenster werden "
            "weder gespeichert noch aufgenommen."
        )
    return 0


def _cmd_screenshots(args: argparse.Namespace, config: Config) -> int:
    day = _parse_day(args.tag)
    with _open_database(config) as database:
        eintraege = database.screenshots(day=day, limit=args.anzahl)

    if not eintraege:
        print("Keine Aufnahmen gefunden.")
        if not config.screenshots.enabled:
            print("Screenshots sind abgeschaltet ([screenshots] aktiv = false).")
        return 0

    for eintrag in reversed(eintraege):
        zeitpunkt = timeutil.to_local(eintrag.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        text = eintrag.ocr_text or ""
        verbleib = (
            f"Bild: {eintrag.screenshot_path}"
            if eintrag.image_available
            else "Bild gelöscht"
        )
        woher = f"{_shorten(eintrag.source_label, 12):<12}"
        if eintrag.context:
            woher += f" {_shorten(eintrag.context, 22):<22}"
        print(f"{zeitpunkt}  {woher}  {len(text):>5} Zeichen  {verbleib}")
        if args.text and text:
            for zeile in text.splitlines():
                print(f"    {zeile}")
            print()
        elif text:
            print(f"    {_shorten(text.replace(chr(10), ' '), 96)}")
    return 0


def _cmd_verschluesseln(args: argparse.Namespace, config: Config) -> int:
    pfad = config.database_path
    if not pfad.is_file():
        print(f"Es gibt noch keine Datenbank unter {pfad}.", file=sys.stderr)
        print(
            "Für eine neue Datenbank genügt [speicher] verschluesselt = true "
            "in der Konfiguration.",
            file=sys.stderr,
        )
        return 1
    if not crypto.encryption_available():
        print(str(crypto.EncryptionUnavailable()), file=sys.stderr)
        return 3
    if crypto.is_encrypted(pfad):
        print(f"{pfad} ist bereits verschlüsselt.")
        return 0

    schluessel_datei = config.key_file
    print(f"Datenbank:      {pfad}")
    print(f"Schlüsseldatei: {schluessel_datei}")
    print(
        "\nDie Klartext-Fassung bleibt als Sicherung liegen. Ohne die "
        "Schlüsseldatei\nsind die Daten danach nicht mehr lesbar — es gibt keine "
        "Hintertür."
    )
    if not args.ja:
        antwort = input("\nFortfahren? [j/N] ").strip().lower()
        if antwort not in {"j", "ja", "y", "yes"}:
            print("Abgebrochen.")
            return 1

    schluessel = crypto.load_or_create_key(schluessel_datei)
    sicherung = crypto.encrypt_database(pfad, schluessel)
    print(f"\nFertig. Verschlüsselt: {pfad}")
    print(f"Klartext-Sicherung:    {sicherung}")
    print(
        "\nJetzt in der Konfiguration [speicher] verschluesselt = true setzen "
        "und die\nSicherung löschen, sobald alles läuft."
    )
    return 0


def _cmd_cloud(args: argparse.Namespace, config: Config) -> int:
    day = _parse_day(args.tag) or timeutil.parse_day("heute")
    categorizer = Categorizer.load(config.categories_path)
    analyzer = CloudAnalyzer(config)

    with _open_database(config) as database:
        if args.woche:
            tage = last_days(day, 7)
            analysen = [
                analyze_day(database, categorizer, tag, config.analysis) for tag in tage
            ]
            if not any(a.has_data for a in analysen):
                print("Für diese Woche liegen keine Daten vor.")
                return 0
            nutzlast = build_week_payload(analysen)
            art = "woche"
        else:
            analyse = analyze_day(database, categorizer, day, config.analysis)
            if not analyse.has_data:
                print(f"Für {day.isoformat()} liegen keine Daten vor.")
                return 0
            store_analysis(database, analyse)
            schnipsel = (
                collect_ocr_snippets(database, day) if config.cloud.send_ocr else None
            )
            nutzlast = build_day_payload(analyse, ocr_snippets=schnipsel)
            art = "taeglich"

        if args.zeigen:
            print("Das — und nur das — würde an die Claude-API gehen:\n")
            print(json.dumps(nutzlast, ensure_ascii=False, indent=2))
            print(f"\nModell: {config.cloud.model}")
            if not config.cloud.send_ocr:
                print("OCR-Text: wird nicht mitgesendet ([cloud] ocr_mitsenden = false)")
            print("Gesendet wurde nichts.")
            return 0

        grund = analyzer.unavailable_reason()
        if grund is not None:
            print(f"Cloud-Analyse nicht möglich — {grund}", file=sys.stderr)
            if not config.cloud.enabled:
                print(
                    "\nZum Einschalten in der Konfiguration [cloud] aktiv = true setzen.\n"
                    "Vorher lohnt ein Blick auf 'fokusradar cloud --zeigen': "
                    "das zeigt genau,\nwas das Gerät verlassen würde.",
                    file=sys.stderr,
                )
            return 3

        if not args.woche and not args.erneut and database.has_cloud_suggestions(day):
            print(
                f"Für {day.isoformat()} liegen schon Cloud-Vorschläge vor "
                "(mit --erneut trotzdem fragen)."
            )
            for vorschlag in database.suggestions(day=day):
                if vorschlag.source == "cloud":
                    print(f"  • {vorschlag.text}")
            return 0

        print(f"Frage {config.cloud.model} …")
        try:
            if args.woche:
                ergebnis = analyzer.analyze_week(analysen)
            else:
                ergebnis = analyzer.analyze_day(analyse, ocr_snippets=schnipsel)
        except CloudError as exc:
            print(str(exc), file=sys.stderr)
            return 3

        analyzer.store(database, day, ergebnis, kind=art)

    if ergebnis.refused:
        print(
            "Die Anfrage wurde abgelehnt (stop_reason: refusal). Es wurden keine "
            "Vorschläge erzeugt.",
            file=sys.stderr,
        )
        return 4

    if not ergebnis.suggestions:
        print("Die Antwort enthielt keine verwertbaren Vorschläge.", file=sys.stderr)
        return 4

    print(f"\nVorschläge ({ergebnis.model})")
    for text, kategorie in ergebnis.suggestions:
        print(f"  • [{kategorie}] {text}")
    print(
        f"\nVerbrauch: {ergebnis.input_tokens} Token hinein, "
        f"{ergebnis.output_tokens} hinaus — etwa {format_usd(ergebnis.cost_usd)}"
    )
    return 0


def _cmd_bild(args: argparse.Namespace, config: Config) -> int:
    """Bild-Analyse: ein einzelnes Bildschirmfoto ansehen lassen (Phase 6)."""
    aufnahme, frisch = _bild_waehlen(args, config)
    if aufnahme is None:
        return 1
    try:
        return _bild_analysieren(args, config, aufnahme, frisch)
    finally:
        # Eine Aufnahme, die dieser Aufruf selbst gemacht hat, gehört auch ihm:
        # sie verschwindet wieder, egal wie der Aufruf ausgeht. Alles andere —
        # eine mitgegebene Datei, eine Aufnahme der Erfassung — bleibt liegen.
        if frisch and not args.behalten and aufnahme.is_file():
            try:
                aufnahme.unlink()
                print(f"Aufnahme gelöscht: {aufnahme}")
            except OSError as exc:  # pragma: no cover - Datei ist schon weg o. Ä.
                print(f"Aufnahme ließ sich nicht löschen: {exc}", file=sys.stderr)


def _bild_analysieren(
    args: argparse.Namespace, config: Config, aufnahme: Path, frisch: bool
) -> int:
    try:
        info = vision.inspect_image(aufnahme)
    except vision.ImageError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Was gerade im Vordergrund ist, sagt nur über eine gerade gemachte Aufnahme
    # etwas aus. Bei einer älteren oder mitgegebenen Datei wäre es geraten.
    kontext = _bild_kontext() if frisch else None
    tarif = price_for(config.cloud.model)
    schaetzung = ""
    if tarif is not None:
        kosten = info.estimated_tokens / 1_000_000 * tarif.input_per_mtok
        schaetzung = f", geschätzt {format_usd(kosten)} für das Bild"

    print(f"Aufnahme:  {info.path}")
    print(f"Umfang:    {info.size_text}")
    print(f"Bild-Token: ~{info.estimated_tokens}{schaetzung}")
    print(f"Kontext:   {kontext or '—'}")
    print(f"Modell:    {config.cloud.model}")

    if args.zeigen:
        print("\nHinaus ginge das Bild oben — vollständig, so wie es ist — und:")
        print("\n  --- Auftrag an das Modell ---")
        for zeile in vision.VISION_SYSTEM_PROMPT.splitlines():
            print(f"  {zeile}")
        print("\n  --- Nachricht neben dem Bild ---")
        for zeile in vision.build_question(kontext).splitlines():
            print(f"  {zeile}")
        print("\nGesendet wurde nichts (--zeigen).")
        return 0

    if not config.cloud.enabled:
        print(
            "\nDie Cloud-Analyse ist abgeschaltet ([cloud] aktiv = false).",
            file=sys.stderr,
        )
        return 3
    if not config.cloud.send_images:
        print(
            "\nDas Senden von Bildern ist abgeschaltet.\n"
            "Ein Bild zeigt alles, was in dem Moment am Bildschirm stand. Wenn du "
            "das willst,\nsetze in der Konfiguration [cloud] bilder_senden = true.",
            file=sys.stderr,
        )
        return 3

    analyzer = CloudAnalyzer(config)
    print("\nFrage die Bild-Analyse …")
    try:
        ergebnis = analyzer.analyze_image(info.path, context=kontext)
    except CloudError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    heute = timeutil.parse_day("heute")
    with _open_database(config) as database:
        database.record_api_usage(
            timeutil.now_utc(),
            day=heute,
            kind="bild",
            model=ergebnis.model,
            input_tokens=ergebnis.input_tokens,
            output_tokens=ergebnis.output_tokens,
            cache_read_tokens=ergebnis.cache_read_tokens,
            cache_write_tokens=ergebnis.cache_write_tokens,
            cost_usd=ergebnis.cost_usd,
        )
        if ergebnis.suggestions:
            for text, kategorie in ergebnis.suggestions:
                database.add_suggestion(heute, "cloud", text, f"bild/{kategorie}")

    if ergebnis.refused:
        print("\nDas Modell hat die Antwort abgelehnt.")
        return 0
    if not ergebnis.suggestions:
        print("\nKeine Vorschläge — auf dem Bild ist nichts aufgefallen.")
    else:
        print(f"\nVorschläge ({len(ergebnis.suggestions)}):")
        for text, kategorie in ergebnis.suggestions:
            print(f"  • [{kategorie}] {text}")
    print(
        f"\nVerbrauch: {ergebnis.input_tokens} hinein, {ergebnis.output_tokens} hinaus"
        f" — {format_usd(ergebnis.cost_usd)} (geschätzt)"
    )
    return 0


def _bild_waehlen(
    args: argparse.Namespace, config: Config
) -> tuple[Path | None, bool]:
    """Aufnahme bestimmen: angegeben, frisch aufgenommen oder die neueste.

    Rückgabe: (Pfad, frisch aufgenommen). ``None`` heißt: es gibt keine.
    """
    if args.datei is not None:
        return Path(args.datei).expanduser(), False

    if args.neu:
        return _bild_aufnehmen(config), True

    with _open_database(config) as database:
        eintraege = database.screenshots(limit=25)
    for eintrag in eintraege:
        if eintrag.image_available and Path(eintrag.screenshot_path).is_file():
            return Path(eintrag.screenshot_path), False

    print(
        "Keine Aufnahme vorhanden, deren Bild noch da ist.\n"
        "FokusRadar löscht Bilder nach der Texterkennung ([screenshots] "
        "bild_loeschen = true).\n"
        "Jetzt eine machen:      fokusradar bild --neu\n"
        "Oder eine mitgeben:     fokusradar bild --datei PFAD",
        file=sys.stderr,
    )
    return None, False


def _bild_aufnehmen(config: Config) -> Path | None:
    """Jetzt eine Aufnahme machen — aber nicht von einem gesperrten Fenster."""
    fenster = create_window_backend()
    info = fenster.snapshot() if fenster.available() else None
    if info is not None:
        with _open_database(config) as database:
            liste = ExclusionList(list(database.exclusions()))
        regel = liste.matching_rule(info.process_name, info.window_title)
        if regel is not None:
            print(
                f"Nicht aufgenommen: {info.process_name} steht auf der "
                f"Ausschlussliste ({regel.label}-Muster {regel.pattern!r}).",
                file=sys.stderr,
            )
            return None
        if info.process_name.casefold() in {
            name.casefold() for name in config.capture.pause_processes
        }:
            print(
                f"Nicht aufgenommen: {info.process_name} löst die Smart Pause aus.",
                file=sys.stderr,
            )
            return None

    backend = create_screenshot_backend(True)
    if not backend.available():
        print(
            "Aufnahme nicht möglich — "
            f"{backend.unavailable_reason() or 'kein Backend verfügbar'}",
            file=sys.stderr,
        )
        return None
    ziel = config.screenshot_dir / screenshot_filename(timeutil.now_utc())
    bild = backend.capture(ziel)
    if bild is None:
        print(
            "Keine Aufnahme möglich — "
            f"{backend.unavailable_reason() or 'unbekannter Grund'}",
            file=sys.stderr,
        )
        return None
    return bild


def _bild_kontext() -> str | None:
    """Ein Satz zum aktiven Fenster — Prozessname, nie der Fenstertitel.

    Der Fenstertitel bliebe hier bewusst draußen: er steht ohnehin im Bild,
    aber er würde die Zusage brechen, dass nur Programmnamen mitgehen.
    """
    fenster = create_window_backend()
    if not fenster.available():
        return None
    info = fenster.snapshot()
    if info is None:
        return None
    return f"Im Vordergrund war {info.process_name}."


def _cmd_kosten(args: argparse.Namespace, config: Config) -> int:
    with _open_database(config) as database:
        summe = database.api_cost_summary()
        eintraege = database.api_usage(limit=args.anzahl)

    if not eintraege:
        print("Es gab noch keine Cloud-Analyse.")
        print(f"Cloud-Analyse: {'an' if config.cloud.enabled else 'aus'}")
        return 0

    print(f"Aufrufe gesamt:  {summe['aufrufe']}")
    print(f"Token hinein:    {summe['input_tokens']:,}".replace(",", "."))
    print(f"Token hinaus:    {summe['output_tokens']:,}".replace(",", "."))
    print(f"Kosten (geschätzt): {format_usd(summe['kosten_usd'])}")
    if summe["von"] and summe["bis"]:
        tage = (summe["bis"] - summe["von"]).days + 1
        if tage > 1:
            schnitt = summe["kosten_usd"] / tage * 30
            print(
                f"Zeitraum:        {summe['von'].isoformat()} bis "
                f"{summe['bis'].isoformat()} ({tage} Tage)"
            )
            print(f"Hochgerechnet:   {format_usd(schnitt)} pro Monat")

    print(f"\n{'Zeitpunkt':<20} {'Art':<10} {'Modell':<18} {'Token':>13} {'Kosten':>9}")
    print("-" * 74)
    for eintrag in reversed(eintraege):
        zeitpunkt = timeutil.to_local(eintrag.timestamp).strftime("%Y-%m-%d %H:%M")
        token = f"{eintrag.input_tokens}/{eintrag.output_tokens}"
        print(
            f"{zeitpunkt:<20} {eintrag.kind:<10} {_shorten(eintrag.model, 18):<18} "
            f"{token:>13} {format_usd(eintrag.cost_usd):>9}"
        )

    tarif = price_for(config.cloud.model)
    if tarif is not None:
        hinweis = f" — {tarif.note}" if tarif.note else ""
        print(
            f"\nPreise für {config.cloud.model}: {tarif.input_per_mtok:g} $ / "
            f"{tarif.output_per_mtok:g} $ je Mio. Token "
            f"(Stand {PRICE_DATE.strftime('%d.%m.%Y')}){hinweis}"
        )
    print("Geschätzte Werte — maßgeblich ist die Abrechnung von Anthropic.")
    return 0


def _cmd_android(args: argparse.Namespace, config: Config) -> int:
    if args.token_neu:
        neu = android_sync.generate_token()
        ziel = config.source or default_config_path()
        try:
            geschrieben = _token_schreiben(ziel, neu)
        except FileNotFoundError:
            print(
                f"Es gibt noch keine Konfigurationsdatei ({ziel}).\n"
                "Erst anlegen mit: fokusradar config --anlegen",
                file=sys.stderr,
            )
            return 2
        print(f"Neues Token: {neu}")
        print(f"Eingetragen in: {geschrieben}")
        if not config.android.enabled:
            print(
                "Der Sync ist noch abgeschaltet — in der Konfiguration "
                "[android] aktiv = true setzen."
            )
        print("Dasselbe Token in der App auf dem Handy hinterlegen.")
        return 0

    tag = timeutil.parse_day(args.tag)
    with _open_database(config) as database:
        geraete = database.android_devices()
        eintraege = database.android_usage(day=tag)
        gesamt = database.android_day_seconds(tag)

    print(f"Sync:     {'an' if config.android.enabled else 'aus ([android] aktiv = false)'}")
    if config.android.token:
        sichtbar = (
            config.android.token
            if args.token_zeigen
            else "gesetzt (" + "•" * 8 + config.android.token[-4:] + ")"
        )
    else:
        sichtbar = "nicht gesetzt — erzeugen mit: fokusradar android --token-neu"
    print(f"Token:    {sichtbar}")
    print(f"Endpunkt: {_sync_adresse(config)}")
    print(
        "Damit das Handy den Rechner erreicht, muss das Dashboard im Heimnetz "
        "lauschen:\n    fokusradar dashboard --host 0.0.0.0"
    )

    print("\nGeräte:")
    if not geraete:
        print("  noch keins — die App auf dem Handy hat bisher nichts geschickt.")
    for name, synced_at, letzter_tag in geraete:
        zeitpunkt = timeutil.to_local(synced_at).strftime("%d.%m.%Y %H:%M")
        print(f"  {name:<20} letzter Sync {zeitpunkt}   Daten bis {letzter_tag.isoformat()}")

    print(f"\nHandy-Nutzung am {tag.isoformat()}: {timeutil.format_duration(gesamt)}")
    if not eintraege:
        print("  keine Daten für diesen Tag.")
        return 0
    for eintrag in eintraege[:15]:
        name = eintrag.app_label or eintrag.package_name
        print(
            f"  {_shorten(name, 24):<24} {_shorten(eintrag.category or '-', 14):<14} "
            f"{timeutil.format_duration(eintrag.seconds):>10}   {eintrag.opens} Aufrufe"
        )
    if len(eintraege) > 15:
        print(f"  … und {len(eintraege) - 15} weitere Apps")
    return 0


def _sync_adresse(config: Config) -> str:
    """Adresse des Sync-Endpunkts, möglichst mit der Adresse im Heimnetz."""
    host = config.dashboard.host
    if host in {"127.0.0.1", "0.0.0.0", "localhost", "::"}:
        host = _lokale_adresse() or host
    return f"http://{host}:{config.dashboard.port}/api/android/nutzung"


def _lokale_adresse() -> str | None:
    """Eigene Adresse im Heimnetz ermitteln (ohne Paket zu verschicken)."""
    import socket

    versuch = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Verbinden ohne Datenverkehr: das Betriebssystem wählt dabei die
        # Netzwerkkarte aus, über die es hinausginge.
        versuch.connect(("10.255.255.255", 1))
        return str(versuch.getsockname()[0])
    except OSError:  # pragma: no cover - hängt am Netzwerk
        return None
    finally:
        versuch.close()


def _token_schreiben(path: Path, token: str) -> Path:
    """Token in den Abschnitt ``[android]`` der Konfigurationsdatei eintragen."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(path)
    zeilen = path.read_text(encoding="utf-8").splitlines()

    im_abschnitt = False
    gesetzt = False
    kopfzeile: int | None = None
    ergebnis: list[str] = []
    for zeile in zeilen:
        gestutzt = zeile.strip()
        if gestutzt.startswith("[") and gestutzt.endswith("]"):
            im_abschnitt = gestutzt == "[android]"
            if im_abschnitt:
                kopfzeile = len(ergebnis)
        elif im_abschnitt and not gesetzt and gestutzt.startswith("token"):
            zeile = f'token = "{token}"'
            gesetzt = True
        ergebnis.append(zeile)

    if not gesetzt and kopfzeile is not None:
        # Abschnitt da, aber ohne token-Zeile — direkt hinter die Überschrift.
        ergebnis.insert(kopfzeile + 1, f'token = "{token}"')
    elif not gesetzt:
        ergebnis += ["", "[android]", "aktiv = false", f'token = "{token}"']
    path.write_text("\n".join(ergebnis) + "\n", encoding="utf-8")
    # In der Datei steht jetzt ein Geheimnis — wie beim API-Schlüssel und beim
    # Datenbank-Schlüssel gehört sie damit nur noch dem eigenen Benutzer.
    try:  # unter Windows wirkungslos, dort schützt die Benutzer-ACL
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover - z. B. exotische Dateisysteme
        pass
    return path


def _cmd_dashboard(args: argparse.Namespace, config: Config) -> int:
    try:
        run_dashboard(
            config, host=args.host, port=args.port, open_browser=args.browser
        )
    except DashboardUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 3
    return 0


def _cmd_config(args: argparse.Namespace, config: Config) -> int:
    if args.anlegen:
        try:
            written = write_default_config(args.config)
        except FileExistsError as exc:
            print(f"Es gibt bereits eine Konfiguration: {exc}", file=sys.stderr)
            return 1
        print(f"Konfigurationsvorlage angelegt: {written}")
        for pfad, schreiber, name in (
            (written.parent / "categories.yaml", write_default_categories, "Kategorien"),
            (written.parent / "exclusions.yaml", write_default_exclusions, "Ausschluss"),
            (written.parent / ".env", _write_env_template, "API-Schlüssel"),
        ):
            try:
                schreiber(pfad)
                print(f"{name + ':':<14} angelegt          {pfad}")
            except FileExistsError:
                print(f"{name + ':':<14} bleibt unverändert {pfad}")
        return 0

    print(f"Quelle:            {config.source or 'Vorgabewerte (keine Datei gefunden)'}")
    print(f"Datenbank:         {config.database_path}")
    ausschluss = config.exclusions_path
    print(
        f"Ausschluss-Vorlage {ausschluss}"
        + ("" if ausschluss.is_file() else "  (nicht vorhanden → eingebaute Vorlage)")
    )
    regeln = config.categories_path
    print(f"Regeldatei         {regeln}{'' if regeln.is_file() else '  (nicht vorhanden → eingebaute Regeln)'}")
    print(f"Intervall          {config.capture.interval_seconds:g} s")
    print(f"Idle-Schwelle      {config.capture.idle_threshold_seconds:g} s")
    print(f"Aktivitäts-Takt    {config.capture.activity_interval_seconds:g} s")
    print(f"Eingaben zählen    {config.capture.count_input_events}")
    print(f"Fenstertitel       {config.capture.store_window_titles}")
    print(f"Fokus ab           {config.analysis.focus_minimum_seconds:g} s")
    print(f"Toleranz           {config.analysis.interruption_tolerance_seconds:g} s")
    print(f"Screenshots        {'an' if config.screenshots.enabled else 'aus'}")
    print(f"Verschlüsselung    {'an' if config.storage.encrypted else 'aus'}")
    print(f"Cloud-Analyse      {'an' if config.cloud.enabled else 'aus'}")
    if config.cloud.enabled:
        print(f"  Modell           {config.cloud.model} (Aufwand {config.cloud.effort})")
        print(f"  Täglich ab       {config.cloud.daily_after or '—'}")
        print(f"  Wochenrückblick  {config.cloud.weekly_on or '—'}")
        print(f"  OCR mitsenden    {config.cloud.send_ocr}")
        print(f"  Bilder senden    {config.cloud.send_images}")
    print(f"API-Schlüssel      {config.env_path}")
    handy = "an" if config.android.enabled else "aus"
    if config.android.enabled and not config.android.token:
        handy = "an, aber ohne Token (fokusradar android --token-neu)"
    print(f"Handy-Sync         {handy}")
    print(f"Dashboard          http://{config.dashboard.host}:{config.dashboard.port}/")
    if config.source is None:
        print("\nMit 'fokusradar config --anlegen' eine Konfigurationsdatei erzeugen.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        config = _resolve_config(args)
    except ConfigError as exc:
        print(f"Fehler in der Konfiguration: {exc}", file=sys.stderr)
        return 2
    try:
        return int(args.func(args, config))
    except CategoryError as exc:
        print(f"Fehler in den Regeln: {exc}", file=sys.stderr)
        return 2
    except ExclusionError as exc:
        print(f"Fehler in der Ausschlussliste: {exc}", file=sys.stderr)
        return 2
    except (DatabaseLocked, crypto.EncryptionUnavailable) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover - nur im Dauerbetrieb
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
