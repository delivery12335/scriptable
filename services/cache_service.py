import asyncio
import logging
from datetime import datetime

from config import TZ, Settings
from database import Database
from services.ceiti_client import CeitiClient, GroupNotFound

log = logging.getLogger(__name__)


class SourceUnavailable(RuntimeError):
    """No trustworthy snapshot is available."""


class CacheService:
    def __init__(self, db: Database, client: CeitiClient, settings: Settings):
        self.db, self.client, self.settings = db, client, settings
        self.lock = asyncio.Lock()
        self.retry_after: dict[str, float] = {}
        self.failed: set[str] = set()

    async def get(self, group: str, force: bool = False):
        async with self.lock:
            stored = await self.db.read(group)
            now = datetime.now(TZ)
            expired = stored is None or (now - stored[1]).total_seconds() >= self.settings.refresh_seconds
            if force or expired:
                if not force and now.timestamp() < self.retry_after.get(group, 0):
                    if stored:
                        return *stored, True
                    raise SourceUnavailable("CEITI unavailable; retry shortly")
                try:
                    snapshot = await self.client.fetch(group)
                    fetched_at = datetime.now(TZ)
                    await self.db.write(group, snapshot, fetched_at)
                    self.failed.discard(group)
                    self.retry_after.pop(group, None)
                    log.info("Cache updated group=%s", group)
                    return snapshot, fetched_at, False
                except Exception as exc:
                    self.failed.add(group)
                    self.retry_after[group] = now.timestamp() + 60
                    log.warning("CEITI refresh failed group=%s: %s", group, exc)
                    if not stored:
                        if isinstance(exc, GroupNotFound):
                            raise
                        raise SourceUnavailable("CEITI unavailable and cache is empty") from exc
            if stored is None:
                raise SourceUnavailable("Cache is empty")
            return *stored, expired or group in self.failed

    async def refresh_all(self) -> None:
        groups = set(await self.db.groups()) | {self.settings.default_group}
        for group in groups:
            try:
                await self.get(group, force=True)
            except (SourceUnavailable, GroupNotFound) as exc:
                log.warning("Warmup incomplete: %s", exc)

    async def run(self) -> None:
        # Runs all day, including mornings; startup warmup happens in lifespan.
        while True:
            await asyncio.sleep(self.settings.refresh_seconds)
            try:
                await self.refresh_all()
            except Exception:
                log.exception("Background refresh failed; will retry next cycle")
