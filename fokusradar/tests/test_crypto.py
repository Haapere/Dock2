"""Tests der Datenbank-Verschlüsselung (SQLCipher)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from fokusradar.capture.base import WindowInfo
from fokusradar.config import StorageConfig
from fokusradar.storage import crypto
from fokusradar.storage.db import Database, DatabaseLocked

sqlcipher = pytest.importorskip("sqlcipher3", reason="Extra [krypto] nicht installiert")


def test_schluessel_wird_angelegt_und_wiederverwendet(tmp_path, monkeypatch):
    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    datei = tmp_path / "schluessel.key"

    erster = crypto.load_or_create_key(datei)
    assert datei.is_file() and len(erster) >= 32
    assert crypto.load_or_create_key(datei) == erster

    if hasattr(datei, "chmod"):  # unter Windows ohne Wirkung
        assert oct(datei.stat().st_mode)[-3:] in {"600", "666"}


def test_umgebungsvariable_hat_vorrang(tmp_path, monkeypatch):
    datei = tmp_path / "schluessel.key"
    crypto.write_key(datei, "aus-der-datei")
    monkeypatch.setenv(crypto.KEY_ENV_VAR, "aus-der-umgebung")
    assert crypto.load_key(datei) == "aus-der-umgebung"


def test_verschluesselte_datenbank_ist_ohne_schluessel_nicht_lesbar(tmp_path, monkeypatch):
    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    pfad = tmp_path / "geheim.db"
    schluessel = crypto.generate_key()

    with Database(pfad, encrypted=True, key=schluessel) as db:
        db.open_window_event(WindowInfo("code.exe", "geheimes-projekt.py"), _jetzt())

    assert crypto.is_encrypted(pfad)
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(str(pfad)).execute("SELECT count(*) FROM window_events")

    # Der Klartext taucht auch nirgends in der Datei auf.
    assert b"geheimes-projekt" not in pfad.read_bytes()

    with Database(pfad, encrypted=True, key=schluessel) as db:
        assert db.window_events()[0].window_title == "geheimes-projekt.py"


def test_falscher_schluessel_meldet_klartext(tmp_path, monkeypatch):
    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    pfad = tmp_path / "geheim.db"
    with Database(pfad, encrypted=True, key="richtig") as db:
        db.record_activity(_jetzt(), 5, 10)

    with pytest.raises(DatabaseLocked) as fehler:
        Database(pfad, encrypted=True, key="falsch").connect()
    assert "Schlüssel" in str(fehler.value)


def test_vorhandene_datenbank_laesst_sich_umstellen(tmp_path, monkeypatch):
    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    pfad = tmp_path / "klartext.db"
    with Database(pfad) as db:
        db.open_window_event(WindowInfo("code.exe", "main.py"), _jetzt())
        db.add_exclusion("keepass*.exe", "process")
    assert not crypto.is_encrypted(pfad)

    schluessel = crypto.generate_key()
    sicherung = crypto.encrypt_database(pfad, schluessel)

    assert crypto.is_encrypted(pfad)
    assert sicherung.is_file() and not crypto.is_encrypted(sicherung)
    with Database(pfad, encrypted=True, key=schluessel) as db:
        assert db.window_events()[0].process_name == "code.exe"
        assert len(db.exclusions()) == 1
        from fokusradar.storage.schema import SCHEMA_VERSION

        assert db.connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    with pytest.raises(ValueError):
        crypto.encrypt_database(pfad, schluessel)  # schon verschlüsselt


def test_from_config_nutzt_die_schluesseldatei(tmp_path, monkeypatch):
    monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
    from fokusradar.config import Config

    config = Config(
        storage=StorageConfig(encrypted=True, key_file=tmp_path / "k.key"),
        database_path=tmp_path / "db.sqlite",
    )
    with Database.from_config(config) as db:
        db.record_activity(_jetzt(), 1, 1)

    assert (tmp_path / "k.key").is_file()
    assert crypto.is_encrypted(tmp_path / "db.sqlite")

    # Ohne Verschlüsselung bleibt alles wie gehabt.
    offen = replace(config, storage=StorageConfig(), database_path=tmp_path / "offen.db")
    with Database.from_config(offen) as db:
        db.record_activity(_jetzt(), 1, 1)
    assert not crypto.is_encrypted(tmp_path / "offen.db")


def test_leere_oder_fehlende_datei_gilt_nicht_als_verschluesselt(tmp_path):
    assert not crypto.is_encrypted(tmp_path / "gibtsnicht.db")
    leer = tmp_path / "leer.db"
    leer.touch()
    assert not crypto.is_encrypted(leer)


def _jetzt():
    from fokusradar import timeutil

    return timeutil.now_utc()
