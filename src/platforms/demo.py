"""Demo-Platform: simuliert Tinder-Flow ohne echten Browser."""
import asyncio
import random
from src.platforms.base import DatingPlatform, Profile, Match
from src.utils.logger import get_logger

log = get_logger(__name__)

FAKE_PROFILES = [
    {"name": "Anna",   "age": 26, "bio": "Yoga-Fan & Kaffeejunkie ☕ Suche jemanden der gerne wandert."},
    {"name": "Laura",  "age": 24, "bio": "Tierärztin in Ausbildung. Mein Hund sucht auch einen Freund."},
    {"name": "Sophie", "age": 29, "bio": "Architektin. Reise lieber als Urlaub zu planen 🌍"},
    {"name": "Mia",    "age": 27, "bio": "Bookworm & Hobbyköchin. Wein > Bier."},
    {"name": "Julia",  "age": 23, "bio": "Studentin (Psychologie). Frage mich nicht warum 😄"},
    {"name": "Emma",   "age": 31, "bio": "Marketing-Managerin. Liebe gute Gespräche und schlechte Witze."},
    {"name": "Lena",   "age": 25, "bio": "Fotografin. Zeige dir Berlin von der anderen Seite."},
    {"name": "Hannah", "age": 28, "bio": "Ärztin. Suche jemanden der mich zum Lachen bringt."},
]

FAKE_MATCHES = [
    Match("m001", "Anna",   26, "Yoga-Fan & Kaffeejunkie",   last_message=None,       conversation=[]),
    Match("m002", "Laura",  24, "Tierärztin in Ausbildung",  last_message="Hey! 😊",  conversation=[
        {"role": "user", "content": "Hey! 😊"},
    ]),
    Match("m003", "Sophie", 29, "Architektin",               last_message="Haha genau!", conversation=[
        {"role": "assistant", "content": "Hey Sophie, Architektur und Reisen – perfekte Kombi! Welches Gebäude hat dich zuletzt wirklich beeindruckt?"},
        {"role": "user",      "content": "Haha genau!"},
        {"role": "user",      "content": "Das Museo Guggenheim in Bilbao hat mich komplett umgehauen 😍"},
    ]),
]


class DemoPlatform(DatingPlatform):
    """Simuliert eine Dating-Plattform für Tests ohne Browser."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._profile_idx = 0
        self._messages: dict[str, list[dict]] = {
            m.match_id: list(m.conversation) for m in FAKE_MATCHES
        }

    async def login(self) -> bool:
        log.info("[cyan][DEMO] Login simuliert[/cyan]")
        await asyncio.sleep(0.5)
        return True

    async def setup_profile(self, profile: Profile) -> bool:
        log.info(f"[cyan][DEMO] Profil gesetzt: {profile.name}, Bio: {profile.bio[:40]}...[/cyan]")
        await asyncio.sleep(0.3)
        return True

    async def get_current_profile_info(self) -> dict:
        p = FAKE_PROFILES[self._profile_idx % len(FAKE_PROFILES)]
        self._profile_idx += 1
        return dict(p)

    async def swipe_right(self) -> bool:
        await asyncio.sleep(0.1)
        return True

    async def swipe_left(self) -> bool:
        await asyncio.sleep(0.1)
        return True

    async def get_matches(self) -> list[Match]:
        await asyncio.sleep(0.3)
        return FAKE_MATCHES

    async def get_messages(self, match_id: str) -> list[dict]:
        await asyncio.sleep(0.1)
        return list(self._messages.get(match_id, []))

    async def send_message(self, match_id: str, text: str) -> bool:
        self._messages.setdefault(match_id, []).append(
            {"role": "assistant", "content": text}
        )
        log.info(f"[cyan][DEMO] Nachricht an {match_id}: {text[:60]}[/cyan]")
        await asyncio.sleep(0.2)
        return True
