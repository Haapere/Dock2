"""Tests der Ausschlussliste."""

from __future__ import annotations

import pytest

from fokusradar.processing.exclusions import (
    DEFAULT_EXCLUSIONS_YAML,
    ExclusionError,
    ExclusionList,
    ExclusionRule,
    write_default_exclusions,
)


def test_prozessmuster_mit_platzhalter():
    regel = ExclusionRule("keepass*.exe", "process")
    assert regel.matches("KeePassXC.exe", None)
    assert regel.matches("keepass.exe", "Datenbank")
    assert not regel.matches("firefox.exe", "keepass")


def test_titelmuster_ist_teiltreffer():
    regel = ExclusionRule("online-banking", "title")
    assert regel.matches("firefox.exe", "Sparkasse Online-Banking – Mozilla Firefox")
    assert not regel.matches("firefox.exe", "Wetterbericht")
    assert not regel.matches("firefox.exe", None)


def test_ungueltige_regeln_werden_abgelehnt():
    with pytest.raises(ExclusionError):
        ExclusionRule("muster", "irgendwas")
    with pytest.raises(ExclusionError):
        ExclusionRule("   ", "process")


def test_liste_liefert_die_erste_passende_regel():
    liste = ExclusionList(
        [ExclusionRule("keepass*.exe", "process"), ExclusionRule("passwort", "title")]
    )
    treffer = liste.matching_rule("firefox.exe", "Mein Passwort-Tresor")
    assert treffer is not None and treffer.pattern == "passwort"
    assert liste.excludes("KeePassXC.exe")
    assert not liste.excludes("code.exe", "main.py")


def test_leere_liste_schliesst_nichts_aus():
    liste = ExclusionList()
    assert liste.is_empty
    assert not liste.excludes("keepass.exe", "Passwort")


def test_vorlage_wird_gelesen():
    liste = ExclusionList.from_yaml(
        "prozesse:\n  - tresor.exe\ntitel:\n  - geheim\n"
    )
    assert len(liste) == 2
    assert liste.excludes("tresor.exe")
    assert liste.excludes("firefox.exe", "Streng geheim")


def test_eingebaute_vorlage_deckt_die_klassiker_ab():
    liste = ExclusionList.default_rules()
    assert liste.excludes("KeePassXC.exe")
    assert liste.excludes("1Password.exe")
    assert liste.excludes("firefox.exe", "Sparkasse Online-Banking")
    assert not liste.excludes("code.exe", "main.py")


@pytest.mark.parametrize(
    "inhalt, teil",
    [
        ("prozesse: keine-liste\n", "muss eine Liste sein"),
        ("prozesse:\n  - 42\n", "kein gültiges Muster"),
        ("- liste\n- statt\n", "Zuordnung auf oberster Ebene"),
        ("prozesse: [\n", "kein gültiges YAML"),
    ],
)
def test_fehlerhafte_vorlage_meldet_klartext(inhalt, teil):
    with pytest.raises(ExclusionError) as fehler:
        ExclusionList.from_yaml(inhalt)
    assert teil in str(fehler.value)


def test_vorlage_anlegen(tmp_path):
    pfad = write_default_exclusions(tmp_path / "exclusions.yaml")
    assert pfad.read_text(encoding="utf-8") == DEFAULT_EXCLUSIONS_YAML
    with pytest.raises(FileExistsError):
        write_default_exclusions(pfad)


def test_beispieldatei_entspricht_der_vorlage():
    from pathlib import Path

    beispiel = Path(__file__).resolve().parent.parent / "config" / "exclusions.yaml"
    assert beispiel.read_text(encoding="utf-8") == DEFAULT_EXCLUSIONS_YAML


# -- Zusammenspiel mit der Datenbank ----------------------------------------


def test_liste_in_der_datenbank_pflegen(database):
    assert database.exclusions().is_empty

    erste = database.add_exclusion("keepass*.exe", "process")
    assert erste is not None
    assert database.add_exclusion("keepass*.exe", "process") is None  # keine Dubletten

    zweite = database.add_exclusion("online-banking", "title")
    liste = database.exclusions()
    assert len(liste) == 2
    assert liste.excludes("firefox.exe", "Sparkasse Online-Banking")

    assert database.remove_exclusion(zweite)
    assert not database.remove_exclusion(zweite)
    assert len(database.exclusions()) == 1


def test_vorlage_wird_nur_in_eine_leere_liste_uebernommen(database):
    uebernommen = database.seed_exclusions(ExclusionList.default_rules())
    assert uebernommen > 0
    # Zweiter Start: die gepflegte Liste bleibt unangetastet.
    assert database.seed_exclusions(ExclusionList.default_rules()) == 0

    database.remove_exclusion(database.exclusions().rules[0].id)
    vorher = len(database.exclusions())
    assert database.seed_exclusions(ExclusionList.default_rules()) == 0
    assert len(database.exclusions()) == vorher
