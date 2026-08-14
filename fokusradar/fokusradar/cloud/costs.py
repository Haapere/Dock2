"""Preise und Kostenschätzung der Claude-API.

Die Preise stehen hier als Tabelle, damit ``fokusradar kosten`` rechnen kann,
ohne ins Netz zu greifen. Sie sind ein Stand, kein Vertrag: maßgeblich ist
immer die Abrechnung von Anthropic. Bei Änderungen einfach die Tabelle
anpassen — oder ``[cloud] preis_input``/``preis_output`` in der Konfiguration
setzen, das schlägt die Tabelle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Stand der Preistabelle.
PRICE_DATE = date(2026, 8, 14)


@dataclass(frozen=True)
class ModelPrice:
    """Preis eines Modells in US-Dollar je einer Million Token."""

    input_per_mtok: float
    output_per_mtok: float
    note: str = ""

    def cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """Kosten eines Aufrufs in US-Dollar.

        Zwischengespeicherte Eingaben kosten rund ein Zehntel, das Schreiben
        in den Cache rund das 1,25-fache des normalen Eingabepreises.
        """
        eingabe = (
            input_tokens
            + cache_read_tokens * 0.1
            + cache_write_tokens * 1.25
        ) / 1_000_000 * self.input_per_mtok
        ausgabe = output_tokens / 1_000_000 * self.output_per_mtok
        return eingabe + ausgabe


#: Preise je Modell (US-Dollar pro Million Token), Stand siehe ``PRICE_DATE``.
PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": ModelPrice(5.0, 25.0),
    "claude-sonnet-5": ModelPrice(
        2.0, 10.0, "Einführungspreis bis 31.08.2026, danach 3 $ / 15 $"
    ),
    "claude-haiku-4-5": ModelPrice(1.0, 5.0),
    "claude-opus-4-8": ModelPrice(5.0, 25.0),
    "claude-fable-5": ModelPrice(10.0, 50.0),
}

#: Modelle, die FokusRadar in der Konfiguration anbietet.
SUPPORTED_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5")

#: Modelle, die den Parameter ``output_config.effort`` kennen.
#: Bei Haiku 4.5 führt er zu einem Fehler, deshalb bleibt er dort weg.
MODELS_WITH_EFFORT = frozenset(
    {"claude-opus-5", "claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"}
)


def price_for(model: str) -> ModelPrice | None:
    """Preis eines Modells; ``None``, wenn er hier nicht hinterlegt ist."""
    return PRICES.get(model)


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    *,
    price: ModelPrice | None = None,
) -> float:
    """Kosten eines Aufrufs schätzen; unbekanntes Modell ergibt 0."""
    tarif = price or price_for(model)
    if tarif is None:
        return 0.0
    return tarif.cost(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)


def format_usd(betrag: float) -> str:
    """Kleine Beträge lesbar machen: unter einem Cent als ``<0,01 $``."""
    if betrag <= 0:
        return "0,00 $"
    if betrag < 0.01:
        return "<0,01 $"
    return f"{betrag:.2f} $".replace(".", ",")
