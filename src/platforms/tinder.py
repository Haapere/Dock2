import asyncio
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from src.platforms.base import DatingPlatform, Profile, Match
from src.utils.browser import BrowserManager
from src.utils.logger import get_logger

log = get_logger(__name__)

TINDER_URL = "https://tinder.com"
TINDER_APP_URL = "https://tinder.com/app/recs"


class TinderPlatform(DatingPlatform):
    def __init__(self, browser: BrowserManager, cfg: dict):
        self.browser = browser
        self.cfg = cfg
        self.page: Page = None

    async def _get_page(self) -> Page:
        if self.page is None:
            self.page = self.browser.page
        return self.page

    # -------------------------------------------------------------------------
    # Login
    # -------------------------------------------------------------------------

    async def login(self) -> bool:
        page = await self._get_page()
        log.info("Öffne Tinder...")
        await page.goto(TINDER_URL, wait_until="networkidle")
        await self.browser.random_delay(2, 4)

        # Cookies akzeptieren
        try:
            await page.click("text=Ich stimme zu", timeout=5000)
            await self.browser.random_delay()
        except Exception:
            pass

        try:
            await page.click('[aria-label="Cookies akzeptieren"]', timeout=3000)
            await self.browser.random_delay()
        except Exception:
            pass

        # Prüfen ob schon eingeloggt
        if await self._is_logged_in():
            log.info("[green]Bereits eingeloggt (Session geladen)[/green]")
            return True

        # Login starten
        log.info("Klicke auf 'Anmelden'...")
        try:
            await self.browser.human_click("text=Anmelden", timeout=10000)
            await self.browser.random_delay(1, 2)
        except Exception:
            try:
                await self.browser.human_click("text=Einloggen", timeout=5000)
                await self.browser.random_delay(1, 2)
            except Exception:
                pass

        # Phone-Login
        try:
            await self.browser.human_click("text=Mit Handynummer anmelden", timeout=8000)
            await self.browser.random_delay()
        except Exception:
            pass

        log.info("[yellow]Bitte manuell einloggen. Drücke Enter wenn fertig...[/yellow]")
        input()

        if await self._is_logged_in():
            await self.browser.save_session()
            log.info("[green]Login erfolgreich![/green]")
            return True

        log.error("Login fehlgeschlagen")
        return False

    async def _is_logged_in(self) -> bool:
        page = await self._get_page()
        try:
            await page.wait_for_selector(
                '[data-testid="rec-card"], .recsCard, [aria-label="Gefällt mir"]',
                timeout=5000
            )
            return True
        except Exception:
            return "tinder.com/app" in page.url

    # -------------------------------------------------------------------------
    # Profil
    # -------------------------------------------------------------------------

    async def setup_profile(self, profile: Profile) -> bool:
        page = await self._get_page()
        log.info("Öffne Profil-Einstellungen...")

        await page.goto(f"{TINDER_URL}/app/profile", wait_until="networkidle")
        await self.browser.random_delay(2, 3)

        # Bio bearbeiten
        if profile.bio:
            try:
                bio_field = await page.wait_for_selector(
                    'textarea[placeholder*="ich"], textarea[name="bio"], [data-testid="bio-input"]',
                    timeout=8000
                )
                await bio_field.click()
                await page.keyboard.select_all()
                await page.keyboard.type(profile.bio, delay=random.uniform(20, 80))
                log.info("Bio gesetzt")
                await self.browser.random_delay()
            except Exception as e:
                log.warning(f"Bio konnte nicht gesetzt werden: {e}")

        # Fotos hochladen
        for i, photo_path in enumerate(profile.photos):
            path = Path(photo_path)
            if not path.exists():
                log.warning(f"Foto nicht gefunden: {photo_path}")
                continue
            try:
                file_input = await page.wait_for_selector(
                    'input[type="file"]', timeout=5000
                )
                await file_input.set_input_files(str(path))
                log.info(f"Foto {i+1} hochgeladen: {path.name}")
                await self.browser.random_delay(2, 4)
            except Exception as e:
                log.warning(f"Foto-Upload fehlgeschlagen: {e}")

        # Altersbereich & Entfernung aus extra-Config
        extra = profile.extra
        if "min_age" in extra or "max_age" in extra:
            try:
                await page.goto(f"{TINDER_URL}/app/settings", wait_until="networkidle")
                await self.browser.random_delay(1, 2)
                log.info("Präferenzen geöffnet")
            except Exception as e:
                log.warning(f"Settings konnten nicht geöffnet werden: {e}")

        # Speichern
        try:
            await self.browser.human_click('[aria-label="Speichern"], button:has-text("Speichern")', timeout=5000)
            log.info("[green]Profil gespeichert[/green]")
        except Exception:
            pass

        return True

    # -------------------------------------------------------------------------
    # Swipen
    # -------------------------------------------------------------------------

    async def get_current_profile_info(self) -> dict:
        page = await self._get_page()
        info = {"name": "Unbekannt", "age": None, "bio": ""}
        try:
            name_el = await page.query_selector(
                '[data-testid="name"], .Ov\\(h\\), h1[itemprop="name"]'
            )
            if name_el:
                text = await name_el.inner_text()
                parts = text.strip().split()
                info["name"] = parts[0] if parts else "?"
                if len(parts) > 1 and parts[-1].isdigit():
                    info["age"] = int(parts[-1])
        except Exception:
            pass

        try:
            bio_el = await page.query_selector('[data-testid="bio"], .bio, [itemprop="description"]')
            if bio_el:
                info["bio"] = (await bio_el.inner_text()).strip()
        except Exception:
            pass

        return info

    async def swipe_right(self) -> bool:
        page = await self._get_page()
        try:
            # Tastenkürzel: L = Like
            await page.keyboard.press("l")
            await self.browser.random_delay(0.3, 0.8)
            return True
        except Exception:
            pass
        try:
            await self.browser.human_click(
                '[aria-label="Gefällt mir"], [aria-label="Like"], '
                '[data-testid="swipe-like"], button.like-button',
                timeout=5000
            )
            return True
        except Exception as e:
            log.error(f"Swipe Right fehlgeschlagen: {e}")
            return False

    async def swipe_left(self) -> bool:
        page = await self._get_page()
        try:
            # Tastenkürzel: N = Nope
            await page.keyboard.press("n")
            await self.browser.random_delay(0.3, 0.8)
            return True
        except Exception:
            pass
        try:
            await self.browser.human_click(
                '[aria-label="Nein danke"], [aria-label="Nope"], '
                '[data-testid="swipe-nope"], button.nope-button',
                timeout=5000
            )
            return True
        except Exception as e:
            log.error(f"Swipe Left fehlgeschlagen: {e}")
            return False

    # -------------------------------------------------------------------------
    # Matches & Chat
    # -------------------------------------------------------------------------

    async def get_matches(self) -> list[Match]:
        page = await self._get_page()
        matches = []

        try:
            await page.goto(f"{TINDER_URL}/app/matches", wait_until="networkidle")
            await self.browser.random_delay(2, 3)

            match_elements = await page.query_selector_all(
                '[data-testid="match-list-item"], .matchListItem, [href*="/messages/"]'
            )

            for el in match_elements[:20]:
                try:
                    link = await el.get_attribute("href") or ""
                    match_id = link.split("/")[-1] if link else ""

                    name_el = await el.query_selector(
                        '[data-testid="match-name"], .match-name, h3, strong'
                    )
                    name = (await name_el.inner_text()).strip() if name_el else "?"

                    msg_el = await el.query_selector('.last-message, [data-testid="last-message"]')
                    last_msg = (await msg_el.inner_text()).strip() if msg_el else None

                    if match_id:
                        matches.append(Match(
                            match_id=match_id,
                            name=name,
                            last_message=last_msg
                        ))
                except Exception:
                    continue

        except Exception as e:
            log.error(f"Matches laden fehlgeschlagen: {e}")

        return matches

    async def get_messages(self, match_id: str) -> list[dict]:
        page = await self._get_page()
        messages = []
        try:
            await page.goto(
                f"{TINDER_URL}/app/messages/{match_id}",
                wait_until="networkidle"
            )
            await self.browser.random_delay(1, 2)

            msg_elements = await page.query_selector_all(
                '[data-testid="message-bubble"], .message, .messageText'
            )
            for el in msg_elements:
                text = (await el.inner_text()).strip()
                parent = await el.evaluate("el => el.closest('[class*=\"sent\"]') ? 'sent' : 'received'")
                if text:
                    messages.append({
                        "role": "assistant" if parent == "sent" else "user",
                        "content": text
                    })
        except Exception as e:
            log.error(f"Nachrichten laden fehlgeschlagen: {e}")

        return messages

    async def send_message(self, match_id: str, text: str) -> bool:
        page = await self._get_page()
        try:
            current_url = page.url
            if match_id not in current_url:
                await page.goto(
                    f"{TINDER_URL}/app/messages/{match_id}",
                    wait_until="networkidle"
                )
                await self.browser.random_delay(1, 2)

            input_el = await page.wait_for_selector(
                '[data-testid="chat-text-field"], textarea[placeholder*="Nachricht"], '
                '.textareaShell textarea',
                timeout=8000
            )
            await input_el.click()
            await asyncio.sleep(random.uniform(0.3, 0.7))

            # Text human-like tippen
            for char in text:
                await page.keyboard.type(char, delay=random.uniform(30, 110))

            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.keyboard.press("Enter")
            log.info(f"[green]Nachricht gesendet an {match_id}: {text[:50]}...[/green]")
            return True
        except Exception as e:
            log.error(f"Senden fehlgeschlagen: {e}")
            return False
