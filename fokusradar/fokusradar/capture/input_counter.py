"""Zählung der Eingabe-Ereignisse (nur Anzahl, keine Inhalte).

Gespeichert wird ausschließlich, *wie oft* Maus und Tastatur betätigt wurden —
nicht *was* getippt wurde. Es gibt bewusst keinen Zugriff auf Tastencodes,
Zeichen oder Zwischenablage. Das Ganze ist optional: fehlt ``pynput``, bleibt
die Spalte ``input_events_count`` leer.
"""

from __future__ import annotations


class InputCounter:
    """Zählt Tastendrücke und Mausklicks seit dem letzten Auslesen."""

    name = "pynput"

    def __init__(self) -> None:
        self._count = 0
        self._listeners: list[object] = []
        self._reason: str | None = None
        self._started = False

    def available(self) -> bool:
        try:
            import pynput  # noqa: F401
        except Exception as exc:  # pragma: no cover - hängt an der Installation
            self._reason = f"pynput nicht nutzbar: {exc}"
            return False
        return True

    def unavailable_reason(self) -> str | None:
        return self._reason

    def start(self) -> bool:
        """Listener starten. Gibt zurück, ob die Zählung wirklich läuft."""
        if self._started:
            return True
        try:  # pragma: no cover - benötigt eine echte Eingabe-Umgebung
            from pynput import keyboard, mouse

            keyboard_listener = keyboard.Listener(on_press=self._bump)
            mouse_listener = mouse.Listener(on_click=self._bump_click)
            keyboard_listener.daemon = True
            mouse_listener.daemon = True
            keyboard_listener.start()
            mouse_listener.start()
            self._listeners = [keyboard_listener, mouse_listener]
            self._started = True
            return True
        except Exception as exc:  # pragma: no cover
            self._reason = f"Eingabe-Zählung konnte nicht starten: {exc}"
            return False

    def stop(self) -> None:
        for listener in self._listeners:
            try:  # pragma: no cover - Aufräumen darf nie den Agenten stoppen
                listener.stop()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._listeners = []
        self._started = False

    def _bump(self, *_args: object) -> None:
        # Das Argument (die gedrückte Taste) wird bewusst ignoriert.
        self._count += 1

    def _bump_click(self, *args: object) -> None:
        # pynput meldet Drücken und Loslassen; nur das Drücken zählt.
        pressed = args[3] if len(args) > 3 else True
        if pressed:
            self._count += 1

    def take(self) -> int:
        """Zählerstand zurückgeben und auf 0 zurücksetzen."""
        count, self._count = self._count, 0
        return count


class NullInputCounter:
    """Attrappe, wenn keine Eingabe-Zählung gewünscht oder möglich ist."""

    name = "keine"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def available(self) -> bool:
        return False

    def unavailable_reason(self) -> str | None:
        return self._reason

    def start(self) -> bool:
        return False

    def stop(self) -> None:
        return None

    def take(self) -> int | None:
        return None


def create_input_counter(setting: bool | str = "auto"):
    """Zähler gemäß Konfiguration erzeugen (``True``/``False``/``"auto"``)."""
    if setting is False:
        return NullInputCounter("in der Konfiguration abgeschaltet")
    counter = InputCounter()
    if counter.available():
        return counter
    reason = counter.unavailable_reason() or "pynput nicht installiert"
    if setting is True:
        reason += " (in der Konfiguration verlangt)"
    return NullInputCounter(reason)
