"""Verschlüsselung der lokalen Datenbank (SQLCipher).

Eingeschaltet über ``[speicher] verschluesselt = true``. Nötig ist dafür das
Extra ``[krypto]`` (``sqlcipher3-binary``); ohne das Paket meldet FokusRadar
das im Klartext und startet nicht mit halb offener Datenbank.

Der Schlüssel kommt entweder aus der Umgebungsvariablen ``FOKUSRADAR_KEY``
oder aus einer Schlüsseldatei neben der Datenbank. Fehlt sie, wird beim ersten
Start eine mit Zufallsschlüssel angelegt (unter Linux/macOS mit Rechten 0600).

Achtung, ohne Umschweife: Wer die Schlüsseldatei verliert, verliert die Daten.
Es gibt keine Hintertür.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
from pathlib import Path

KEY_ENV_VAR = "FOKUSRADAR_KEY"


class EncryptionUnavailable(RuntimeError):
    """SQLCipher ist nicht installiert."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "Für die verschlüsselte Datenbank wird SQLCipher benötigt:\n"
            '    pip install "fokusradar[krypto]"'
            + (f"\n({detail})" if detail else "")
        )


def sqlcipher_module():
    """DB-API-Modul von SQLCipher liefern."""
    try:
        from sqlcipher3 import dbapi2
    except ImportError as exc:  # pragma: no cover - hängt an der Installation
        raise EncryptionUnavailable(str(exc)) from exc
    return dbapi2


def encryption_available() -> bool:
    """Steht SQLCipher zur Verfügung?"""
    try:
        sqlcipher_module()
    except EncryptionUnavailable:
        return False
    return True


def generate_key() -> str:
    """Neuen Zufallsschlüssel erzeugen."""
    return secrets.token_urlsafe(32)


def load_key(key_file: Path) -> str | None:
    """Schlüssel lesen: erst Umgebungsvariable, dann Datei."""
    from_env = os.environ.get(KEY_ENV_VAR)
    if from_env and from_env.strip():
        return from_env.strip()
    key_file = Path(key_file).expanduser()
    if key_file.is_file():
        key = key_file.read_text(encoding="utf-8").strip()
        return key or None
    return None


def load_or_create_key(key_file: Path) -> str:
    """Schlüssel lesen oder beim ersten Mal anlegen."""
    existing = load_key(key_file)
    if existing:
        return existing
    return write_key(key_file, generate_key())


def write_key(key_file: Path, key: str) -> str:
    """Schlüssel in eine Datei schreiben und die Rechte einschränken."""
    key_file = Path(key_file).expanduser()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key + "\n", encoding="utf-8")
    try:  # unter Windows wirkungslos, dort schützt die Benutzer-ACL
        key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover - z. B. exotische Dateisysteme
        pass
    return key


def apply_key(connection, key: str) -> None:
    """``PRAGMA key`` setzen — muss vor jeder anderen Anweisung passieren.

    ``PRAGMA`` nimmt keine Platzhalter, der Schlüssel muss also in die
    Anweisung selbst. Einfache Anführungszeichen werden nach SQL-Regel
    verdoppelt, damit auch Schlüssel mit Sonderzeichen sicher ankommen.
    """
    escaped = key.replace("'", "''")
    connection.execute(f"PRAGMA key = '{escaped}'")


def is_encrypted(path: Path) -> bool:
    """Sieht die Datei nach einer verschlüsselten Datenbank aus?

    Eine unverschlüsselte SQLite-Datei beginnt mit ``SQLite format 3``; bei
    SQLCipher ist auch der Kopf verschlüsselt.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as datei:
        return datei.read(16) != b"SQLite format 3\x00"


def encrypt_database(path: Path, key: str, *, backup_suffix: str = ".unverschluesselt") -> Path:
    """Eine vorhandene Klartext-Datenbank verschlüsseln.

    Die Klartext-Fassung bleibt als Sicherung neben der Datenbank liegen; ihr
    Pfad wird zurückgegeben. Sie sollte nach der Kontrolle gelöscht werden.
    """
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(path)
    if is_encrypted(path):
        raise ValueError(f"{path} ist bereits verschlüsselt.")

    module = sqlcipher_module()
    ziel = path.with_suffix(path.suffix + ".verschluesselt")
    if ziel.exists():
        ziel.unlink()

    connection = module.connect(str(path))
    try:
        connection.execute("ATTACH DATABASE ? AS verschluesselt KEY ?", (str(ziel), key))
        connection.execute("SELECT sqlcipher_export('verschluesselt')")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.execute(f"PRAGMA verschluesselt.user_version = {int(version)}")
        connection.execute("DETACH DATABASE verschluesselt")
    finally:
        connection.close()

    sicherung = path.with_suffix(path.suffix + backup_suffix)
    if sicherung.exists():
        sicherung.unlink()
    shutil.move(str(path), str(sicherung))
    shutil.move(str(ziel), str(path))
    return sicherung
