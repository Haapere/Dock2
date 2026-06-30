import json
import random
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from src.utils.logger import get_logger

log = get_logger(__name__)


class BrowserManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.session_file = Path(cfg.get("session_file", "sessions/session.json"))

    async def start(self) -> Page:
        self.playwright = await async_playwright().start()
        import os
        launch_kwargs: dict = {
            "headless": self.cfg.get("headless", False),
            "slow_mo": self.cfg.get("slow_mo", 50),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        # Systemchromium bevorzugen falls vorhanden
        if os.path.exists("/opt/pw-browsers/chromium"):
            launch_kwargs["executable_path"] = "/opt/pw-browsers/chromium"

        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        storage_state = None
        if self.session_file.exists():
            log.info(f"Lade gespeicherte Session: {self.session_file}")
            storage_state = str(self.session_file)

        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            storage_state=storage_state,
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )

        # Anti-Erkennung: navigator.webdriver entfernen
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
        """)

        self.page = await self.context.new_page()
        return self.page

    async def save_session(self):
        if self.context:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(self.session_file))
            log.info(f"Session gespeichert: {self.session_file}")

    async def random_delay(self, min_s: float = 1.0, max_s: float = 3.0):
        delay = random.uniform(min_s, max_s)
        await asyncio.sleep(delay)

    async def human_click(self, selector: str, timeout: int = 10000):
        element = await self.page.wait_for_selector(selector, timeout=timeout)
        box = await element.bounding_box()
        if box:
            x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            await self.page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.05, 0.2))
            await self.page.mouse.click(x, y)
        else:
            await element.click()

    async def human_type(self, selector: str, text: str):
        await self.human_click(selector)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        for char in text:
            await self.page.keyboard.type(char, delay=random.uniform(30, 120))

    async def close(self):
        await self.save_session()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
