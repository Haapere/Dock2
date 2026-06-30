from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Profile:
    name: str
    age: int
    bio: str
    photos: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class Match:
    match_id: str
    name: str
    age: Optional[int] = None
    bio: Optional[str] = None
    last_message: Optional[str] = None
    conversation: list[dict] = field(default_factory=list)


class DatingPlatform(ABC):
    """Abstrakte Basis für alle Dating-Plattformen."""

    @abstractmethod
    async def login(self) -> bool:
        """Login mit Phone/Facebook/Apple. Gibt True zurück wenn erfolgreich."""

    @abstractmethod
    async def setup_profile(self, profile: Profile) -> bool:
        """Profil erstellen oder aktualisieren."""

    @abstractmethod
    async def swipe_right(self) -> bool:
        """Like / Swipe Right."""

    @abstractmethod
    async def swipe_left(self) -> bool:
        """Pass / Swipe Left."""

    @abstractmethod
    async def get_current_profile_info(self) -> dict:
        """Infos zum aktuell angezeigten Profil."""

    @abstractmethod
    async def get_matches(self) -> list[Match]:
        """Alle aktuellen Matches abrufen."""

    @abstractmethod
    async def send_message(self, match_id: str, text: str) -> bool:
        """Nachricht an Match senden."""

    @abstractmethod
    async def get_messages(self, match_id: str) -> list[dict]:
        """Nachrichtenverlauf für ein Match."""
