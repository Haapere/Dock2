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


def get_platform(cfg: dict, browser: BrowserManager | None = None):
    platform_name = cfg.get("platform", "tinder").lower()
    if platform_name == "demo":
        from src.platforms.demo import DemoPlatform
        return DemoPlatform(cfg)
    elif platform_name == "tinder":
        from src.platforms.tinder import TinderPlatform
        return TinderPlatform(browser, cfg)
    elif platform_name == "bumble":
        from src.platforms.bumble import BumblePlatform
        return BumblePlatform(browser, cfg)
    else:
        raise ValueError(f"Unbekannte Plattform: {platform_name}. Verwende 'tinder', 'bumble' oder 'demo'.")


async def _login_and_run(cfg: dict, action_fn):
    is_demo = cfg.get("platform", "").lower() == "demo"

    if is_demo:
        platform = get_platform(cfg)
        await platform.login()
        await action_fn(platform)
        return

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


@cli.command()
@click.pass_context
def login(ctx):
    """Nur einloggen und Session speichern (für spätere Läufe)."""
    cfg = ctx.obj["cfg"]

    async def run(platform):
        log.info("[green]Login erfolgreich — Session gespeichert.[/green]")
        log.info("Du kannst jetzt 'python main.py swipen' oder 'chat' starten.")

    asyncio.run(_login_and_run(cfg, run))


@cli.command("session-import")
@click.argument("session_file_arg", metavar="FILE", default="-")
@click.pass_context
def session_import(ctx, session_file_arg):
    """Session aus Chrome exportieren und importieren.

    FILE: Pfad zur JSON-Datei oder '-' für stdin (Standard).

    Exportiere die Session in Chrome DevTools Console mit:
        copy(JSON.stringify({
          cookies: document.cookie.split(';').map(c => {
            const [n, ...v] = c.trim().split('=');
            return {name: n, value: v.join('='), domain: '.tinder.com', path: '/'};
          }),
          localStorage: Object.fromEntries(Object.entries(localStorage))
        }))
    """
    import json
    from pathlib import Path

    cfg = ctx.obj["cfg"]

    if session_file_arg == "-":
        console.print("[cyan]Paste den JSON-Output aus Chrome DevTools, dann Strg+D:[/cyan]")
        raw_text = sys.stdin.read().strip()
    else:
        src = Path(session_file_arg)
        if not src.exists():
            console.print(f"[red]Datei nicht gefunden: {session_file_arg}[/red]")
            sys.exit(1)
        raw_text = src.read_text()

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        console.print(f"[red]Ungültiges JSON: {e}[/red]")
        sys.exit(1)

    storage = _build_storage_state(raw)

    dest = Path(cfg.get("session_file", "sessions/session.json"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        json.dump(storage, f, indent=2)

    n_cookies = len(storage.get("cookies", []))
    n_origins = sum(
        len(o.get("localStorage", [])) for o in storage.get("origins", [])
    )
    console.print(f"[green]Session importiert → {dest}[/green]")
    console.print(f"  {n_cookies} Cookies, {n_origins} localStorage-Einträge")
    console.print("Starte jetzt: [bold]python main.py swipen[/bold]")


def _build_storage_state(raw: dict | list) -> dict:
    """Konvertiert verschiedene Export-Formate in Playwright storage_state."""
    # Bereits Playwright-Format
    if isinstance(raw, dict) and "cookies" in raw and "origins" in raw:
        # Evtl. localStorage im flachen Format nachliefern
        if "localStorage" in raw:
            local = raw["localStorage"]
            raw.setdefault("origins", [])
            raw["origins"].append({
                "origin": "https://tinder.com",
                "localStorage": [{"name": k, "value": str(v)} for k, v in local.items()]
            })
            del raw["localStorage"]
        return raw

    # Unser kombiniertes Chrome-Export-Format: {cookies: [...], localStorage: {...}}
    if isinstance(raw, dict) and "cookies" in raw:
        cookies = raw["cookies"]
        local = raw.get("localStorage", {})
    elif isinstance(raw, list):
        # Reines Cookie-Array (EditThisCookie / Cookie-Editor)
        cookies = raw
        local = {}
    else:
        cookies = []
        local = {}

    def normalize_cookie(c: dict) -> dict:
        return {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".tinder.com"),
            "path": c.get("path", "/"),
            "expires": float(c.get("expirationDate", c.get("expires", -1))),
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": bool(c.get("secure", True)),
            "sameSite": c.get("sameSite", "None"),
        }

    origins = []
    if local:
        origins.append({
            "origin": "https://tinder.com",
            "localStorage": [{"name": k, "value": str(v)} for k, v in local.items()]
        })

    return {
        "cookies": [normalize_cookie(c) for c in cookies],
        "origins": origins,
    }


if __name__ == "__main__":
    cli(obj={})
