import asyncio
import random
from anthropic import AsyncAnthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.platforms.base import DatingPlatform, Match
from src.utils.logger import get_logger

log = get_logger(__name__)
console = Console()

OPENER_PROMPTS = {
    "witty": "Schreibe eine witzige, originelle Eröffnungsnachricht. Kein Standard-Opener.",
    "friendly": "Schreibe eine freundliche, warme Eröffnungsnachricht.",
    "direct": "Schreibe eine direkte, selbstbewusste Eröffnungsnachricht.",
    "question": "Stelle eine interessante Frage als Eröffnung, die Gespräch einleitet.",
}


class ChatBot:
    def __init__(self, platform: DatingPlatform, cfg: dict):
        self.platform = platform
        self.cfg = cfg
        self.chat_cfg = cfg.get("chat", {})
        self.client = AsyncAnthropic(api_key=cfg.get("anthropic_api_key", ""))
        self.model = self.chat_cfg.get("ai_model", "claude-haiku-4-5-20251001")
        self.persona = self.chat_cfg.get("persona", "")
        self.language = self.chat_cfg.get("language", "de")
        self.opener_style = self.chat_cfg.get("opener_style", "witty")
        self.max_messages = self.chat_cfg.get("max_messages_per_match", 10)
        self.processed: set[str] = set()

    async def _generate_response(
        self, match: Match, conversation: list[dict], is_opener: bool = False
    ) -> str:
        lang_instruction = "Antworte auf Deutsch." if self.language == "de" else "Reply in English."

        system = f"""{self.persona}

{lang_instruction}
Schreibe kurze, natürliche Nachrichten (1-3 Sätze).
Keine Emojis übertreiben. Sei authentisch und interessiert.
Ziel: Ein persönliches Treffen vereinbaren.
"""
        if is_opener:
            opener_hint = OPENER_PROMPTS.get(self.opener_style, OPENER_PROMPTS["witty"])
            profile_info = ""
            if match.bio:
                profile_info = f"\nProfil von {match.name}: {match.bio}"
            messages = [{
                "role": "user",
                "content": f"{opener_hint}{profile_info}\nSchreibe eine Eröffnungsnachricht an {match.name}."
            }]
        else:
            messages = conversation[-10:]  # Letzte 10 Nachrichten als Kontext

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                system=system,
                messages=messages,
            )
            return response.content[0].text.strip()
        except Exception as e:
            log.error(f"KI-Fehler: {e}")
            return ""

    async def _process_match(self, match: Match):
        if match.match_id in self.processed:
            return

        messages = await self.platform.get_messages(match.match_id)
        match.conversation = messages

        sent_count = sum(1 for m in messages if m["role"] == "assistant")
        if sent_count >= self.max_messages:
            log.info(f"[yellow]{match.name}: Max Nachrichten erreicht ({sent_count})[/yellow]")
            return

        is_opener = len(messages) == 0

        # Nur antworten wenn letzte Nachricht vom anderen
        if not is_opener and messages and messages[-1]["role"] == "assistant":
            log.info(f"[dim]{match.name}: Warte auf Antwort...[/dim]")
            return

        response = await self._generate_response(match, messages, is_opener=is_opener)
        if not response:
            return

        console.print(Panel(
            f"[bold cyan]{match.name}[/bold cyan]\n"
            f"[dim]{'Eröffnung' if is_opener else 'Antwort'}:[/dim] {response}",
            title="[green]KI-Nachricht[/green]"
        ))

        # Menschliche Schreib-Verzögerung simulieren
        typing_delay = len(response) * random.uniform(0.04, 0.08)
        typing_delay = max(2.0, min(typing_delay, 15.0))
        log.info(f"Schreibe {typing_delay:.1f}s...")
        await asyncio.sleep(typing_delay)

        ok = await self.platform.send_message(match.match_id, response)
        if ok:
            self.processed.add(match.match_id)
            log.info(f"[green]Gesendet an {match.name}[/green]")
        else:
            log.error(f"Senden an {match.name} fehlgeschlagen")

    async def run_once(self):
        log.info("Lade Matches...")
        matches = await self.platform.get_matches()

        if not matches:
            log.info("Keine Matches gefunden")
            return 0

        log.info(f"[cyan]{len(matches)} Matches gefunden[/cyan]")

        table = Table(title="Aktuelle Matches")
        table.add_column("Name")
        table.add_column("Letzte Nachricht", max_width=50)
        for m in matches:
            table.add_row(m.name, m.last_message or "[dim]noch keine[/dim]")
        console.print(table)

        for match in matches:
            await self._process_match(match)
            await asyncio.sleep(random.uniform(2, 5))

        return len(matches)

    async def run_loop(self):
        interval = self.chat_cfg.get("check_interval", 300)
        console.rule("[bold blue]Chat-Bot gestartet[/bold blue]")
        log.info(f"Check alle {interval}s | Modell: {self.model}")

        while True:
            try:
                count = await self.run_once()
                log.info(f"[dim]Warte {interval}s... (Nächster Check)[/dim]")
            except KeyboardInterrupt:
                log.info("Bot gestoppt")
                break
            except Exception as e:
                log.error(f"Fehler: {e}")

            await asyncio.sleep(interval)
