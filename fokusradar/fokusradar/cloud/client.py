"""Anbindung an die Claude-API (Hybrid-Schicht, Phase 4).

Der Ablauf einer Analyse:

1. Tag (oder Woche) **lokal** auswerten — das passiert ohnehin schon.
2. Aus dem Ergebnis die verdichtete Zusammenfassung bauen
   (:mod:`fokusradar.cloud.prompts` — dort steht, was das Gerät verlässt).
3. Genau diese Zusammenfassung an die Claude-API schicken.
4. Vorschläge mit ``source = 'cloud'`` speichern, Verbrauch und Kosten in
   ``api_usage`` festhalten.

Der API-Schlüssel kommt aus der Umgebungsvariablen ``ANTHROPIC_API_KEY`` oder
aus einer ``.env``-Datei neben der Konfiguration — nie aus der Datenbank und
nie aus dem Repository.

Ohne ``[cloud] aktiv = true`` passiert hier gar nichts: FokusRadar baut ohne
diesen Schalter keine Netzwerkverbindung auf.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from fokusradar import timeutil
from fokusradar.cloud import costs, prompts
from fokusradar.config import CloudConfig, Config
from fokusradar.processing.analysis import DayAnalysis

API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"


class CloudError(RuntimeError):
    """Die Cloud-Analyse ließ sich nicht durchführen."""


class CloudUnavailable(CloudError):
    """Das ``anthropic``-Paket fehlt."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "Für die Cloud-Analyse wird das Anthropic-SDK benötigt:\n"
            '    pip install "fokusradar[cloud]"' + (f"\n({detail})" if detail else "")
        )


class MissingApiKey(CloudError):
    """Es ist kein API-Schlüssel hinterlegt."""

    def __init__(self, env_path: Path) -> None:
        super().__init__(
            f"Kein API-Schlüssel gefunden. Setze {API_KEY_ENV_VAR} in der Umgebung\n"
            f"oder lege ihn in {env_path} ab:\n"
            f"    {API_KEY_ENV_VAR}=sk-ant-...\n"
            "Schlüssel gibt es unter https://platform.claude.com/ — die Datei "
            "gehört nicht ins Repository."
        )


@dataclass
class CloudResult:
    """Ergebnis eines API-Aufrufs."""

    suggestions: list[tuple[str, str]] = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str | None = None
    refused: bool = False

    @property
    def texts(self) -> list[str]:
        return [text for text, _kategorie in self.suggestions]


def load_env_file(path: Path) -> dict[str, str]:
    """Einfache ``.env``-Datei lesen (``SCHLÜSSEL=wert``, ``#`` ist Kommentar).

    Bewusst ohne Zusatzpaket: FokusRadar braucht genau eine Zeile daraus.
    """
    werte: dict[str, str] = {}
    path = Path(path).expanduser()
    if not path.is_file():
        return werte
    for zeile in path.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        name, _, wert = zeile.partition("=")
        wert = wert.strip().strip('"').strip("'")
        if name.strip():
            werte[name.strip()] = wert
    return werte


def find_api_key(config: Config) -> str | None:
    """API-Schlüssel suchen: erst Umgebung, dann ``.env`` neben der Konfiguration."""
    aus_umgebung = os.environ.get(API_KEY_ENV_VAR)
    if aus_umgebung and aus_umgebung.strip():
        return aus_umgebung.strip()
    aus_datei = load_env_file(config.env_path).get(API_KEY_ENV_VAR, "")
    return aus_datei.strip() or None


class CloudAnalyzer:
    """Erzeugt Vorschläge über die Claude-API und schreibt sie in die Datenbank."""

    def __init__(
        self,
        config: Config,
        *,
        client: Any | None = None,
        api_key: str | None = None,
    ) -> None:
        self.config = config
        self.settings: CloudConfig = config.cloud
        self._client = client
        self._api_key = api_key

    # -- Voraussetzungen ----------------------------------------------------

    def unavailable_reason(self) -> str | None:
        """Warum die Cloud-Analyse gerade nicht läuft — oder ``None``."""
        if not self.settings.enabled:
            return "in der Konfiguration abgeschaltet ([cloud] aktiv = false)"
        if self._client is not None:
            return None
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            return f"Anthropic-SDK nicht installiert ({exc})"
        if not (self._api_key or find_api_key(self.config)):
            return f"kein API-Schlüssel ({API_KEY_ENV_VAR} bzw. {self.config.env_path})"
        return None

    def available(self) -> bool:
        return self.unavailable_reason() is None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.settings.enabled:
            raise CloudError(
                "Die Cloud-Analyse ist abgeschaltet. Zum Einschalten in der "
                "Konfiguration [cloud] aktiv = true setzen."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - hängt an der Installation
            raise CloudUnavailable(str(exc)) from exc

        schluessel = self._api_key or find_api_key(self.config)
        if not schluessel:
            raise MissingApiKey(self.config.env_path)
        self._client = anthropic.Anthropic(
            api_key=schluessel, timeout=self.settings.timeout_seconds
        )
        return self._client

    # -- Analysen -----------------------------------------------------------

    def analyze_day(
        self, analysis: DayAnalysis, *, ocr_snippets: list[str] | None = None
    ) -> CloudResult:
        """Tageszusammenfassung an die API geben und Vorschläge zurückliefern."""
        self._ensure_client()  # erst prüfen, dann Daten aufbereiten
        payload = prompts.build_day_payload(analysis, ocr_snippets=ocr_snippets)
        return self._ask(
            prompts.SYSTEM_PROMPT,
            "Hier ist meine Tageszusammenfassung als JSON:\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def analyze_week(self, analyses: list[DayAnalysis]) -> CloudResult:
        """Wochenzahlen an die API geben und einen Rückblick zurückliefern."""
        self._ensure_client()
        payload = prompts.build_week_payload(analyses)
        return self._ask(
            prompts.WEEK_SYSTEM_PROMPT,
            "Hier sind meine Wochenzahlen als JSON:\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _ask(self, system_prompt: str, user_text: str) -> CloudResult:
        """Einen Aufruf ausführen und die Antwort auswerten."""
        client = self._ensure_client()
        model = self.settings.model

        params: dict[str, Any] = {
            "model": model,
            "max_tokens": self.settings.max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_text}],
            "output_config": {
                "format": {"type": "json_schema", "schema": prompts.RESPONSE_SCHEMA}
            },
        }
        # Haiku 4.5 kennt den Effort-Parameter nicht und lehnt ihn ab.
        if model in costs.MODELS_WITH_EFFORT:
            params["output_config"]["effort"] = self.settings.effort

        try:
            response = client.messages.create(**params)
        except Exception as exc:  # SDK-Fehler in eine klare Meldung überführen
            raise CloudError(f"Aufruf der Claude-API fehlgeschlagen: {exc}") from exc

        return self._to_result(response, model)

    def _to_result(self, response: Any, model: str) -> CloudResult:
        """Antwort in ein ``CloudResult`` überführen (inklusive Kosten)."""
        verbrauch = getattr(response, "usage", None)
        ergebnis = CloudResult(
            model=getattr(response, "model", model) or model,
            input_tokens=int(getattr(verbrauch, "input_tokens", 0) or 0),
            output_tokens=int(getattr(verbrauch, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(verbrauch, "cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(
                getattr(verbrauch, "cache_creation_input_tokens", 0) or 0
            ),
            stop_reason=getattr(response, "stop_reason", None),
        )
        ergebnis.cost_usd = costs.estimate_cost(
            ergebnis.model,
            ergebnis.input_tokens,
            ergebnis.output_tokens,
            ergebnis.cache_read_tokens,
            ergebnis.cache_write_tokens,
            price=self.settings.price,
        )

        # Eine Ablehnung ist eine gültige Antwort mit leerem Inhalt — vor dem
        # Auslesen von content prüfen, sonst greift man ins Leere.
        if ergebnis.stop_reason == "refusal":
            ergebnis.refused = True
            return ergebnis

        ergebnis.suggestions = _parse_suggestions(response)
        return ergebnis

    # -- Speichern ----------------------------------------------------------

    def store(
        self, database, day: date, result: CloudResult, kind: str = "taeglich"
    ) -> None:
        """Vorschläge und Verbrauch festhalten."""
        if result.suggestions:
            database.replace_suggestions(day, "cloud", result.suggestions)
        database.record_api_usage(
            timeutil.now_utc(),
            day=day,
            kind=kind,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_write_tokens=result.cache_write_tokens,
            cost_usd=result.cost_usd,
        )


def _parse_suggestions(response: Any) -> list[tuple[str, str]]:
    """Vorschläge aus der Antwort lesen.

    Erwartet wird das JSON aus ``RESPONSE_SCHEMA``. Falls doch einmal Fließtext
    zurückkommt, werden Aufzählungszeilen als Notnagel ausgewertet — lieber ein
    brauchbarer Vorschlag als eine Ausnahme.
    """
    text = "".join(
        block.text
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ).strip()
    if not text:
        return []

    try:
        daten = json.loads(text)
    except json.JSONDecodeError:
        return _parse_plain_text(text)

    eintraege = daten.get("vorschlaege") if isinstance(daten, dict) else None
    if not isinstance(eintraege, list):
        return _parse_plain_text(text)

    ergebnis: list[tuple[str, str]] = []
    for eintrag in eintraege:
        if isinstance(eintrag, dict) and str(eintrag.get("text", "")).strip():
            ergebnis.append(
                (str(eintrag["text"]).strip(), str(eintrag.get("kategorie", "cloud")))
            )
        elif isinstance(eintrag, str) and eintrag.strip():
            ergebnis.append((eintrag.strip(), "cloud"))
    return ergebnis


def _parse_plain_text(text: str) -> list[tuple[str, str]]:
    """Notnagel: Aufzählungszeilen aus Fließtext holen."""
    zeilen = [
        zeile.strip().lstrip("-•*0123456789. ").strip()
        for zeile in text.splitlines()
        if zeile.strip().startswith(("-", "•", "*"))
        or (zeile.strip()[:2].rstrip(".").isdigit() and "." in zeile[:3])
    ]
    treffer = [(zeile, "cloud") for zeile in zeilen if len(zeile) > 20]
    if treffer:
        return treffer
    return [(text.strip(), "cloud")] if len(text.strip()) > 20 else []
