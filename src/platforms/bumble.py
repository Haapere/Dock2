import asyncio
import random
from pathlib import Path

from playwright.async_api import Page

from src.platforms.base import DatingPlatform, Profile, Match
from src.utils.browser import BrowserManager
from src.utils.logger import get_logger

log = get_logger(__name__)

BUMBLE_URL = "https://bumble.com"
BUMBLE_APP_URL = "https://bumble.com/app"


class BumblePlatform(DatingPlatform):
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
        log.info("Öffne Bumble...")
        await page.goto(BUMBLE_URL, wait_until="networkidle")
        await self.browser.random_delay(2, 4)

        # Cookie-Banner
        try:
            await page.click('button:has-text("Accept"), button:has-text("Akzeptieren")', timeout=5000)
            await self.browser.random_delay()
        except Exception:
            pass

        if await self._is_logged_in():
            log.info("[green]Bereits eingeloggt[/green]")
            return True

        try:
            await self.browser.human_click(
                'a:has-text("Sign In"), a:has-text("Anmelden"), button:has-text("Log in")',
                timeout=10000
            )
            await self.browser.random_delay(1, 2)
        except Exception:
            pass

        log.info("[yellow]Browser ist offen. Bitte einloggen, dann Enter drücken...[/yellow]")
        input("  → Fertig? Enter drücken: ")

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
                '.encounters-action, [data-qa-role="encounters-controls"], .scroll-area',
                timeout=5000
            )
            return True
        except Exception:
            return "bumble.com/app" in page.url

    # -------------------------------------------------------------------------
    # Profil
    # -------------------------------------------------------------------------

    async def setup_profile(self, profile: Profile) -> bool:
        page = await self._get_page()
        log.info("Öffne Bumble Profil...")

        await page.goto(f"{BUMBLE_URL}/profile", wait_until="networkidle")
        await self.browser.random_delay(2, 3)

        if profile.bio:
            try:
                bio_field = await page.wait_for_selector(
                    'textarea[placeholder*="dir"], textarea[name="bio"], .about-me textarea',
                    timeout=8000
                )
                await bio_field.click()
                await page.keyboard.select_all()
                await page.keyboard.type(profile.bio, delay=random.uniform(25, 80))
                log.info("Bio gesetzt")
                await self.browser.random_delay()
            except Exception as e:
                log.warning(f"Bio konnte nicht gesetzt werden: {e}")

        for i, photo_path in enumerate(profile.photos):
            path = Path(photo_path)
            if not path.exists():
                log.warning(f"Foto nicht gefunden: {photo_path}")
                continue
            try:
                file_input = await page.wait_for_selector('input[type="file"]', timeout=5000)
                await file_input.set_input_files(str(path))
                log.info(f"Foto {i+1} hochgeladen")
                await self.browser.random_delay(2, 4)
            except Exception as e:
                log.warning(f"Foto-Upload fehlgeschlagen: {e}")

        try:
            await self.browser.human_click('button:has-text("Speichern"), button:has-text("Save")', timeout=5000)
            log.info("[green]Bumble-Profil gespeichert[/green]")
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
                '.encounters-story-profile__name, [data-qa-role="profile-name"], h1.person__name'
            )
            if name_el:
                text = await name_el.inner_text()
                parts = text.strip().split(",")
                info["name"] = parts[0].strip()
                if len(parts) > 1:
                    try:
                        info["age"] = int(parts[1].strip())
                    except ValueError:
                        pass
        except Exception:
            pass

        try:
            bio_el = await page.query_selector('.encounters-story-about, .person__bio')
            if bio_el:
                info["bio"] = (await bio_el.inner_text()).strip()
        except Exception:
            pass

        return info

    async def swipe_right(self) -> bool:
        page = await self._get_page()
        try:
            await self.browser.human_click(
                '[data-qa-role="encounters-action-like"], .encounters-action--like, '
                'button[aria-label*="Like"]',
                timeout=5000
            )
            return True
        except Exception as e:
            log.error(f"Swipe Right fehlgeschlagen: {e}")
            return False

    async def swipe_left(self) -> bool:
        page = await self._get_page()
        try:
            await self.browser.human_click(
                '[data-qa-role="encounters-action-dislike"], .encounters-action--dislike, '
                'button[aria-label*="Pass"]',
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
            await page.goto(f"{BUMBLE_URL}/app", wait_until="networkidle")
            await self.browser.random_delay(1, 2)

            # Matches-Tab
            try:
                await page.click('[data-qa-role="connections-tab"], .messenger-tab', timeout=5000)
                await self.browser.random_delay()
            except Exception:
                pass

            items = await page.query_selector_all(
                '.conversations-list-item, [data-qa-role="connection-card"]'
            )
            for el in items[:20]:
                try:
                    link = await el.get_attribute("href") or ""
                    match_id = link.split("/")[-1] if "/" in link else ""

                    name_el = await el.query_selector('.connection-name, strong, h3')
                    name = (await name_el.inner_text()).strip() if name_el else "?"

                    msg_el = await el.query_selector('.conversation-preview, .last-message')
                    last_msg = (await msg_el.inner_text()).strip() if msg_el else None

                    if name != "?":
                        matches.append(Match(
                            match_id=match_id or name,
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
                f"{BUMBLE_URL}/app/connections/{match_id}",
                wait_until="networkidle"
            )
            await self.browser.random_delay(1, 2)

            msg_elements = await page.query_selector_all('.message, .chat-message')
            for el in msg_elements:
                text = (await el.inner_text()).strip()
                is_mine = await el.evaluate("el => el.classList.contains('is-mine')")
                if text:
                    messages.append({
                        "role": "assistant" if is_mine else "user",
                        "content": text
                    })
        except Exception as e:
            log.error(f"Nachrichten laden: {e}")

        return messages

    async def send_message(self, match_id: str, text: str) -> bool:
        page = await self._get_page()
        try:
            current_url = page.url
            if match_id not in current_url:
                await page.goto(
                    f"{BUMBLE_URL}/app/connections/{match_id}",
                    wait_until="networkidle"
                )
                await self.browser.random_delay(1, 2)

            input_el = await page.wait_for_selector(
                '.message-input textarea, [data-qa-role="message-input"], textarea.chat-input',
                timeout=8000
            )
            await input_el.click()
            await asyncio.sleep(random.uniform(0.3, 0.7))

            for char in text:
                await page.keyboard.type(char, delay=random.uniform(30, 110))

            await asyncio.sleep(random.uniform(0.5, 1.0))
            await page.keyboard.press("Enter")
            log.info(f"[green]Nachricht gesendet: {text[:50]}[/green]")
            return True
        except Exception as e:
            log.error(f"Senden fehlgeschlagen: {e}")
            return False
