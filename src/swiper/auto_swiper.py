import asyncio
import random
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from src.platforms.base import DatingPlatform
from src.utils.logger import get_logger

log = get_logger(__name__)
console = Console()


class AutoSwiper:
    def __init__(self, platform: DatingPlatform, cfg: dict):
        self.platform = platform
        self.cfg = cfg
        self.swiper_cfg = cfg.get("swiper", {})
        self.stats = {"likes": 0, "passes": 0, "errors": 0, "matches": 0}

    def _should_like(self) -> bool:
        like_rate = self.swiper_cfg.get("like_rate", 0.65)
        return random.random() < like_rate

    async def _handle_popups(self):
        if not hasattr(self.platform, "browser") or self.platform.browser is None:
            return
        page = self.platform.browser.page
        popup_selectors = [
            '[aria-label="Nicht jetzt"], button:has-text("Nicht jetzt")',
            'button:has-text("Nein danke")',
            '[aria-label="Schließen"], button[aria-label="Close"]',
            '.dialog button:last-child',
        ]
        for selector in popup_selectors:
            try:
                await page.click(selector, timeout=1500)
                await asyncio.sleep(0.5)
            except Exception:
                pass

    async def _check_for_match(self):
        if not hasattr(self.platform, "browser") or self.platform.browser is None:
            if random.random() < 0.05:
                self.stats["matches"] += 1
                log.info("[bold yellow]🎉 MATCH! (simuliert)[/bold yellow]")
            return
        page = self.platform.browser.page
        try:
            match_el = await page.wait_for_selector(
                '[data-testid="match-popup"], .matchPopup, '
                'h2:has-text("It\'s a Match"), h2:has-text("Ein Match")',
                timeout=2000
            )
            if match_el:
                self.stats["matches"] += 1
                log.info("[bold yellow]🎉 MATCH![/bold yellow]")
                # Match-Popup schließen
                await asyncio.sleep(1.5)
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                    await page.click(
                        'button:has-text("Weiter swipen"), button:has-text("Keep Swiping"), '
                        '[data-testid="match-close-button"]',
                        timeout=3000
                    )
                except Exception:
                    pass
        except Exception:
            pass

    async def run(self):
        max_swipes = self.swiper_cfg.get("max_swipes_per_session", 100)
        delay_cfg = self.swiper_cfg.get("delay_between_swipes", {})
        delay_min = delay_cfg.get("min", 1.5)
        delay_max = delay_cfg.get("max", 4.0)
        pause_every = self.swiper_cfg.get("pause_every", 20)
        pause_cfg = self.swiper_cfg.get("pause_duration", {})
        pause_min = pause_cfg.get("min", 30)
        pause_max = pause_cfg.get("max", 90)

        console.rule("[bold blue]Auto-Swiper gestartet[/bold blue]")
        log.info(f"Ziel: {max_swipes} Swipes | Like-Rate: {self.swiper_cfg.get('like_rate', 0.65)*100:.0f}%")

        has_browser = hasattr(self.platform, "browser") and self.platform.browser is not None
        if has_browser:
            page = self.platform.browser.page
            try:
                from src.platforms.tinder import TINDER_APP_URL
                await page.goto(TINDER_APP_URL, wait_until="networkidle")
            except ImportError:
                pass
            await asyncio.sleep(2)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Swipen...", total=max_swipes)

            for i in range(max_swipes):
                # Pause-Check
                if i > 0 and i % pause_every == 0:
                    pause_secs = random.uniform(pause_min, pause_max)
                    log.info(f"[cyan]Pause {pause_secs:.0f}s nach {i} Swipes[/cyan]")
                    await asyncio.sleep(pause_secs)

                # Aktuelle Profil-Info
                try:
                    info = await self.platform.get_current_profile_info()
                    name = info.get("name", "?")
                    age = info.get("age", "?")
                except Exception:
                    name, age = "?", "?"

                # Swipen
                if self._should_like():
                    ok = await self.platform.swipe_right()
                    if ok:
                        self.stats["likes"] += 1
                        action = "[green]LIKE[/green]"
                    else:
                        self.stats["errors"] += 1
                        action = "[red]FEHLER[/red]"
                else:
                    ok = await self.platform.swipe_left()
                    if ok:
                        self.stats["passes"] += 1
                        action = "[red]PASS[/red]"
                    else:
                        self.stats["errors"] += 1
                        action = "[red]FEHLER[/red]"

                progress.update(task, advance=1, description=f"{action} {name} ({age})")

                # Match-Popup & andere Popups
                await self._check_for_match()
                await self._handle_popups()

                # Zufällige Pause
                delay = random.uniform(delay_min, delay_max)
                await asyncio.sleep(delay)

                if self.stats["errors"] > 5:
                    log.warning("Zu viele Fehler - überprüfe ob Browser noch auf Tinder ist")
                    await self._handle_popups()
                    await asyncio.sleep(3)

        self._print_stats()

    def _print_stats(self):
        table = Table(title="Swipe-Session Ergebnisse", show_header=True)
        table.add_column("Aktion", style="cyan")
        table.add_column("Anzahl", justify="right")

        table.add_row("Likes 👍", str(self.stats["likes"]))
        table.add_row("Passes 👎", str(self.stats["passes"]))
        table.add_row("Matches 🎉", str(self.stats["matches"]))
        table.add_row("Fehler ⚠️", str(self.stats["errors"]))
        table.add_row(
            "Gesamt",
            str(self.stats["likes"] + self.stats["passes"])
        )

        console.print(table)
        like_rate_actual = (
            self.stats["likes"] / max(1, self.stats["likes"] + self.stats["passes"]) * 100
        )
        console.print(f"[bold]Tatsächliche Like-Rate: {like_rate_actual:.1f}%[/bold]")
