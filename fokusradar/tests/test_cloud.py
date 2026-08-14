"""Tests der Cloud-Hybrid-Analyse.

Alle Tests laufen gegen eine Attrappe des Anthropic-SDK: es geht nie ein
echter Aufruf hinaus, und die Testläufe kosten nichts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta

import pytest

from fokusradar.capture.base import WindowInfo
from fokusradar.cloud import costs
from fokusradar.cloud.client import (
    API_KEY_ENV_VAR,
    CloudAnalyzer,
    CloudError,
    find_api_key,
    load_env_file,
)
from fokusradar.cloud.prompts import (
    build_day_payload,
    build_week_payload,
    collect_ocr_snippets,
)
from fokusradar.config import CloudConfig
from fokusradar.processing.analysis import analyze_day, last_days
from fokusradar.processing.categories import Categorizer

REGELN = """
standard: rest

kategorien:
  - name: arbeit
    zaehlt_als: fokus
    prozesse: [code.exe]
  - name: ablenkung
    zaehlt_als: ablenkung
    titel: [youtube]
  - name: rest
    zaehlt_als: neutral
    prozesse: [slack.exe, firefox.exe]
"""


# -- Attrappe des SDK --------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int = 1200
    output_tokens: int = 300
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeBlock:
    text: str
    type: str = "text"


@dataclass
class FakeResponse:
    content: list = field(default_factory=list)
    usage: FakeUsage = field(default_factory=FakeUsage)
    model: str = "claude-sonnet-5"
    stop_reason: str = "end_turn"


class FakeMessages:
    """Nimmt Aufrufe entgegen und liefert eine vorbereitete Antwort."""

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def create(self, **params):
        self.calls.append(params)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.messages = FakeMessages(response, error)


def antwort(vorschlaege: list[tuple[str, str]], **kwargs) -> FakeResponse:
    """Antwort im Format des Schemas bauen."""
    nutzlast = {
        "vorschlaege": [{"text": text, "kategorie": kat} for text, kat in vorschlaege]
    }
    return FakeResponse(
        content=[FakeBlock(json.dumps(nutzlast, ensure_ascii=False))], **kwargs
    )


# -- Vorbereitung ------------------------------------------------------------


@pytest.fixture
def regeln() -> Categorizer:
    return Categorizer.from_yaml(REGELN)


@pytest.fixture
def tag():
    return (datetime.now().astimezone() - timedelta(days=1)).date()


@pytest.fixture
def cloud_config(config):
    """Konfiguration mit eingeschalteter Cloud-Analyse."""
    return replace(config, cloud=CloudConfig(enabled=True))


@pytest.fixture
def analyse(database, regeln, tag):
    start = datetime.combine(tag, time(9, 0)).astimezone()
    verlauf = [
        (0, 3600, "code.exe", "main.py"),
        (60, 900, "firefox.exe", "Doku – YouTube"),
        (75, 2700, "code.exe", "test.py"),
    ]
    for versatz, dauer, prozess, titel in verlauf:
        beginn = start + timedelta(minutes=versatz)
        event_id = database.open_window_event(WindowInfo(prozess, titel), beginn)
        database.close_window_event(event_id, beginn + timedelta(seconds=dauer))
    return analyze_day(database, regeln, tag)


# -- Was das Gerät verlässt --------------------------------------------------


def test_nutzlast_enthaelt_keine_fenstertitel(analyse):
    nutzlast = build_day_payload(analyse)
    als_text = json.dumps(nutzlast, ensure_ascii=False)

    assert "main.py" not in als_text
    assert "YouTube" not in als_text
    assert "test.py" not in als_text
    # Prozessnamen und Kennzahlen sind dagegen ausdrücklich dabei.
    assert "code.exe" in als_text
    assert nutzlast["fokus_anteil_prozent"] == 88
    assert nutzlast["kategorien_minuten"]["arbeit"] == 105
    assert nutzlast["fensterwechsel"] == 3
    assert "text_ausschnitte" not in nutzlast


def test_ocr_schnipsel_nur_auf_ausdruecklichen_wunsch(analyse):
    ohne = build_day_payload(analyse)
    mit = build_day_payload(analyse, ocr_snippets=["Angebot 4711", "Kostenstelle"])

    assert "text_ausschnitte" not in ohne
    assert mit["text_ausschnitte"] == ["Angebot 4711", "Kostenstelle"]


def test_ocr_schnipsel_werden_gekuerzt(analyse):
    nutzlast = build_day_payload(analyse, ocr_snippets=["x" * 999])
    assert len(nutzlast["text_ausschnitte"][0]) == 400


def test_wochen_nutzlast_fasst_zusammen(database, regeln, tag, analyse):
    analysen = [analyze_day(database, regeln, t) for t in last_days(tag, 7)]
    nutzlast = build_week_payload(analysen)

    assert nutzlast["zeitraum"]["tage_mit_daten"] == 1
    assert nutzlast["summen"]["fokus_anteil_prozent"] == 88
    assert len(nutzlast["tage"]) == 1  # leere Tage werden weggelassen
    assert nutzlast["programme_gesamt"][0]["prozess"] == "code.exe"


def test_ocr_schnipsel_kommen_aus_der_datenbank(database, tag):
    beginn = datetime.combine(tag, time(10, 0)).astimezone()
    database.record_screenshot(beginn, ocr_text="kurz")
    database.record_screenshot(beginn, ocr_text="deutlich laengerer Text hier")
    database.record_screenshot(beginn, ocr_text=None)

    schnipsel = collect_ocr_snippets(database, tag)
    assert schnipsel == ["deutlich laengerer Text hier", "kurz"]


# -- Schlüssel ---------------------------------------------------------------


def test_env_datei_wird_gelesen(tmp_path):
    datei = tmp_path / ".env"
    datei.write_text(
        "# Kommentar\n\nANTHROPIC_API_KEY = \"sk-ant-test\"\nEGAL=1\n", encoding="utf-8"
    )
    werte = load_env_file(datei)
    assert werte[API_KEY_ENV_VAR] == "sk-ant-test"
    assert load_env_file(tmp_path / "fehlt.env") == {}


def test_umgebung_hat_vorrang_vor_der_datei(cloud_config, tmp_path, monkeypatch):
    config = replace(cloud_config, source=tmp_path / "config.toml")
    (tmp_path / ".env").write_text(f"{API_KEY_ENV_VAR}=aus-der-datei\n", encoding="utf-8")

    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    assert find_api_key(config) == "aus-der-datei"

    monkeypatch.setenv(API_KEY_ENV_VAR, "aus-der-umgebung")
    assert find_api_key(config) == "aus-der-umgebung"


def test_ohne_schluessel_meldet_der_analyzer_den_grund(
    config, analyse, tmp_path, monkeypatch
):
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    an = replace(
        config, cloud=CloudConfig(enabled=True), source=tmp_path / "config.toml"
    )
    analyzer = CloudAnalyzer(an)
    assert not analyzer.available()
    assert "kein API-Schlüssel" in analyzer.unavailable_reason()

    with pytest.raises(CloudError) as fehler:
        analyzer.analyze_day(analyse)
    assert "API-Schlüssel" in str(fehler.value)


def test_abgeschaltete_cloud_meldet_das(config, analyse):
    analyzer = CloudAnalyzer(config)
    assert "abgeschaltet" in analyzer.unavailable_reason()
    with pytest.raises(CloudError) as fehler:
        analyzer.analyze_day(analyse)
    assert "abgeschaltet" in str(fehler.value)


# -- Aufruf und Auswertung ---------------------------------------------------


def test_tagesanalyse_liefert_vorschlaege(cloud_config, analyse):
    client = FakeClient(
        antwort([("Blocke den Vormittag für code.exe.", "fokus")])
    )
    analyzer = CloudAnalyzer(cloud_config, client=client)

    ergebnis = analyzer.analyze_day(analyse)

    assert ergebnis.suggestions == [("Blocke den Vormittag für code.exe.", "fokus")]
    assert ergebnis.input_tokens == 1200
    assert ergebnis.output_tokens == 300
    assert ergebnis.cost_usd == pytest.approx(1200 / 1e6 * 2 + 300 / 1e6 * 10)
    assert not ergebnis.refused

    # Der Aufruf selbst: richtiges Modell, Schema, Aufwand.
    aufruf = client.messages.calls[0]
    assert aufruf["model"] == "claude-sonnet-5"
    assert aufruf["output_config"]["format"]["type"] == "json_schema"
    assert aufruf["output_config"]["effort"] == "medium"
    assert "Produktivitäts-Coach" in aufruf["system"]
    assert "main.py" not in json.dumps(aufruf["messages"], ensure_ascii=False)


def test_haiku_bekommt_keinen_aufwand_parameter(cloud_config, analyse):
    haiku = replace(
        cloud_config, cloud=replace(cloud_config.cloud, model="claude-haiku-4-5")
    )
    client = FakeClient(antwort([("Kurz und knapp.", "fokus")], model="claude-haiku-4-5"))

    CloudAnalyzer(haiku, client=client).analyze_day(analyse)

    aufruf = client.messages.calls[0]
    assert "effort" not in aufruf["output_config"]  # Haiku 4.5 lehnt ihn ab
    assert aufruf["output_config"]["format"]["type"] == "json_schema"


def test_ablehnung_wird_erkannt(cloud_config, analyse):
    client = FakeClient(FakeResponse(content=[], stop_reason="refusal"))
    ergebnis = CloudAnalyzer(cloud_config, client=client).analyze_day(analyse)

    assert ergebnis.refused
    assert ergebnis.suggestions == []


def test_fliesstext_wird_als_notnagel_ausgewertet(cloud_config, analyse):
    client = FakeClient(
        FakeResponse(
            content=[
                FakeBlock(
                    "Hier meine Hinweise:\n"
                    "- Lege die Chat-Prüfung auf zwei feste Zeitpunkte am Tag.\n"
                    "- Nutze in code.exe die Sprungmarken statt der Dateisuche.\n"
                )
            ]
        )
    )
    ergebnis = CloudAnalyzer(cloud_config, client=client).analyze_day(analyse)

    assert len(ergebnis.suggestions) == 2
    assert ergebnis.suggestions[0][0].startswith("Lege die Chat-Prüfung")


def test_sdk_fehler_wird_zu_klartext(cloud_config, analyse):
    client = FakeClient(error=RuntimeError("überlastet"))
    with pytest.raises(CloudError) as fehler:
        CloudAnalyzer(cloud_config, client=client).analyze_day(analyse)
    assert "Claude-API" in str(fehler.value)
    assert "überlastet" in str(fehler.value)


def test_ergebnis_wird_gespeichert(database, cloud_config, analyse, tag):
    client = FakeClient(antwort([("Ein Vorschlag mit genug Text.", "workflow")]))
    analyzer = CloudAnalyzer(cloud_config, client=client)

    ergebnis = analyzer.analyze_day(analyse)
    analyzer.store(database, tag, ergebnis)

    vorschlaege = database.suggestions(day=tag)
    assert [v.source for v in vorschlaege] == ["cloud"]
    assert vorschlaege[0].category == "workflow"
    assert database.has_cloud_suggestions(tag)

    verbrauch = database.api_usage()
    assert len(verbrauch) == 1
    assert verbrauch[0].model == "claude-sonnet-5"
    assert verbrauch[0].kind == "taeglich"
    assert verbrauch[0].cost_usd > 0

    summe = database.api_cost_summary()
    assert summe["aufrufe"] == 1
    assert summe["input_tokens"] == 1200


def test_lokale_und_cloud_vorschlaege_stehen_nebeneinander(
    database, cloud_config, analyse, tag
):
    from fokusradar.processing.analysis import store_analysis

    store_analysis(database, analyse)  # lokale Vorschläge
    client = FakeClient(antwort([("Ein Vorschlag aus der Cloud.", "fokus")]))
    analyzer = CloudAnalyzer(cloud_config, client=client)
    analyzer.store(database, tag, analyzer.analyze_day(analyse))

    quellen = {v.source for v in database.suggestions(day=tag)}
    assert quellen == {"local", "cloud"}


def test_wochenanalyse_nutzt_die_wochenvorlage(database, cloud_config, regeln, tag, analyse):
    analysen = [analyze_day(database, regeln, t) for t in last_days(tag, 7)]
    client = FakeClient(antwort([("Die Woche war ungleich verteilt.", "fokus")]))

    CloudAnalyzer(cloud_config, client=client).analyze_week(analysen)

    aufruf = client.messages.calls[0]
    assert "Wochenrückblick" in aufruf["system"]
    assert "zeitraum" in aufruf["messages"][0]["content"]


# -- Kosten ------------------------------------------------------------------


def test_kostenschaetzung():
    preis = costs.price_for("claude-sonnet-5")
    assert preis is not None
    # 1 Mio. Eingabe + 1 Mio. Ausgabe = 2 $ + 10 $
    assert preis.cost(1_000_000, 1_000_000) == pytest.approx(12.0)
    # Cache-Lesen kostet ein Zehntel
    assert preis.cost(0, 0, cache_read_tokens=1_000_000) == pytest.approx(0.2)
    assert costs.estimate_cost("gibt-es-nicht", 1_000, 1_000) == 0.0


def test_eigener_tarif_schlaegt_die_tabelle(cloud_config, analyse):
    teuer = replace(
        cloud_config,
        cloud=replace(cloud_config.cloud, price_input=100.0, price_output=200.0),
    )
    client = FakeClient(antwort([("Ein Vorschlag mit genug Text.", "fokus")]))
    ergebnis = CloudAnalyzer(teuer, client=client).analyze_day(analyse)

    assert ergebnis.cost_usd == pytest.approx(1200 / 1e6 * 100 + 300 / 1e6 * 200)


def test_betraege_werden_lesbar_formatiert():
    assert costs.format_usd(0) == "0,00 $"
    assert costs.format_usd(0.004) == "<0,01 $"
    assert costs.format_usd(1.5) == "1,50 $"


# -- Automatischer Auslöser in der Erfassung ---------------------------------


def _tracker(database, config, client, *, regeln=None):
    from fokusradar.agent import Tracker
    from tests.conftest import FakeIdleBackend, FakeInputCounter, FakeWindowBackend
    from fokusradar.processing.exclusions import ExclusionList

    tracker = Tracker(
        database,
        config,
        window_backend=FakeWindowBackend(),
        idle_backend=FakeIdleBackend(0.0),
        input_counter=FakeInputCounter(),
        categorizer=regeln or Categorizer.from_yaml(REGELN),
        exclusions=ExclusionList(),
    )
    tracker._cloud_analyzer = lambda: CloudAnalyzer(config, client=client)
    return tracker


def _abends(tag, stunde=19):
    return datetime.combine(tag, time(stunde, 0)).astimezone()


def test_tracker_holt_abends_die_tagesanalyse(database, cloud_config, analyse, tag):
    client = FakeClient(antwort([("Ein Vorschlag mit genug Text.", "fokus")]))
    tracker = _tracker(database, cloud_config, client)
    meldungen: list[str] = []
    tracker._on_event = meldungen.append

    tracker._maybe_cloud_analysis(_abends(tag))

    assert client.messages.calls, "es hätte ein Aufruf stattfinden müssen"
    assert database.has_cloud_suggestions(tag)
    assert tracker.stats.cloud_calls >= 1
    assert any("Cloud-Analyse" in text for text in meldungen)


def test_tracker_fragt_vor_der_uhrzeit_nicht(database, cloud_config, analyse, tag):
    client = FakeClient(antwort([("Ein Vorschlag mit genug Text.", "fokus")]))
    tracker = _tracker(database, cloud_config, client)

    tracker._maybe_cloud_analysis(_abends(tag, stunde=9))

    assert client.messages.calls == []
    assert not database.has_cloud_suggestions(tag)


def test_tracker_fragt_pro_tag_nur_einmal(database, cloud_config, analyse, tag):
    client = FakeClient(antwort([("Ein Vorschlag mit genug Text.", "fokus")]))
    tracker = _tracker(database, cloud_config, client)

    tracker._maybe_cloud_analysis(_abends(tag))
    erste_anzahl = len(client.messages.calls)
    # Der Zeitabstand-Schutz wird umgangen, trotzdem darf nichts passieren.
    tracker._last_cloud_check = None
    tracker._maybe_cloud_analysis(_abends(tag, stunde=20))

    assert len(client.messages.calls) == erste_anzahl


def test_tracker_ohne_cloud_ruehrt_nichts_an(database, config, analyse, tag):
    client = FakeClient(antwort([("Ein Vorschlag mit genug Text.", "fokus")]))
    tracker = _tracker(database, config, client)

    tracker._maybe_cloud_analysis(_abends(tag))

    assert client.messages.calls == []


def test_tracker_uebersteht_einen_api_fehler(database, cloud_config, analyse, tag):
    client = FakeClient(error=RuntimeError("Netzwerk weg"))
    tracker = _tracker(database, cloud_config, client)
    meldungen: list[str] = []
    tracker._on_event = meldungen.append

    tracker._maybe_cloud_analysis(_abends(tag))  # darf nicht durchschlagen

    assert any("fehlgeschlagen" in text for text in meldungen)
    assert not database.has_cloud_suggestions(tag)
