"""FokusRadar — lokaler Aktivitäts-Monitor.

Phase 1: Erfassung des aktiven Fensters, Idle-Erkennung und Speicherung in einer
lokalen SQLite-Datenbank; Rohdaten-Anzeige über die Kommandozeile.
"""

from fokusradar.config import Config, load_config
from fokusradar.storage.db import Database
from fokusradar.agent import Tracker

__version__ = "0.1.0"

__all__ = ["Config", "load_config", "Database", "Tracker", "__version__"]
