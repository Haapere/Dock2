"""Ausschlussliste: was FokusRadar nie erfassen soll.

Passt das aktive Fenster auf ein Muster der Liste, wird **nichts** gespeichert —
kein Prozessname, kein Titel, kein Screenshot. Die Zeit fehlt dann bewusst in
der Auswertung; das ist der Preis dafür, dass Passwort-Manager, Banking und
Ähnliches gar nicht erst in der Datenbank landen.

Die gültige Liste steht in der Tabelle ``exclusion_list`` — sie lässt sich im
Dashboard und über ``fokusradar ausschluss`` pflegen. ``exclusions.yaml`` ist
nur die **Startvorlage**: Sie wird einmalig übernommen, solange die Tabelle
leer ist.

Muster:

* ``process`` — Prozessname mit ``*`` und ``?`` (``keepass*.exe``)
* ``title``   — Teiltreffer im Fenstertitel (``online-banking``), ``*``/``?`` erlaubt

Groß-/Kleinschreibung spielt keine Rolle.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

PATTERN_TYPES = ("process", "title")

DEFAULT_EXCLUSIONS_YAML = """\
# FokusRadar — Startvorlage der Ausschlussliste
#
# Fenster, die auf eines dieser Muster passen, werden nie erfasst: weder
# Prozessname noch Titel noch Screenshot. Diese Datei wird einmalig
# übernommen, solange die Ausschlussliste in der Datenbank leer ist.
# Danach ist die Datenbank maßgeblich — zu pflegen im Dashboard oder mit
#   fokusradar ausschluss hinzufuegen --prozess "keepass*.exe"

prozesse:
  - keepass*.exe
  - 1password*.exe
  - bitwarden*.exe
  - lastpass*.exe
  - "*keychain*"

titel:
  - online-banking
  - onlinebanking
  - passwort
  - password manager
  - tan-eingabe
"""


class ExclusionError(ValueError):
    """Fehlerhafte Ausschluss-Vorlage."""


@dataclass(frozen=True)
class ExclusionRule:
    """Ein Muster der Ausschlussliste."""

    pattern: str
    pattern_type: str = "process"
    id: int | None = None

    def __post_init__(self) -> None:
        if self.pattern_type not in PATTERN_TYPES:
            raise ExclusionError(
                f"Mustertyp muss 'process' oder 'title' sein, gefunden: {self.pattern_type!r}"
            )
        if not self.pattern.strip():
            raise ExclusionError("Muster darf nicht leer sein")

    @property
    def label(self) -> str:
        return "Prozess" if self.pattern_type == "process" else "Titel"

    def matches(self, process_name: str, window_title: str | None) -> bool:
        """Passt dieses Muster auf das aktive Fenster?"""
        pattern = self.pattern.casefold()
        if self.pattern_type == "process":
            return fnmatch.fnmatch((process_name or "").casefold(), pattern)
        title = (window_title or "").casefold()
        if not title:
            return False
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatch(title, pattern)
        return pattern in title


class ExclusionList:
    """Sammlung von Ausschlussmustern."""

    def __init__(self, rules: list[ExclusionRule] | None = None) -> None:
        self.rules = list(rules or [])

    def __len__(self) -> int:
        return len(self.rules)

    def __iter__(self):
        return iter(self.rules)

    @property
    def is_empty(self) -> bool:
        return not self.rules

    def matching_rule(
        self, process_name: str, window_title: str | None
    ) -> ExclusionRule | None:
        """Erstes passendes Muster; ``None``, wenn nichts greift."""
        for rule in self.rules:
            if rule.matches(process_name, window_title):
                return rule
        return None

    def excludes(self, process_name: str, window_title: str | None = None) -> bool:
        return self.matching_rule(process_name, window_title) is not None

    # -- Laden --------------------------------------------------------------

    @classmethod
    def from_yaml(cls, text: str) -> "ExclusionList":
        """Startvorlage aus YAML lesen."""
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - hängt an der Installation
            raise ExclusionError(
                "Für die Ausschluss-Vorlage wird PyYAML benötigt: pip install pyyaml"
            ) from exc

        try:
            raw = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ExclusionError(f"Vorlage ist kein gültiges YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ExclusionError("Vorlage muss eine Zuordnung auf oberster Ebene sein")

        rules: list[ExclusionRule] = []
        for key, pattern_type in (("prozesse", "process"), ("titel", "title")):
            entries = raw.get(key, [])
            if entries is None:
                continue
            if not isinstance(entries, list):
                raise ExclusionError(f"'{key}' muss eine Liste sein")
            for entry in entries:
                if not isinstance(entry, str) or not entry.strip():
                    raise ExclusionError(f"'{key}' enthält kein gültiges Muster: {entry!r}")
                rules.append(ExclusionRule(entry.strip(), pattern_type))
        return cls(rules)

    @classmethod
    def default_rules(cls) -> "ExclusionList":
        return cls.from_yaml(DEFAULT_EXCLUSIONS_YAML)

    @classmethod
    def load_template(cls, path: Path | None) -> "ExclusionList":
        """Vorlage aus einer Datei lesen; fehlt sie, gilt die eingebaute."""
        if path is None or not Path(path).is_file():
            return cls.default_rules()
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))


def write_default_exclusions(path: Path, *, overwrite: bool = False) -> Path:
    """Vorlage der Ausschlussliste anlegen."""
    path = Path(path).expanduser()
    if path.exists() and not overwrite:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_EXCLUSIONS_YAML, encoding="utf-8")
    return path
