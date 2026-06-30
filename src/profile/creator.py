from src.platforms.base import DatingPlatform, Profile
from src.utils.logger import get_logger

log = get_logger(__name__)


class ProfileCreator:
    def __init__(self, platform: DatingPlatform, cfg: dict):
        self.platform = platform
        self.cfg = cfg

    def _build_profile(self) -> Profile:
        p = self.cfg.get("profile", {})
        platform_name = self.cfg.get("platform", "tinder")
        extra = p.get(platform_name, {})

        return Profile(
            name=p.get("name", ""),
            age=p.get("age", 25),
            bio=p.get("bio", ""),
            photos=p.get("photos", []),
            extra=extra,
        )

    async def run(self):
        profile = self._build_profile()
        log.info(f"Erstelle/Aktualisiere Profil für: {profile.name}")

        success = await self.platform.setup_profile(profile)

        if success:
            log.info("[green]Profil erfolgreich eingerichtet![/green]")
        else:
            log.error("Profil-Einrichtung fehlgeschlagen")

        return success
