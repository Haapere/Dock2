"""Kommandozeile von FokusRadar.

    fokusradar track      # Erfassung starten (läuft im Vordergrund)
    fokusradar status     # Backends, Datenbank, laufende Sitzung
    fokusradar log        # Rohdaten: letzte Fensterwechsel
    fokusradar zeiten     # Zeit je Programm an einem Tag
    fokusradar aktivitaet # Messpunkte des Aktivitätslevels
    fokusradar config     # Konfiguration anzeigen oder anlegen
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from datetime import date
from pathlib import Path

from fokusradar import __version__, timeutil
from fokusradar.agent import Tracker
from fokusradar.config import Config, ConfigError, load_config, write_default_config
from fokusradar.storage.db import Database


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

    config_cmd = subparsers.add_parser("config", help="Konfiguration anzeigen oder anlegen")
    config_cmd.add_argument(
        "--anlegen",
        action="store_true",
        help="Vorlage der Konfigurationsdatei schreiben",
    )
    config_cmd.set_defaults(func=_cmd_config)

    return parser


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

    with Database(config.database_path) as database:
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
        size_kb = config.database_path.stat().st_size / 1024
        print(f"  ({size_kb:,.0f} KB)".replace(",", "."))
    else:
        print("  (noch nicht angelegt)")

    print("\nErfassung:")
    print(f"  Intervall          {config.capture.interval_seconds:g} s")
    print(f"  Idle-Schwelle      {config.capture.idle_threshold_seconds:g} s")
    print(f"  Aktivitäts-Takt    {config.capture.activity_interval_seconds:g} s")
    print(
        f"  Fenstertitel       {'werden gespeichert' if config.capture.store_window_titles else 'werden nicht gespeichert'}"
    )

    with Database(config.database_path) as database:
        tracker = Tracker(database, config)
        print("\nBackends:")
        for label, state in tracker.backend_report():
            print(f"  {label:<18} {state}")

        print("\nDatenbestand:")
        for table, count in database.table_counts().items():
            print(f"  {table:<18} {count:>8} Zeilen")

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
    with Database(config.database_path) as database:
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
    with Database(config.database_path) as database:
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
    with Database(config.database_path) as database:
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


def _cmd_config(args: argparse.Namespace, config: Config) -> int:
    if args.anlegen:
        try:
            written = write_default_config(args.config)
        except FileExistsError as exc:
            print(f"Es gibt bereits eine Konfiguration: {exc}", file=sys.stderr)
            return 1
        print(f"Konfigurationsvorlage angelegt: {written}")
        return 0

    print(f"Quelle:            {config.source or 'Vorgabewerte (keine Datei gefunden)'}")
    print(f"Datenbank:         {config.database_path}")
    print(f"Intervall          {config.capture.interval_seconds:g} s")
    print(f"Idle-Schwelle      {config.capture.idle_threshold_seconds:g} s")
    print(f"Aktivitäts-Takt    {config.capture.activity_interval_seconds:g} s")
    print(f"Eingaben zählen    {config.capture.count_input_events}")
    print(f"Fenstertitel       {config.capture.store_window_titles}")
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
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover - nur im Dauerbetrieb
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
