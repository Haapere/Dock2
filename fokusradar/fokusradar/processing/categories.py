"""Regelbasierte Kategorisierung von Fensternutzungen.

Die Regeln stehen in ``categories.yaml`` (Vorgabe: neben der Konfigurationsdatei
im Benutzerprofil). Fehlt die Datei, gelten die eingebauten Regeln aus
``DEFAULT_CATEGORIES_YAML`` — FokusRadar ist also ohne Einrichtung nutzbar und
die Datei dient dem Feinschliff.

Reihenfolge der Prüfung (die erste Übereinstimmung gewinnt):

1. alle ``titel``-Muster, in der Reihenfolge der Kategorien in der Datei
2. alle ``prozesse``-Muster, ebenfalls in Reihenfolge
3. sonst die Kategorie aus ``standard``

Titel-Muster sind Teiltreffer (``youtube`` passt auf „… – YouTube – Firefox"),
Prozess-Muster sind Namensmuster mit ``*`` und ``?`` (``code.exe``, ``*chrome*``).
Groß-/Kleinschreibung spielt nirgends eine Rolle.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

# Wie eine Kategorie in der Auswertung zählt.
KIND_FOCUS = "fokus"
KIND_DISTRACTION = "ablenkung"
KIND_NEUTRAL = "neutral"
VALID_KINDS = {KIND_FOCUS, KIND_DISTRACTION, KIND_NEUTRAL}

DEFAULT_CATEGORIES_YAML = """\
# FokusRadar — Kategorien und Regeln
#
# "zaehlt_als" steuert die Auswertung:
#   fokus     — zählt als konzentrierte Arbeit (bildet die Fokus-Sessions)
#   ablenkung — zählt als Ablenkung (Top-Ablenkungen, Ablenkungsanteil)
#   neutral   — wird nur gezählt, aber weder als Fokus noch als Ablenkung gewertet
#
# Geprüft wird zuerst über alle "titel"-Muster (Teiltreffer), danach über alle
# "prozesse"-Muster (mit * und ? als Platzhaltern). Die erste Übereinstimmung gewinnt.
#
# Die Zahlen des Android-Begleiters laufen durch dieselben Regeln: dort steht der
# Paketname (com.instagram.android) an der Stelle des Prozesses und der App-Name
# an der Stelle des Fenstertitels.

standard: sonstiges

kategorien:
  - name: entwicklung
    zaehlt_als: fokus
    prozesse:
      - code.exe
      - devenv.exe
      - pycharm*.exe
      - idea*.exe
      - sublime_text.exe
      - notepad++.exe
      - WindowsTerminal.exe
      - powershell.exe
      - cmd.exe
      - windsurf.exe
      - com.termux
      - com.github.android
    titel:
      - stack overflow
      - github.com
      - gitlab
      - docs.python.org

  - name: schreiben_und_planen
    zaehlt_als: fokus
    prozesse:
      - WINWORD.EXE
      - EXCEL.EXE
      - POWERPNT.EXE
      - Acrobat.exe
      - obsidian.exe
      - notion.exe
      - onenote.exe
    titel:
      - confluence
      - jira

  - name: kommunikation
    zaehlt_als: neutral
    prozesse:
      - outlook.exe
      - ms-teams.exe
      - teams.exe
      - slack.exe
      - thunderbird.exe
      - zoom.exe
      - webex.exe
      - com.whatsapp
      - org.thoughtcrime.securesms
      - org.telegram.messenger
      - com.microsoft.teams
      - com.slack
      - com.google.android.gm

  - name: ablenkung
    zaehlt_als: ablenkung
    prozesse:
      - steam.exe
      - discord.exe
      - com.google.android.youtube
      - com.instagram.android
      - com.zhiliaoapp.musically
      - com.reddit.frontpage
      - com.netflix.mediaclient
      - tv.twitch.android.app
      - com.facebook.katana
      - com.snapchat.android
    titel:
      - youtube
      - netflix
      - twitch
      - reddit
      - instagram
      - tiktok
      - facebook
      - 9gag

  - name: sonstiges
    zaehlt_als: neutral
    prozesse:
      - explorer.exe
      - firefox.exe
      - chrome.exe
      - msedge.exe
      - spotify.exe
      - com.android.*
      - com.google.android.apps.*
      - org.mozilla.*
      - com.spotify.music
"""


class CategoryError(ValueError):
    """Fehlerhafte Regeldatei."""


@dataclass(frozen=True)
class Category:
    """Eine Kategorie samt ihrer Muster."""

    name: str
    kind: str = KIND_NEUTRAL
    process_patterns: tuple[str, ...] = ()
    title_patterns: tuple[str, ...] = ()

    @property
    def is_focus(self) -> bool:
        return self.kind == KIND_FOCUS

    @property
    def is_distraction(self) -> bool:
        return self.kind == KIND_DISTRACTION


class Categorizer:
    """Ordnet (Prozessname, Fenstertitel) einer Kategorie zu."""

    def __init__(
        self,
        categories: list[Category],
        default: str = "sonstiges",
        *,
        source: Path | None = None,
    ) -> None:
        self.categories = categories
        self.default = default
        self.source = source
        self._by_name = {category.name: category for category in categories}
        self._cache: dict[tuple[str, str | None], str] = {}

    # -- Laden --------------------------------------------------------------

    @classmethod
    def from_yaml(cls, text: str, *, source: Path | None = None) -> "Categorizer":
        """Regeln aus YAML-Text lesen."""
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - hängt an der Installation
            raise CategoryError(
                "Für die Kategorien wird PyYAML benötigt: pip install pyyaml"
            ) from exc

        try:
            raw = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise CategoryError(f"Regeldatei ist kein gültiges YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise CategoryError("Regeldatei muss eine Zuordnung auf oberster Ebene sein")

        entries = raw.get("kategorien", [])
        if not isinstance(entries, list) or not entries:
            raise CategoryError("Abschnitt 'kategorien' fehlt oder ist leer")

        categories: list[Category] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise CategoryError(f"Kategorie muss eine Zuordnung sein: {entry!r}")
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                raise CategoryError(f"Kategorie ohne gültigen 'name': {entry!r}")
            kind = entry.get("zaehlt_als", KIND_NEUTRAL)
            if kind not in VALID_KINDS:
                raise CategoryError(
                    f"Kategorie '{name}': 'zaehlt_als' muss "
                    f"{', '.join(sorted(VALID_KINDS))} sein, gefunden: {kind!r}"
                )
            categories.append(
                Category(
                    name=name.strip(),
                    kind=kind,
                    process_patterns=_pattern_tuple(entry.get("prozesse"), name, "prozesse"),
                    title_patterns=_pattern_tuple(entry.get("titel"), name, "titel"),
                )
            )

        default = raw.get("standard", categories[-1].name)
        if not isinstance(default, str) or default not in {c.name for c in categories}:
            raise CategoryError(
                f"'standard' muss auf eine vorhandene Kategorie zeigen, gefunden: {default!r}"
            )
        return cls(categories, default, source=source)

    @classmethod
    def default_rules(cls) -> "Categorizer":
        """Eingebaute Regeln."""
        return cls.from_yaml(DEFAULT_CATEGORIES_YAML)

    @classmethod
    def load(cls, path: Path | None) -> "Categorizer":
        """Regeln aus einer Datei laden; fehlt sie, gelten die eingebauten."""
        if path is None or not Path(path).is_file():
            return cls.default_rules()
        path = Path(path)
        return cls.from_yaml(path.read_text(encoding="utf-8"), source=path)

    # -- Zuordnung ----------------------------------------------------------

    def categorize(self, process_name: str, window_title: str | None = None) -> str:
        """Kategorie für eine Fensternutzung bestimmen."""
        key = (process_name, window_title)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        title = (window_title or "").casefold()
        process = (process_name or "").casefold()

        result = self.default
        for category in self.categories:
            if title and any(_matches_title(title, p) for p in category.title_patterns):
                result = category.name
                break
        else:
            for category in self.categories:
                if any(fnmatch.fnmatch(process, p) for p in category.process_patterns):
                    result = category.name
                    break

        if len(self._cache) > 2048:
            self._cache.clear()
        self._cache[key] = result
        return result

    def kind_of(self, category_name: str | None) -> str:
        """Wie eine Kategorie zählt (fokus/ablenkung/neutral)."""
        category = self._by_name.get(category_name or "")
        return category.kind if category else KIND_NEUTRAL

    def is_focus(self, category_name: str | None) -> bool:
        return self.kind_of(category_name) == KIND_FOCUS

    def is_distraction(self, category_name: str | None) -> bool:
        return self.kind_of(category_name) == KIND_DISTRACTION

    @property
    def names(self) -> list[str]:
        return [category.name for category in self.categories]


def _pattern_tuple(value: object, category: str, feld: str) -> tuple[str, ...]:
    """Musterliste einlesen und normalisieren."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CategoryError(f"Kategorie '{category}': '{feld}' muss eine Liste sein")
    patterns = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CategoryError(
                f"Kategorie '{category}': '{feld}' enthält kein gültiges Muster: {item!r}"
            )
        patterns.append(item.strip().casefold())
    return tuple(patterns)


def _matches_title(title: str, pattern: str) -> bool:
    """Titelmuster prüfen: Platzhalter-Muster oder Teiltreffer."""
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatch(title, pattern)
    return pattern in title


def write_default_categories(path: Path, *, overwrite: bool = False) -> Path:
    """Regeldatei mit den eingebauten Regeln anlegen."""
    path = Path(path).expanduser()
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_CATEGORIES_YAML, encoding="utf-8")
    return path
