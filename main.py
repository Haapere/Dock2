#!/usr/bin/env python3
"""Dating App Automation - Profil | Swipen | Chat"""

import asyncio
import sys
import click
from rich.console import Console

from src.utils.config import load_config
from src.utils.browser import BrowserManager
from src.utils.logger import get_logger

console = Console()
log = get_logger(__name__)


def get_platform(cfg: dict, browser: BrowserManager):
    platform_name = cfg.get("platform", "tinder").lower()
    if platform_name == "tinder":
        from src.platforms.tinder import TinderPlatform
        return TinderPlatform(browser, cfg)
    elif platform_name == "bumble":
        from src.platforms.bumble import BumblePlatform
        return BumblePlatform(browser, cfg)
    else:
        raise ValueError(f"Unbekannte Plattform: {platform_name}. Verwende 'tinder' oder 'bumble'.")


async def _login_and_run(cfg: dict, action_fn):
    browser = BrowserManager(cfg)
    try:
        await browser.start()
        platform = get_platform(cfg, browser)

        logged_in = await platform.login()
        if not logged_in:
            log.error("[red]Login fehlgeschlagen - Abbruch[/red]")
            sys.exit(1)

        await action_fn(platform)
    finally:
        await browser.close()


# ---------------------------------------------------------------------------
# CLI Befehle
# ---------------------------------------------------------------------------

@click.group()
@click.option("--config", "-c", default="config.yaml", help="Pfad zur config.yaml")
@click.pass_context
def cli(ctx, config):
    """Dating App Automation - Profil | Swipen | Chat"""
    ctx.ensure_object(dict)
    try:
        ctx.obj["cfg"] = load_config(config)
    except FileNotFoundError as e:
        console.print(f"[red]Fehler: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def profil(ctx):
    """Profil erstellen oder aktualisieren."""
    cfg = ctx.obj["cfg"]

    async def run(platform):
        from src.profile.creator import ProfileCreator
        creator = ProfileCreator(platform, cfg)
        await creator.run()

    asyncio.run(_login_and_run(cfg, run))


@cli.command()
@click.option("--anzahl", "-n", default=None, type=int, help="Anzahl Swipes (überschreibt config)")
@click.pass_context
def swipen(ctx, anzahl):
    """Automatisch swipen (liken/passen)."""
    cfg = ctx.obj["cfg"]
    if anzahl:
        cfg.setdefault("swiper", {})["max_swipes_per_session"] = anzahl

    async def run(platform):
        from src.swiper.auto_swiper import AutoSwiper
        swiper = AutoSwiper(platform, cfg)
        await swiper.run()

    asyncio.run(_login_and_run(cfg, run))


@cli.command()
@click.option("--einmalig", is_flag=True, help="Nur einmal prüfen, kein Loop")
@click.pass_context
def chat(ctx, einmalig):
    """KI-gestützte Chat-Automatisierung für Matches."""
    cfg = ctx.obj["cfg"]

    if not cfg.get("anthropic_api_key"):
        console.print("[red]Fehler: ANTHROPIC_API_KEY fehlt in config.yaml oder .env[/red]")
        sys.exit(1)

    async def run(platform):
        from src.chat.bot import ChatBot
        bot = ChatBot(platform, cfg)
        if einmalig:
            await bot.run_once()
        else:
            await bot.run_loop()

    asyncio.run(_login_and_run(cfg, run))


@cli.command()
@click.option("--anzahl", "-n", default=50, type=int, help="Anzahl Swipes")
@click.pass_context
def komplett(ctx, anzahl):
    """Alles in einem: Profil → Swipen → Chat."""
    cfg = ctx.obj["cfg"]
    cfg.setdefault("swiper", {})["max_swipes_per_session"] = anzahl

    if not cfg.get("anthropic_api_key"):
        console.print("[yellow]Warnung: Kein API-Key - Chat wird übersprungen[/yellow]")

    async def run(platform):
        from src.profile.creator import ProfileCreator
        from src.swiper.auto_swiper import AutoSwiper
        from src.chat.bot import ChatBot

        console.rule("[bold]1. Profil[/bold]")
        creator = ProfileCreator(platform, cfg)
        await creator.run()

        console.rule("[bold]2. Swipen[/bold]")
        swiper = AutoSwiper(platform, cfg)
        await swiper.run()

        if cfg.get("anthropic_api_key"):
            console.rule("[bold]3. Chat[/bold]")
            bot = ChatBot(platform, cfg)
            await bot.run_once()

    asyncio.run(_login_and_run(cfg, run))


@cli.command()
@click.pass_context
def status(ctx):
    """Aktuelle Matches und Stats anzeigen."""
    cfg = ctx.obj["cfg"]

    async def run(platform):
        from src.chat.bot import ChatBot
        bot = ChatBot(platform, cfg)
        await bot.run_once()

    asyncio.run(_login_and_run(cfg, run))


if __name__ == "__main__":
    cli(obj={})
