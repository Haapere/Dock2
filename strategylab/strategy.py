"""Strategie-Basisklasse und Registry.

Eine Strategie erzeugt aus OHLCV-Daten eine Zielpositions-Serie:
    +1 = long, 0 = flat, -1 = short.
Die Umsetzung (Ausführung am Folgetag, Kosten) übernimmt der Backtester.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

import pandas as pd

_REGISTRY: dict[str, type["Strategy"]] = {}


class Strategy(ABC):
    """Basisklasse für alle Strategien.

    Unterklassen definieren `params` (Default-Parameter) und implementieren
    `generate_signals`, das eine Positions-Serie in {-1, 0, +1} zurückgibt.
    """

    name: str = "strategy"
    params: dict[str, Any] = {}

    def __init__(self, **overrides: Any):
        unknown = set(overrides) - set(self.params)
        if unknown:
            raise ValueError(
                f"Unbekannte Parameter für '{self.name}': {sorted(unknown)}. "
                f"Erlaubt: {sorted(self.params)}"
            )
        self.p = {**self.params, **overrides}

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Liefert die Zielposition (-1/0/+1) je Handelstag."""

    def describe(self) -> str:
        params = ", ".join(f"{k}={v}" for k, v in self.p.items())
        return f"{self.name}({params})"


def register_strategy(cls: type[Strategy]) -> type[Strategy]:
    """Klassen-Dekorator: macht die Strategie über ihren Namen auffindbar."""
    if not cls.name or cls.name == "strategy":
        raise ValueError(f"{cls.__name__} braucht ein eindeutiges 'name'-Attribut")
    _REGISTRY[cls.name] = cls
    return cls


def get_strategy(name: str, **params: Any) -> Strategy:
    _ensure_builtins_loaded()
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(keine)"
        raise KeyError(f"Strategie '{name}' nicht gefunden. Verfügbar: {available}")
    return _REGISTRY[name](**params)


def list_strategies() -> Iterator[tuple[str, type[Strategy]]]:
    _ensure_builtins_loaded()
    yield from sorted(_REGISTRY.items())


def _ensure_builtins_loaded() -> None:
    # Import erst hier, um Zirkularimporte zwischen strategy.py und
    # den Strategie-Modulen zu vermeiden.
    import strategylab.strategies  # noqa: F401


def parse_params(raw: str | None) -> dict[str, Any]:
    """Parst CLI-Parameter der Form 'fast=20,slow=50,threshold=1.5'."""
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"Ungültiges Parameterformat: '{pair}' (erwartet key=value)")
        key, value = pair.split("=", 1)
        out[key.strip()] = _coerce(value.strip())
    return out


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value
