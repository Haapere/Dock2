"""Tests der Bild-Analyse (Phase 6).

Ein echtes Bild geht hier nie hinaus: der API-Aufruf läuft gegen eine Attrappe,
die aufzeichnet, was ihr übergeben wurde. Genau das ist der interessante Teil —
was das Gerät verlässt und unter welchen Bedingungen.
"""

from __future__ import annotations

import base64
import dataclasses
import struct
import zlib
from pathlib import Path

import pytest

from fokusradar.cloud import vision
from fokusradar.cloud.client import CloudAnalyzer, CloudError
from fokusradar.config import CloudConfig


def png_bytes(width: int = 40, height: int = 20) -> bytes:
    """Ein winziges, gültiges PNG bauen — ohne Zusatzpaket."""

    def chunk(art: bytes, daten: bytes) -> bytes:
        roh = art + daten
        return struct.pack(">I", len(daten)) + roh + struct.pack(">I", zlib.crc32(roh))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    zeilen = b"".join(b"\x00" + b"\x7f\x7f\x7f" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(zeilen))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def bild(tmp_path) -> Path:
    ziel = tmp_path / "aufnahme.png"
    ziel.write_bytes(png_bytes())
    return ziel


# -- Prüfen der Aufnahme -----------------------------------------------------


def test_aufnahme_wird_vermessen(bild):
    info = vision.inspect_image(bild)

    assert info.media_type == "image/png"
    assert (info.width, info.height) == (40, 20)
    assert info.size_bytes == bild.stat().st_size
    assert "40×20" in info.size_text
    # 800 Pixel sind weniger als ein Token wert — aufgerundet bleibt mindestens 1.
    assert 1 <= info.estimated_tokens <= vision.MAX_IMAGE_TOKENS


def test_grosse_aufnahme_schaetzt_hoechstens_die_obergrenze():
    info = vision.ImageInfo(
        path=Path("x.png"), media_type="image/png", size_bytes=1, width=4000, height=3000
    )
    assert info.estimated_tokens == vision.MAX_IMAGE_TOKENS


def test_unbekannte_masse_nehmen_den_schlechtesten_fall_an():
    info = vision.ImageInfo(path=Path("x.jpg"), media_type="image/jpeg", size_bytes=1)
    assert info.estimated_tokens == vision.MAX_IMAGE_TOKENS


def test_fehlende_datei(tmp_path):
    with pytest.raises(vision.ImageError, match="Keine Aufnahme"):
        vision.inspect_image(tmp_path / "gibtsnicht.png")


def test_unbekanntes_format(tmp_path):
    datei = tmp_path / "aufnahme.tiff"
    datei.write_bytes(b"egal")
    with pytest.raises(vision.ImageError, match="wird nicht unterstützt"):
        vision.inspect_image(datei)


def test_leere_datei(tmp_path):
    datei = tmp_path / "leer.png"
    datei.write_bytes(b"")
    with pytest.raises(vision.ImageError, match="leer"):
        vision.inspect_image(datei)


def test_zu_grosse_datei(tmp_path):
    datei = tmp_path / "riesig.png"
    datei.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * vision.MAX_IMAGE_BYTES)
    with pytest.raises(vision.ImageError, match="MB"):
        vision.inspect_image(datei)


def test_png_masse_nur_bei_echtem_png():
    assert vision.png_dimensions(b"kein png") == (None, None)
    assert vision.png_dimensions(png_bytes(7, 3)) == (7, 3)


# -- Was gesendet wird -------------------------------------------------------


def test_nachricht_enthaelt_bild_und_frage(bild):
    info = vision.inspect_image(bild)
    inhalt = vision.build_image_content(info, context="Im Vordergrund war code.exe.")

    assert [teil["type"] for teil in inhalt] == ["image", "text"]
    quelle = inhalt[0]["source"]
    assert quelle["type"] == "base64"
    assert quelle["media_type"] == "image/png"
    # Wirklich das Bild, unverändert.
    assert base64.standard_b64decode(quelle["data"]) == bild.read_bytes()
    assert "\n" not in quelle["data"]
    # Genau der Text, den --zeigen anzeigt — die Vorschau darf nicht abdriften.
    assert inhalt[1]["text"] == vision.build_question("Im Vordergrund war code.exe.")
    assert "code.exe" in inhalt[1]["text"]


def test_ohne_kontext_bleibt_die_frage_knapp(bild):
    inhalt = vision.build_image_content(vision.inspect_image(bild))
    assert "Dazu bekannt" not in inhalt[1]["text"]


def test_auftrag_verbietet_das_wiedergeben_von_inhalten():
    # Diese Zusage steht im README und ist der Grund, warum die Funktion
    # überhaupt vertretbar ist — sie darf nicht unbemerkt verschwinden.
    assert "Beschreibe **nicht**, was auf dem Bild steht" in vision.VISION_SYSTEM_PROMPT
    assert "niemals wieder" in vision.VISION_SYSTEM_PROMPT


# -- Der Aufruf --------------------------------------------------------------


class FakeBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FakeUsage:
    input_tokens = 1500
    output_tokens = 120
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [FakeBlock(text)]
        self.model = "claude-sonnet-5"
        self.usage = FakeUsage()
        self.stop_reason = "end_turn"


class FakeMessages:
    def __init__(self, antwort: str) -> None:
        self.antwort = antwort
        self.calls: list[dict] = []

    def create(self, **params):
        self.calls.append(params)
        return FakeResponse(self.antwort)


class FakeClient:
    """SDK-Attrappe — es geht garantiert nichts ins Netz."""

    def __init__(self, antwort: str) -> None:
        self.messages = FakeMessages(antwort)


ANTWORT = (
    '{"vorschlaege": [{"text": "Leg die beiden Fenster nebeneinander statt '
    'übereinander — in Windows mit Windows-Taste und Pfeiltaste.", '
    '"kategorie": "fenster"}]}'
)


@pytest.fixture
def bild_config(config):
    return dataclasses.replace(
        config, cloud=CloudConfig(enabled=True, send_images=True)
    )


def test_bild_analyse_sendet_und_liefert_vorschlaege(bild_config, bild):
    client = FakeClient(ANTWORT)
    analyzer = CloudAnalyzer(bild_config, client=client)

    ergebnis = analyzer.analyze_image(bild, context="Im Vordergrund war code.exe.")

    assert [text for text, _k in ergebnis.suggestions] == [
        "Leg die beiden Fenster nebeneinander statt übereinander — in Windows "
        "mit Windows-Taste und Pfeiltaste."
    ]
    assert ergebnis.suggestions[0][1] == "fenster"
    assert ergebnis.cost_usd > 0

    (aufruf,) = client.messages.calls
    inhalt = aufruf["messages"][0]["content"]
    assert inhalt[0]["type"] == "image"
    assert aufruf["system"] is vision.VISION_SYSTEM_PROMPT
    # Das eigene Schema, nicht das der Tagesanalyse.
    schema = aufruf["output_config"]["format"]["schema"]
    assert schema is vision.VISION_RESPONSE_SCHEMA


def test_ohne_schalter_geht_kein_bild_hinaus(config, bild):
    nur_cloud = dataclasses.replace(config, cloud=CloudConfig(enabled=True))
    client = FakeClient(ANTWORT)
    analyzer = CloudAnalyzer(nur_cloud, client=client)

    with pytest.raises(CloudError, match="bilder_senden"):
        analyzer.analyze_image(bild)

    assert client.messages.calls == []


def test_kaputte_aufnahme_wird_vor_dem_senden_bemerkt(bild_config, tmp_path):
    client = FakeClient(ANTWORT)
    analyzer = CloudAnalyzer(bild_config, client=client)

    with pytest.raises(vision.ImageError):
        analyzer.analyze_image(tmp_path / "fehlt.png")

    assert client.messages.calls == []


def test_ablehnung_wird_erkannt(bild_config, bild):
    client = FakeClient(ANTWORT)

    class Abgelehnt(FakeResponse):
        def __init__(self) -> None:
            super().__init__("")
            self.content = []
            self.stop_reason = "refusal"

    client.messages.create = lambda **params: Abgelehnt()
    analyzer = CloudAnalyzer(bild_config, client=client)

    ergebnis = analyzer.analyze_image(bild)
    assert ergebnis.refused
    assert ergebnis.suggestions == []


# -- Kommandozeile -----------------------------------------------------------


def test_cli_bild_zeigen_sendet_nichts(config, bild, capsys, monkeypatch):
    from fokusradar.cli import main

    def kein_netz(*args, **kwargs):  # pragma: no cover - darf nie laufen
        raise AssertionError("Es hätte kein Aufruf stattfinden dürfen")

    monkeypatch.setattr(CloudAnalyzer, "analyze_image", kein_netz)

    code = main(["--db", str(config.database_path), "bild", "--datei", str(bild), "--zeigen"])
    ausgabe = capsys.readouterr().out

    assert code == 0
    assert str(bild) in ausgabe
    assert "Gesendet wurde nichts" in ausgabe
    assert "40×20" in ausgabe
    # Auftrag und Nachricht stehen vollständig da, nicht als Zusammenfassung.
    assert "Beschreibe **nicht**, was auf dem Bild steht" in ausgabe
    for zeile in vision.build_question().splitlines():
        assert zeile in ausgabe


def test_cli_bild_ohne_schalter_bricht_ab(config, bild, capsys):
    from fokusradar.cli import main

    code = main(["--db", str(config.database_path), "bild", "--datei", str(bild)])
    fehler = capsys.readouterr().err

    assert code == 3
    assert "abgeschaltet" in fehler
    assert bild.is_file()  # nichts gelöscht


def test_cli_bild_ohne_vorhandene_aufnahme(config, capsys):
    from fokusradar.cli import main

    code = main(["--db", str(config.database_path), "bild"])
    fehler = capsys.readouterr().err

    assert code == 1
    assert "--neu" in fehler


# -- Wer löscht was? ---------------------------------------------------------
#
# Eine mitgegebene Datei gehört dem Nutzer und wird nie angerührt. Eine
# Aufnahme, die der Aufruf selbst gemacht hat, räumt er wieder weg — auch dann,
# wenn unterwegs etwas schiefgeht.


@pytest.fixture
def bild_konfig_datei(tmp_path):
    """Konfiguration mit eingeschalteter Bild-Analyse, auf der Platte."""
    from fokusradar.config import DEFAULT_CONFIG_TEMPLATE

    datei = tmp_path / "config.toml"
    text = DEFAULT_CONFIG_TEMPLATE.replace(
        'datenbank = ""', f'datenbank = "{tmp_path / "test.db"}"'
    )
    kopf = text.index("[cloud]")
    text = (
        text[:kopf]
        + text[kopf:]
        .replace("aktiv = false", "aktiv = true", 1)
        .replace("bilder_senden = false", "bilder_senden = true", 1)
    )
    datei.write_text(text, encoding="utf-8")
    return datei


def _fake_ergebnis():
    from fokusradar.cloud.client import CloudResult

    return CloudResult(
        suggestions=[("Leg die Fenster nebeneinander.", "fenster")],
        model="claude-sonnet-5",
        input_tokens=1500,
        output_tokens=80,
        cost_usd=0.0031,
    )


def test_cli_bild_ruehrt_die_mitgegebene_datei_nicht_an(
    bild_konfig_datei, bild, capsys, monkeypatch
):
    """Eine Datei, die der Nutzer selbst nennt, wird nie gelöscht."""
    from fokusradar.cli import main

    monkeypatch.setattr(
        CloudAnalyzer, "analyze_image", lambda self, pfad, **kw: _fake_ergebnis()
    )

    code = main(["--config", str(bild_konfig_datei), "bild", "--datei", str(bild)])
    ausgabe = capsys.readouterr().out

    assert code == 0
    assert bild.is_file(), "die mitgegebene Datei muss liegen bleiben"
    assert "gelöscht" not in ausgabe
    assert "Leg die Fenster nebeneinander." in ausgabe


def test_cli_bild_neu_raeumt_die_eigene_aufnahme_weg(
    bild_konfig_datei, tmp_path, capsys, monkeypatch
):
    from fokusradar import cli

    aufnahme = tmp_path / "frisch.png"
    aufnahme.write_bytes(png_bytes())
    monkeypatch.setattr(cli, "_bild_aufnehmen", lambda config: aufnahme)
    monkeypatch.setattr(
        CloudAnalyzer, "analyze_image", lambda self, pfad, **kw: _fake_ergebnis()
    )

    code = cli.main(["--config", str(bild_konfig_datei), "bild", "--neu"])

    assert code == 0
    assert not aufnahme.exists()
    assert "gelöscht" in capsys.readouterr().out


def test_cli_bild_neu_raeumt_auch_nach_einem_fehler_weg(
    bild_konfig_datei, tmp_path, monkeypatch
):
    """Ein misslungener Aufruf darf keine Aufnahme liegen lassen."""
    from fokusradar import cli

    aufnahme = tmp_path / "frisch.png"
    aufnahme.write_bytes(png_bytes())
    monkeypatch.setattr(cli, "_bild_aufnehmen", lambda config: aufnahme)

    def scheitert(self, pfad, **kw):
        raise CloudError("Aufruf der Claude-API fehlgeschlagen: Zeitüberschreitung")

    monkeypatch.setattr(CloudAnalyzer, "analyze_image", scheitert)

    code = cli.main(["--config", str(bild_konfig_datei), "bild", "--neu"])

    assert code == 3
    assert not aufnahme.exists()


def test_cli_bild_neu_mit_zeigen_sendet_nichts_und_raeumt_weg(
    bild_konfig_datei, tmp_path, capsys, monkeypatch
):
    from fokusradar import cli

    aufnahme = tmp_path / "frisch.png"
    aufnahme.write_bytes(png_bytes())
    monkeypatch.setattr(cli, "_bild_aufnehmen", lambda config: aufnahme)

    def kein_netz(self, pfad, **kw):  # pragma: no cover - darf nie laufen
        raise AssertionError("Es hätte kein Aufruf stattfinden dürfen")

    monkeypatch.setattr(CloudAnalyzer, "analyze_image", kein_netz)

    code = cli.main(["--config", str(bild_konfig_datei), "bild", "--neu", "--zeigen"])

    assert code == 0
    assert not aufnahme.exists()
    assert "Gesendet wurde nichts" in capsys.readouterr().out


def test_cli_bild_behalten_laesst_die_aufnahme_liegen(
    bild_konfig_datei, tmp_path, monkeypatch
):
    from fokusradar import cli

    aufnahme = tmp_path / "frisch.png"
    aufnahme.write_bytes(png_bytes())
    monkeypatch.setattr(cli, "_bild_aufnehmen", lambda config: aufnahme)
    monkeypatch.setattr(
        CloudAnalyzer, "analyze_image", lambda self, pfad, **kw: _fake_ergebnis()
    )

    code = cli.main(
        ["--config", str(bild_konfig_datei), "bild", "--neu", "--behalten"]
    )

    assert code == 0
    assert aufnahme.is_file()


def test_cli_bild_verbraucht_und_speichert(bild_konfig_datei, bild, monkeypatch):
    """Vorschlag und Verbrauch landen in der Datenbank."""
    from fokusradar.cli import main
    from fokusradar.config import load_config
    from fokusradar.storage.db import Database

    monkeypatch.setattr(
        CloudAnalyzer, "analyze_image", lambda self, pfad, **kw: _fake_ergebnis()
    )
    main(["--config", str(bild_konfig_datei), "bild", "--datei", str(bild)])

    config = load_config(bild_konfig_datei)
    with Database(config.database_path) as database:
        (verbrauch,) = database.api_usage()
        vorschlaege = database.suggestions()

    assert verbrauch.kind == "bild"
    assert verbrauch.input_tokens == 1500
    assert [v.category for v in vorschlaege] == ["bild/fenster"]
    assert [v.source for v in vorschlaege] == ["cloud"]


def test_vorschlag_ergaenzt_statt_zu_ersetzen(database):
    from datetime import date

    tag = date(2026, 8, 14)
    database.replace_suggestions(tag, "cloud", [("Aus der Tagesanalyse.", "fokus")])
    neu = database.add_suggestion(tag, "cloud", "Aus der Bildanalyse.", "bild/fenster")

    texte = {v.text for v in database.suggestions(day=tag)}
    assert neu is not None
    assert texte == {"Aus der Tagesanalyse.", "Aus der Bildanalyse."}

    # Derselbe Text kommt kein zweites Mal hinein.
    assert database.add_suggestion(tag, "cloud", "Aus der Bildanalyse.") is None
    assert len(database.suggestions(day=tag)) == 2
