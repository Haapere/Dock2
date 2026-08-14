"""Was an die Claude-API geht — und was nicht.

Diese Datei ist die Datenschutz-Grenze des Projekts: alles, was FokusRadar
jemals an einen Server schickt, wird **hier** zusammengestellt. Wer wissen
will, was das Gerät verlässt, muss nur ``build_day_payload`` lesen — oder
``fokusradar cloud --zeigen`` aufrufen, das genau diese Struktur ausgibt,
ohne sie zu senden.

Es gehen ausschließlich verdichtete Zahlen und Prozessnamen hinaus:

* Kennzahlen des Tages (Sekunden je Kategorie, Fokus, Ablenkung, Wechsel)
* Fokus-Sessions als Uhrzeit und Dauer
* die wichtigsten Programme mit Prozessnamen
* auf ausdrücklichen Wunsch (``ocr_mitsenden = true``) Textschnipsel aus der
  lokalen Texterkennung

**Nie** gehen hinaus: Fenstertitel, Screenshots, die Datenbank, Rohdaten
einzelner Fensterwechsel.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fokusradar import timeutil
from fokusradar.processing.analysis import DayAnalysis

MAX_APPS = 8
MAX_SESSIONS = 8
MAX_OCR_SNIPPETS = 5
MAX_OCR_LENGTH = 400

SYSTEM_PROMPT = """\
Du bist ein pragmatischer Produktivitäts-Coach. Du bekommst die verdichtete \
Bildschirm-Statistik eines Arbeitstages — keine Inhalte, nur Zahlen und \
Programmnamen.

Gib 2-3 konkrete, umsetzbare Vorschläge zu diesen zwei Fragen:
1. Wie könnte die Person fokussierter arbeiten?
2. Wo verliert sie Zeit durch ineffiziente Bedienung einzelner Programme?

Regeln:
- Kurz und konkret, keine Allgemeinplätze und keine Motivationssprüche.
- Beziehe dich auf die tatsächlichen Zahlen und Programme aus den Daten.
- Wo es passt, nenne einen konkreten Kniff (Tastenkürzel, Einstellung, \
Arbeitsweise) statt nur "mach weniger davon".
- Keine Diagnosen, keine Bewertung der Person.
- Wenn die Datenlage für eine Aussage zu dünn ist, sag das statt zu raten.
- Antworte auf Deutsch und duze die Person.\
"""

WEEK_SYSTEM_PROMPT = """\
Du bist ein pragmatischer Produktivitäts-Coach. Du bekommst die verdichteten \
Kennzahlen einer Arbeitswoche — keine Inhalte, nur Zahlen und Programmnamen.

Schreibe einen kurzen Wochenrückblick:
1. Was fällt über die Woche hinweg auf? Nenne ein Muster, keine Tagesliste.
2. Zwei bis drei konkrete Vorschläge für die kommende Woche.

Regeln:
- Kurz und konkret, keine Allgemeinplätze und keine Motivationssprüche.
- Beziehe dich auf die tatsächlichen Zahlen und Programme aus den Daten.
- Unterscheide Muster von Zufall: einzelne Ausreißer sind noch kein Trend.
- Wenn die Woche zu wenige Tage mit Daten hat, sag das offen.
- Antworte auf Deutsch und duze die Person.\
"""

#: Schema der Antwort — so kommen die Vorschläge strukturiert zurück.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vorschlaege": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Der Vorschlag, ein bis drei Sätze.",
                    },
                    "kategorie": {
                        "type": "string",
                        "enum": ["fokus", "workflow", "sonstiges"],
                        "description": "Fokus/Zeitmanagement oder Bedienung eines Programms.",
                    },
                },
                "required": ["text", "kategorie"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["vorschlaege"],
    "additionalProperties": False,
}


def build_day_payload(
    analysis: DayAnalysis,
    *,
    ocr_snippets: list[str] | None = None,
) -> dict[str, Any]:
    """Die verdichtete Tageszusammenfassung — genau das geht an die API."""
    dauer = timeutil.format_duration
    payload: dict[str, Any] = {
        "datum": analysis.day.isoformat(),
        "wochentag": _WEEKDAYS[analysis.day.weekday()],
        "erfasste_zeit": dauer(analysis.total_seconds),
        "fokuszeit": dauer(analysis.focus_seconds),
        "fokus_anteil_prozent": round(analysis.focus_share * 100),
        "ablenkungszeit": dauer(analysis.distraction_seconds),
        "ablenkung_anteil_prozent": round(analysis.distraction_share * 100),
        "fensterwechsel": analysis.switches,
        "wechsel_pro_stunde": round(analysis.switches_per_hour, 1),
        "laengster_fokusblock": dauer(analysis.longest_focus_seconds),
        "kategorien_minuten": {
            name: round(seconds / 60)
            for name, seconds in sorted(
                analysis.category_seconds.items(), key=lambda item: -item[1]
            )
        },
        "programme": [
            {
                "prozess": app.process_name,
                "kategorie": app.category,
                "minuten": round(app.seconds / 60),
                "aufrufe": app.events,
                "schnitt_sekunden": round(app.average_seconds),
            }
            for app in analysis.apps[:MAX_APPS]
        ],
        "fokus_sessions": [
            {
                "von": timeutil.to_local(session.start).strftime("%H:%M"),
                "bis": timeutil.to_local(session.end).strftime("%H:%M"),
                "fokuszeit": dauer(session.focus_seconds),
                "unterbrechungen": session.interruptions,
                "programm": session.main_process,
            }
            for session in analysis.focus_sessions[:MAX_SESSIONS]
        ],
        "lokale_hinweise": analysis.suggestions,
    }
    if ocr_snippets:
        payload["text_ausschnitte"] = [
            snippet[:MAX_OCR_LENGTH] for snippet in ocr_snippets[:MAX_OCR_SNIPPETS]
        ]
    return payload


def build_week_payload(analyses: list[DayAnalysis]) -> dict[str, Any]:
    """Verdichtete Wochenzahlen: je Tag eine Zeile plus Summen."""
    dauer = timeutil.format_duration
    mit_daten = [analysis for analysis in analyses if analysis.has_data]
    gesamt = sum(a.total_seconds for a in mit_daten)
    fokus = sum(a.focus_seconds for a in mit_daten)
    ablenkung = sum(a.distraction_seconds for a in mit_daten)

    programme: dict[str, int] = {}
    for analysis in mit_daten:
        for app in analysis.apps:
            programme[app.process_name] = programme.get(app.process_name, 0) + app.seconds

    return {
        "zeitraum": {
            "von": analyses[0].day.isoformat() if analyses else None,
            "bis": analyses[-1].day.isoformat() if analyses else None,
            "tage_mit_daten": len(mit_daten),
        },
        "summen": {
            "erfasste_zeit": dauer(gesamt),
            "fokuszeit": dauer(fokus),
            "fokus_anteil_prozent": round(fokus / gesamt * 100) if gesamt else 0,
            "ablenkungszeit": dauer(ablenkung),
            "ablenkung_anteil_prozent": round(ablenkung / gesamt * 100) if gesamt else 0,
        },
        "tage": [
            {
                "datum": analysis.day.isoformat(),
                "wochentag": _WEEKDAYS[analysis.day.weekday()],
                "erfasste_zeit": dauer(analysis.total_seconds),
                "fokus_anteil_prozent": round(analysis.focus_share * 100),
                "ablenkung_anteil_prozent": round(analysis.distraction_share * 100),
                "wechsel_pro_stunde": round(analysis.switches_per_hour, 1),
                "laengster_fokusblock": dauer(analysis.longest_focus_seconds),
            }
            for analysis in analyses
            if analysis.has_data
        ],
        "programme_gesamt": [
            {"prozess": name, "minuten": round(seconds / 60)}
            for name, seconds in sorted(programme.items(), key=lambda item: -item[1])[
                :MAX_APPS
            ]
        ],
    }


def collect_ocr_snippets(
    database, day: date, limit: int = MAX_OCR_SNIPPETS
) -> list[str]:
    """Textschnipsel der längsten Aufnahmen des Tages einsammeln.

    Wird nur aufgerufen, wenn ``[cloud] ocr_mitsenden = true`` gesetzt ist.
    """
    schnipsel = [
        eintrag.ocr_text.strip()
        for eintrag in database.screenshots(day=day)
        if eintrag.ocr_text and eintrag.ocr_text.strip()
    ]
    schnipsel.sort(key=len, reverse=True)
    return schnipsel[:limit]


_WEEKDAYS = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]
