"""Lokale Auswertung eines Tages: Fokus, Ablenkung, Zusammenfassung.

Alles hier läuft ohne Netzwerk. Die Cloud-Analyse aus Phase 4 bekommt später
genau das Ergebnis dieser Auswertung als Eingabe — nie die Rohdaten.

Begriffe:

* **Fokus-Session** — ein zusammenhängender Block in Kategorien, die als
  ``fokus`` zählen. Kurze Abstecher (Vorgabe: bis 60 Sekunden, inklusive
  Pausen) unterbrechen den Block nicht, ihre Zeit zählt aber auch nicht als
  Fokuszeit. Erst ab einer Mindestdauer (Vorgabe: 10 Minuten) gilt ein Block
  als Fokus-Session.
* **Wechsel** — jede erfasste Fensternutzung ist ein Wechsel; die Rate pro
  Stunde ist das Maß für Zerfaserung.
* **Ablenkung** — Zeit in Kategorien, die als ``ablenkung`` zählen.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from fokusradar import timeutil
from fokusradar.config import AnalysisConfig
from fokusradar.processing.categories import Categorizer

if TYPE_CHECKING:  # nur für die Typannotationen — sonst gäbe es einen Importzirkel
    from fokusradar.storage.db import Database, WindowEvent

TOP_LIST_LENGTH = 5


@dataclass(frozen=True)
class FocusSession:
    """Ein zusammenhängender Block konzentrierter Arbeit."""

    start: datetime
    end: datetime
    focus_seconds: int
    interruptions: int
    main_process: str

    @property
    def span_seconds(self) -> int:
        return int(round((self.end - self.start).total_seconds()))


@dataclass(frozen=True)
class AppUsage:
    """Nutzung eines Programms an einem Tag."""

    process_name: str
    category: str
    seconds: int
    events: int

    @property
    def average_seconds(self) -> float:
        return self.seconds / self.events if self.events else 0.0


@dataclass
class DayAnalysis:
    """Ergebnis der Tagesauswertung."""

    day: date
    total_seconds: int = 0
    focus_seconds: int = 0
    distraction_seconds: int = 0
    switches: int = 0
    category_seconds: dict[str, int] = field(default_factory=dict)
    apps: list[AppUsage] = field(default_factory=list)
    focus_sessions: list[FocusSession] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    first_event: datetime | None = None
    last_event: datetime | None = None
    #: Namen der Kategorien, die als Ablenkung zählen (aus den Regeln).
    distraction_categories: set[str] = field(default_factory=set, repr=False)

    # -- abgeleitete Werte --------------------------------------------------

    @property
    def has_data(self) -> bool:
        return self.total_seconds > 0

    @property
    def active_minutes(self) -> int:
        return int(round(self.total_seconds / 60))

    @property
    def focus_share(self) -> float:
        return self.focus_seconds / self.total_seconds if self.total_seconds else 0.0

    @property
    def distraction_share(self) -> float:
        return self.distraction_seconds / self.total_seconds if self.total_seconds else 0.0

    @property
    def switches_per_hour(self) -> float:
        if not self.total_seconds:
            return 0.0
        return self.switches / (self.total_seconds / 3600)

    @property
    def longest_focus_seconds(self) -> int:
        return max((s.focus_seconds for s in self.focus_sessions), default=0)

    @property
    def top_apps(self) -> list[AppUsage]:
        return self.apps[:TOP_LIST_LENGTH]

    @property
    def top_distractions(self) -> list[AppUsage]:
        return [app for app in self.apps if app.category in self.distraction_categories][
            :TOP_LIST_LENGTH
        ]

    def top_distractions_json(self) -> list[dict[str, object]]:
        """Form, in der die Top-Ablenkungen in ``daily_summaries`` landen."""
        return [
            {"prozess": app.process_name, "kategorie": app.category, "sekunden": app.seconds}
            for app in self.top_distractions
        ]


def analyze_day(
    database: "Database",
    categorizer: Categorizer,
    day: date,
    config: AnalysisConfig | None = None,
    *,
    recategorize: bool = True,
) -> DayAnalysis:
    """Einen lokalen Kalendertag auswerten.

    Die Kategorien werden dabei standardmäßig neu bestimmt und gespeichert —
    so wirken Änderungen an ``categories.yaml`` rückwirkend.
    """
    settings = config or AnalysisConfig()
    events = database.window_events(day=day, ascending=True)
    if recategorize:
        assignments = [
            (event.id, categorizer.categorize(event.process_name, event.window_title))
            for event in events
        ]
        database.set_categories(assignments)
        events = [
            _with_category(event, category) for event, category in zip(events, assignments)
        ]

    analysis = DayAnalysis(
        day=day,
        distraction_categories={
            category.name for category in categorizer.categories if category.is_distraction
        },
    )

    per_app: dict[tuple[str, str], list[int]] = {}
    for event in events:
        seconds = event.effective_seconds
        category = event.category or categorizer.default
        analysis.total_seconds += seconds
        analysis.switches += 1
        analysis.category_seconds[category] = (
            analysis.category_seconds.get(category, 0) + seconds
        )
        if categorizer.is_focus(category):
            analysis.focus_seconds += seconds
        elif categorizer.is_distraction(category):
            analysis.distraction_seconds += seconds

        key = (event.process_name, category)
        bucket = per_app.setdefault(key, [0, 0])
        bucket[0] += seconds
        bucket[1] += 1

    if events:
        analysis.first_event = events[0].started_at
        analysis.last_event = max(
            (event.ended_at or event.started_at for event in events), default=None
        )

    analysis.apps = sorted(
        (
            AppUsage(process_name=name, category=category, seconds=values[0], events=values[1])
            for (name, category), values in per_app.items()
        ),
        key=lambda app: (-app.seconds, app.process_name),
    )
    analysis.focus_sessions = find_focus_sessions(events, categorizer, settings)
    analysis.suggestions = build_local_suggestions(analysis, settings)
    return analysis


def find_focus_sessions(
    events: list["WindowEvent"], categorizer: Categorizer, config: AnalysisConfig
) -> list[FocusSession]:
    """Zusammenhängende Fokus-Blöcke aus den Fensternutzungen ableiten."""
    tolerance = timedelta(seconds=config.interruption_tolerance_seconds)
    sessions: list[FocusSession] = []

    start: datetime | None = None
    end: datetime | None = None
    focus_seconds = 0
    interruptions = 0
    processes: dict[str, int] = {}

    def flush() -> None:
        nonlocal start, end, focus_seconds, interruptions, processes
        if start is not None and end is not None and focus_seconds >= config.focus_minimum_seconds:
            main = max(processes.items(), key=lambda item: item[1])[0] if processes else "—"
            sessions.append(
                FocusSession(
                    start=start,
                    end=end,
                    focus_seconds=focus_seconds,
                    interruptions=interruptions,
                    main_process=main,
                )
            )
        start = end = None
        focus_seconds = 0
        interruptions = 0
        processes = {}

    for event in events:
        seconds = event.effective_seconds
        event_end = event.ended_at or (event.started_at + timedelta(seconds=seconds))
        if not categorizer.is_focus(event.category):
            continue  # unterbricht erst, wenn die Lücke zu groß wird (Prüfung unten)

        if start is not None and end is not None and event.started_at - end <= tolerance:
            if event.started_at > end:
                interruptions += 1
        else:
            flush()
            start = event.started_at

        end = event_end
        focus_seconds += seconds
        processes[event.process_name] = processes.get(event.process_name, 0) + seconds

    flush()
    return sessions


def build_local_suggestions(analysis: DayAnalysis, config: AnalysisConfig) -> list[str]:
    """Regelbasierte Vorschläge aus den Kennzahlen ableiten.

    Bewusst wenige und konkrete Hinweise: höchstens drei, nach Dringlichkeit
    sortiert. Die ausführlicheren Vorschläge kommen ab Phase 4 aus der
    Claude-API — diese hier funktionieren ohne Netzwerk.
    """
    if not analysis.has_data or analysis.total_seconds < 15 * 60:
        return []

    kandidaten: list[tuple[int, str]] = []
    dauer = timeutil.format_duration

    if analysis.switches_per_hour >= config.switch_rate_threshold:
        kandidaten.append(
            (
                10,
                f"{analysis.switches_per_hour:.0f} Fensterwechsel pro Stunde — das ist viel. "
                f"Nimm dir für die nächste Aufgabe einen festen Block von 25 Minuten vor "
                f"und lege alles andere solange beiseite.",
            )
        )

    if analysis.distraction_share >= config.distraction_share_threshold:
        top = analysis.top_distractions
        detail = (
            f" Größter Posten: {top[0].process_name} ({dauer(top[0].seconds)})." if top else ""
        )
        kandidaten.append(
            (
                9,
                f"{analysis.distraction_share * 100:.0f} % der erfassten Zeit "
                f"({dauer(analysis.distraction_seconds)}) gingen an Ablenkungen.{detail} "
                f"Ein fester Zeitpunkt dafür — statt zwischendurch — spart den Wiedereinstieg.",
            )
        )

    if analysis.total_seconds >= 2 * 3600 and analysis.longest_focus_seconds < 25 * 60:
        laengster = (
            dauer(analysis.longest_focus_seconds)
            if analysis.longest_focus_seconds
            else "gar keiner"
        )
        kandidaten.append(
            (
                8,
                f"Kein längerer Block am Stück: der beste war {laengster}. "
                f"Benachrichtigungen für zwei Stunden stummschalten bringt hier am meisten.",
            )
        )

    zappel = [
        app
        for app in analysis.apps
        if app.events >= config.short_visit_count and app.average_seconds <= config.short_visit_seconds
    ]
    if zappel:
        app = max(zappel, key=lambda item: item.events)
        kandidaten.append(
            (
                7,
                f"{app.process_name} wurde {app.events}-mal geöffnet, im Schnitt nur "
                f"{app.average_seconds:.0f} Sekunden. Zweimal am Tag gesammelt durchgehen "
                f"kostet weniger als {app.events} Unterbrechungen.",
            )
        )

    if not kandidaten and analysis.focus_share >= 0.5 and analysis.longest_focus_seconds >= 45 * 60:
        kandidaten.append(
            (
                1,
                f"Guter Tag: {analysis.focus_share * 100:.0f} % Fokuszeit, längster Block "
                f"{dauer(analysis.longest_focus_seconds)}. So beibehalten.",
            )
        )

    kandidaten.sort(key=lambda item: -item[0])
    return [text for _priority, text in kandidaten[:3]]


def store_analysis(database: "Database", analysis: DayAnalysis) -> None:
    """Zusammenfassung und lokale Vorschläge in der Datenbank ablegen."""
    database.save_daily_summary(
        analysis.day,
        total_active_minutes=analysis.active_minutes,
        category_breakdown=dict(
            sorted(analysis.category_seconds.items(), key=lambda item: -item[1])
        ),
        top_distractions=analysis.top_distractions_json(),
    )
    database.replace_suggestions(
        analysis.day, "local", [(text, "lokal") for text in analysis.suggestions]
    )


def analyze_days(
    database: "Database",
    categorizer: Categorizer,
    days: list[date],
    config: AnalysisConfig | None = None,
    *,
    recategorize: bool = False,
) -> list[DayAnalysis]:
    """Mehrere Tage auswerten (für Wochentrend und Dashboard)."""
    return [
        analyze_day(database, categorizer, day, config, recategorize=recategorize)
        for day in days
    ]


def last_days(end: date, count: int) -> list[date]:
    """Liste der letzten ``count`` Tage bis einschließlich ``end``."""
    return [end - timedelta(days=offset) for offset in range(count - 1, -1, -1)]


def _with_category(event: "WindowEvent", assignment: tuple[int, str]) -> "WindowEvent":
    """Kopie der Fensternutzung mit gesetzter Kategorie."""
    return replace(event, category=assignment[1])
