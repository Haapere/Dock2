"""Startdatenbestand aus Konzept und Tracker.

Übernimmt die Inhalte der beiden Ausgangsdateien (Konzept_Content_Creator.docx
und Tracker_Content_Creator.xlsx) in die Datenbank, damit nicht bei null
angefangen werden muss: Ausrüstungsbudget, Kanal-Grundaufbau, Fahrplan und die
Pflichten aus dem Steuer-Kapitel.
"""

from __future__ import annotations

from datetime import date, timedelta

from creatordock import fahrplan, finanzen, kanaele
from creatordock.store import Store

# Kapitel 3 des Konzepts: Ausrüstung & Budget.
AUSRUESTUNG = (
    ("Kamera", "Neueres Smartphone oder Sony ZV-E10 (Einsteiger-Systemkamera)", 0, 700),
    ("Stativ", "Fluid-Kopf-Stativ für ruhige Schwenks", 40, 80),
    ("Licht", "2x LED-Panel mit Softbox/Diffusor (Neewer/Godox-Set)", 80, 150),
    ("Mikrofon", "Externes Richtmikro oder Lavalier", 40, 100),
    ("Speicher", "Externe, verschlüsselte SSD nur für Rohmaterial", 80, 150),
    ("Verifikation", "Ausweis-Scanner/App, Vertragsvorlagen", 0, 0),
)

# Kapitel 2 und 8: Pflichten und nächste Schritte, mit Fristen relativ zum Start.
FAHRPLAN = (
    ("Gewerbe beim Gewerbeamt anmelden", "Steuern", 7, "hoch",
     "Kosten ca. 20–40 €. Tätigkeitsbeschreibung ehrlich formulieren."),
    ("Fragebogen zur steuerlichen Erfassung über ELSTER einreichen", "Steuern", 30, "hoch",
     "Pflicht innerhalb eines Monats nach Aufnahme der Tätigkeit."),
    ("Kleinunternehmerregelung prüfen und entscheiden", "Steuern", 30, "hoch",
     "§ 19 UStG: Vorjahresumsatz bis 25.000 € und laufendes Jahr bis 100.000 €."),
    ("Getrenntes Geschäftskonto eröffnen", "Steuern", 14, "mittel",
     "Trennt private und geschäftliche Zahlungsströme, vereinfacht die EÜR."),
    ("Belegablage GoBD-konform einrichten", "Steuern", 30, "mittel",
     "Unveränderbar, vollständig, 10 Jahre aufbewahren."),
    ("Model-Release anwaltlich prüfen lassen", "Recht", 21, "hoch",
     "Vorlage aus CreatorDock exportieren und einmalig prüfen lassen."),
    ("Verschlüsselte Ablage für Ausweise und Verträge einrichten", "Recht", 7, "hoch",
     "VeraCrypt-Container oder Systemverschlüsselung. Gehört nicht in diese App."),
    ("Ausrüstung beschaffen und Lichtsetup testen", "Ausrüstung", 21, "mittel",
     "Budget siehe Ausrüstungsliste."),
    ("Künstlername festlegen und Verfügbarkeit prüfen", "Persona", 7, "hoch",
     "Auf allen Zielplattformen gleichzeitig prüfen, bevor er feststeht."),
    ("Projekt-Mailadresse und eigene Telefonnummer einrichten", "Persona", 7, "hoch",
     "Niemals die private Adresse oder Nummer verwenden."),
    ("Kanäle anlegen und überall Zwei-Faktor aktivieren", "Persona", 14, "hoch",
     "Siehe Kanal-Register."),
    ("Wasserzeichen und visuelle Identität festlegen", "Persona", 14, "mittel",
     "Einheitlich über alle Kanäle."),
    ("Nische schärfen: was unterscheidet den Kanal", "Marketing", 14, "hoch",
     "Ohne klare Nische verpufft die Reichweite."),
    ("Anzeige zur Partnerinnen-Suche veröffentlichen", "Marketing", 21, "mittel",
     "Vorlage in CreatorDock. Veröffentlichen, nicht anschreiben."),
    ("Content-Kalender für die ersten 6 Wochen füllen", "Marketing", 14, "hoch",
     "3× Teaser, 1× Paid-Release pro Woche."),
    ("Erster Solo-Dreh zum Test von Equipment und Workflow", "Produktion", 28, "mittel",
     "Ohne Partnerin — erst Technik und Ablauf sitzen lassen."),
)


def befuellen(store: Store, kuenstlername: str = "", start: str | None = None) -> dict:
    """Legt den Startdatenbestand an. Vorhandene Daten bleiben unberührt."""
    db = store.laden()
    projekt = db["projekt"]
    if kuenstlername:
        projekt["kuenstlername"] = kuenstlername.strip()
    startdatum = date.fromisoformat(start) if start else date.today()
    projekt["start"] = startdatum.isoformat()
    projekt.setdefault("opsec", {})

    angelegt = {"budget": 0, "kanaele": 0, "fahrplan": 0}

    if not store.sammlung("budget"):
        for position, empfehlung, von, bis in AUSRUESTUNG:
            finanzen.budget_posten(store, position, empfehlung, von, bis)
            angelegt["budget"] += 1

    if not store.sammlung("kanaele"):
        for kanal in kanaele.STANDARD_KANAELE:
            kanaele.anlegen(store, **kanal)
            angelegt["kanaele"] += 1

    if not store.sammlung("fahrplan"):
        for titel, bereich, tage, prioritaet, notiz in FAHRPLAN:
            fahrplan.anlegen(
                store,
                titel=titel,
                bereich=bereich,
                faellig=(startdatum + timedelta(days=tage)).isoformat(),
                prioritaet=prioritaet,
                notiz=notiz,
            )
            angelegt["fahrplan"] += 1

    return angelegt
