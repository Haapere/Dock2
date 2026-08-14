"""Cloud-Hybrid-Schicht: Vorschläge über die Claude-API (Phase 4).

Standardmäßig abgeschaltet. Ist sie aktiv, verlässt ausschließlich die
verdichtete Zusammenfassung aus :mod:`fokusradar.cloud.prompts` das Gerät.
"""

from fokusradar.cloud.client import (
    API_KEY_ENV_VAR,
    CloudAnalyzer,
    CloudError,
    CloudResult,
    CloudUnavailable,
    MissingApiKey,
    find_api_key,
    load_env_file,
)
from fokusradar.cloud.costs import (
    PRICE_DATE,
    SUPPORTED_MODELS,
    ModelPrice,
    estimate_cost,
    format_usd,
    price_for,
)
from fokusradar.cloud.prompts import (
    build_day_payload,
    build_week_payload,
    collect_ocr_snippets,
)
from fokusradar.cloud.vision import ImageError, ImageInfo, inspect_image

__all__ = [
    "ImageError",
    "ImageInfo",
    "inspect_image",
    "API_KEY_ENV_VAR",
    "PRICE_DATE",
    "SUPPORTED_MODELS",
    "CloudAnalyzer",
    "CloudError",
    "CloudResult",
    "CloudUnavailable",
    "MissingApiKey",
    "ModelPrice",
    "build_day_payload",
    "build_week_payload",
    "collect_ocr_snippets",
    "estimate_cost",
    "find_api_key",
    "format_usd",
    "load_env_file",
    "price_for",
]
