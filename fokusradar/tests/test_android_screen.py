"""Tests der Bildschirm-Aufnahmen vom Handy (Phase 6)."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from fokusradar.android import screen
from fokusradar.android.sync import SyncError
from fokusradar.config import AndroidConfig, ScreenshotConfig
from fokusradar.processing.exclusions import ExclusionList, ExclusionRule
from tests.test_vision import png_bytes

ZEITPUNKT = datetime(2026, 8, 14, 10, 30, tzinfo=timezone.utc)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


# -- Prüfen ------------------------------------------------------------------


def test_png_wird_angenommen():
    aufnahme = screen.parse_capture(
        png_bytes(), device="Pixel-7", package="com.example.app", label="Beispiel"
    )
    assert aufnahme.suffix == ".png"
    assert aufnahme.device == "Pixel-7"
    assert aufnahme.package == "com.example.app"
    assert aufnahme.label == "Beispiel"


def test_jpeg_wird_angenommen():
    assert screen.parse_capture(JPEG, device="G", package="p").suffix == ".jpg"


@pytest.mark.parametrize(
    "daten, geraet, paket, teil",
    [
        (png_bytes(), "", "com.x", "Geraet"),
        (png_bytes(), "G", "  ", "Paket"),
        (b"", "G", "com.x", "leer"),
        (b"weder png noch jpeg", "G", "com.x", "kein PNG"),
    ],
)
def test_unbrauchbares_wird_abgelehnt(daten, geraet, paket, teil):
    with pytest.raises(SyncError) as fehler:
        screen.parse_capture(daten, device=geraet, package=paket)
    assert teil in str(fehler.value)


def test_zu_grosse_aufnahme():
    riesig = b"\x89PNG\r\n\x1a\n" + b"\x00" * screen.MAX_IMAGE_BYTES
    with pytest.raises(SyncError) as fehler:
        screen.parse_capture(riesig, device="G", package="com.x")
    assert fehler.value.status == 413


# -- Übernehmen --------------------------------------------------------------


class FakeOcr:
    """Erkennt immer denselben Text — Tesseract braucht hier niemand."""

    def __init__(self, text: str | None = "Posteingang   3 ungelesen") -> None:
        self.result = text
        self.images: list = []

    def text(self, image):
        self.images.append(image)
        # Bei der Texterkennung muss das Bild noch da sein.
        assert image.is_file()
        return self.result


@pytest.fixture
def bild_config(config, tmp_path):
    return dataclasses.replace(
        config,
        android=AndroidConfig(enabled=True, token="geheim"),
        screenshots=ScreenshotConfig(enabled=True, directory=tmp_path / "aufnahmen"),
    )


def test_aufnahme_wird_erkannt_und_das_bild_geloescht(database, bild_config):
    ocr = FakeOcr()
    aufnahme = screen.parse_capture(png_bytes(), device="Pixel-7", package="com.example.app")

    bericht = screen.store_capture(
        database, bild_config, aufnahme, ocr_backend=ocr, now=ZEITPUNKT
    )

    assert bericht["status"] == "ok"
    assert bericht["bild"] == "gelöscht"
    assert bericht["zeichen"] > 0
    assert len(ocr.images) == 1
    assert not ocr.images[0].exists()  # das Bild ist wieder weg

    (eintrag,) = database.screenshots()
    assert eintrag.device == "Pixel-7"
    assert eintrag.context == "com.example.app"
    assert eintrag.source_label == "Pixel-7"
    assert "Posteingang" in eintrag.ocr_text
    assert not eintrag.image_available


def test_bild_bleibt_wenn_es_bleiben_soll(database, bild_config, tmp_path):
    behalten = dataclasses.replace(
        bild_config,
        screenshots=ScreenshotConfig(
            enabled=True, directory=tmp_path / "aufnahmen", delete_image=False
        ),
    )
    aufnahme = screen.parse_capture(png_bytes(), device="Pixel-7", package="com.example.app")

    bericht = screen.store_capture(
        database, behalten, aufnahme, ocr_backend=FakeOcr(), now=ZEITPUNKT
    )

    (eintrag,) = database.screenshots()
    assert eintrag.image_available
    assert bericht["bild"] == eintrag.screenshot_path


def test_ausgeschlossene_app_beruehrt_die_platte_nie(database, bild_config, tmp_path):
    liste = ExclusionList([ExclusionRule("*bank*", "process")])
    aufnahme = screen.parse_capture(png_bytes(), device="Pixel-7", package="de.meinebank.app")

    bericht = screen.store_capture(
        database,
        bild_config,
        aufnahme,
        ocr_backend=FakeOcr(),
        exclusions=liste,
        now=ZEITPUNKT,
    )

    assert bericht["status"] == "ausgeschlossen"
    assert bericht["gespeichert"] is False
    assert database.screenshots() == []
    ordner = tmp_path / "aufnahmen"
    assert not ordner.exists() or not list(ordner.iterdir())


def test_ohne_texterkennung_wird_nur_der_eintrag_geschrieben(database, bild_config):
    aufnahme = screen.parse_capture(png_bytes(), device="Tablet", package="com.example.app")

    bericht = screen.store_capture(database, bild_config, aufnahme, now=ZEITPUNKT)

    assert bericht["zeichen"] == 0
    (eintrag,) = database.screenshots()
    assert eintrag.ocr_text is None
    assert eintrag.device == "Tablet"


def test_dateiname_traegt_geraet_und_zeit(database, bild_config, tmp_path):
    behalten = dataclasses.replace(
        bild_config,
        screenshots=ScreenshotConfig(
            enabled=True, directory=tmp_path / "aufnahmen", delete_image=False
        ),
    )
    aufnahme = screen.parse_capture(png_bytes(), device="Pixel 7/Pro", package="com.x")

    screen.store_capture(database, behalten, aufnahme, now=ZEITPUNKT)

    (datei,) = list((tmp_path / "aufnahmen").iterdir())
    assert datei.suffix == ".png"
    assert "Pixel-7-Pro" in datei.name  # kein Schrägstrich im Dateinamen


def test_geraete_lassen_sich_getrennt_abfragen(database, bild_config):
    for geraet in ("Pixel-7", "Tablet", "Pixel-7"):
        screen.store_capture(
            database,
            bild_config,
            screen.parse_capture(png_bytes(), device=geraet, package="com.x"),
            now=ZEITPUNKT,
        )

    assert len(database.screenshots()) == 3
    assert len(database.screenshots(device="Pixel-7")) == 2
    assert database.screenshots(device="Rechner") == []


# -- Endpunkt ----------------------------------------------------------------

pytest.importorskip("fastapi", reason="Dashboard-Tests brauchen FastAPI")
pytest.importorskip("httpx", reason="TestClient benötigt httpx")

KOPF = {
    "Authorization": "Bearer geheim",
    "X-FokusRadar-Geraet": "Pixel-7",
    "X-FokusRadar-Paket": "com.example.app",
    "Content-Type": "image/png",
}


def _client(config):
    from fastapi.testclient import TestClient

    from fokusradar.dashboard.app import create_app

    return TestClient(create_app(config), raise_server_exceptions=False)


def test_endpunkt_nimmt_eine_aufnahme_an(bild_config):
    antwort = _client(bild_config).post(
        "/api/android/bildschirm", content=png_bytes(), headers=KOPF
    )
    assert antwort.status_code == 200
    assert antwort.json()["gespeichert"] is True


def test_endpunkt_gibt_es_nur_mit_token(bild_config):
    antwort = _client(bild_config).post("/api/android/bildschirm", content=png_bytes())
    assert antwort.status_code == 401


def test_ohne_android_gibt_es_den_endpunkt_nicht(config):
    antwort = _client(config).post(
        "/api/android/bildschirm", content=png_bytes(), headers=KOPF
    )
    assert antwort.status_code == 404


def test_abgeschaltete_screenshots_nehmen_nichts_an(bild_config):
    ohne = dataclasses.replace(bild_config, screenshots=ScreenshotConfig(enabled=False))
    antwort = _client(ohne).post(
        "/api/android/bildschirm", content=png_bytes(), headers=KOPF
    )
    assert antwort.status_code == 409
    assert "[screenshots] aktiv" in antwort.json()["detail"]


def test_kein_bild_im_rumpf(bild_config):
    antwort = _client(bild_config).post(
        "/api/android/bildschirm", content=b"kein bild", headers=KOPF
    )
    assert antwort.status_code == 400


def test_fehlender_kopf(bild_config):
    kopf = {k: v for k, v in KOPF.items() if k != "X-FokusRadar-Paket"}
    antwort = _client(bild_config).post(
        "/api/android/bildschirm", content=png_bytes(), headers=kopf
    )
    assert antwort.status_code == 400
    assert "Paket" in antwort.json()["detail"]
