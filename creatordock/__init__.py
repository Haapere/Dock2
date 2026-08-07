"""CreatorDock — lokale Projektzentrale für das Content-Creator-Projekt.

Verwaltet Partnerinnen-Onboarding (Altersverifikation, Model-Release, Widerruf),
Drehplanung, Content-Kalender, Kanäle, Finanzen und den Fahrplan — komplett
offline auf dem eigenen Rechner, ohne Cloud und ohne Fremdbibliotheken.

Einstieg:  ``creatordock gui``  (oder Doppelklick auf das Start-Skript)
"""

from creatordock.store import Store, datenordner

__all__ = ["Store", "datenordner"]
__version__ = "0.1.0"
