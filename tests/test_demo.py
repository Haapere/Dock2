"""Vollständiger Integrationstest im Demo-Modus."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.platforms.demo import DemoPlatform, FAKE_MATCHES
from src.profile.creator import ProfileCreator
from src.swiper.auto_swiper import AutoSwiper
from src.chat.bot import ChatBot
from unittest.mock import AsyncMock, patch


CFG = {
    "platform": "demo",
    "anthropic_api_key": "test-key",
    "profile": {
        "name": "Max",
        "age": 28,
        "bio": "Humorvoll und abenteuerlustig.",
        "photos": [],
        "tinder": {},
    },
    "swiper": {
        "like_rate": 0.7,
        "max_swipes_per_session": 8,
        "delay_between_swipes": {"min": 0.01, "max": 0.02},
        "pause_every": 100,
        "pause_duration": {"min": 0, "max": 0},
    },
    "chat": {
        "ai_model": "claude-haiku-4-5-20251001",
        "check_interval": 60,
        "max_messages_per_match": 10,
        "opener_style": "witty",
        "language": "de",
        "persona": "Du bist Max.",
    },
}


async def test_profil():
    print("\n--- TEST: Profil erstellen ---")
    platform = DemoPlatform(CFG)
    creator = ProfileCreator(platform, CFG)
    ok = await creator.run()
    assert ok, "Profil-Erstellung fehlgeschlagen"
    print("PASS Profil erfolgreich erstellt")


async def test_swipen():
    print("\n--- TEST: Auto-Swipen ---")
    platform = DemoPlatform(CFG)
    swiper = AutoSwiper(platform, CFG)
    await swiper.run()
    total = swiper.stats["likes"] + swiper.stats["passes"]
    assert total == 8, f"Erwartet 8 Swipes, got {total}"
    assert swiper.stats["errors"] == 0, "Keine Fehler erwartet"
    print(f"PASS {swiper.stats['likes']} Likes, {swiper.stats['passes']} Passes, {swiper.stats['matches']} Matches")


async def test_chat_mock():
    print("\n--- TEST: Chat mit Mock-KI ---")
    platform = DemoPlatform(CFG)
    bot = ChatBot(platform, CFG)

    # KI-Aufruf mocken
    fake_responses = [
        "Hey Anna! Kaffee oder Yoga – was kommt bei dir zuerst? ☕🧘",
        "Interessant! Ich finde Yoga auch gut zum Abschalten. Hast du einen Lieblings-Stil?",
        "Gute Wahl! Laura, dein Hund und ich – wir sollten uns kennenlernen 😄",
    ]
    response_iter = iter(fake_responses)

    async def mock_generate(match, conversation, is_opener=False):
        return next(response_iter, "Lass uns einen Kaffee trinken! ☕")

    bot._generate_response = mock_generate

    count = await bot.run_once()
    assert count == 3, f"Erwartet 3 Matches, got {count}"

    # Prüfen ob Nachrichten gesendet wurden
    anna_msgs = platform._messages.get("m001", [])
    assert len(anna_msgs) == 1, f"Anna sollte 1 Nachricht haben, hat {len(anna_msgs)}"
    assert "Anna" in anna_msgs[0]["content"] or "Kaffee" in anna_msgs[0]["content"]

    # Sophie hatte schon 2 Nachrichten vom anderen, also Antwort erwartet
    sophie_msgs = platform._messages.get("m003", [])
    assert len(sophie_msgs) > 3, f"Sophie sollte mehr als 3 Nachrichten haben"

    print(f"PASS {count} Matches bearbeitet")
    print(f"     Anna: '{anna_msgs[0]['content'][:50]}'")
    print(f"     Sophie: Antwort auf '{FAKE_MATCHES[2].conversation[-1]['content'][:30]}'")


async def test_komplett():
    print("\n--- TEST: Komplett-Flow ---")
    platform = DemoPlatform(CFG)

    # 1. Profil
    creator = ProfileCreator(platform, CFG)
    assert await creator.run()

    # 2. Swipen
    swiper = AutoSwiper(platform, CFG)
    await swiper.run()
    assert swiper.stats["errors"] == 0

    # 3. Chat (mit Mock)
    bot = ChatBot(platform, CFG)
    bot._generate_response = AsyncMock(return_value="Hast du Lust auf einen Kaffee? ☕")
    count = await bot.run_once()
    assert count > 0

    print(f"PASS Komplett-Flow: Profil OK → {swiper.stats['likes']}L/{swiper.stats['passes']}P → {count} Matches gechattet")


async def main():
    print("=" * 60)
    print("Dating App Automation — Demo-Tests")
    print("=" * 60)

    tests = [test_profil, test_swipen, test_chat_mock, test_komplett]
    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"FAIL {test.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Ergebnis: {passed} bestanden, {failed} fehlgeschlagen")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
