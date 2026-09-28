import asyncio
import logging

import httpx

from models.lesson import Snapshot

log = logging.getLogger(__name__)
BASE_URL = "https://orar-api.ceiti.md/v1"


class GroupNotFound(ValueError):
    """The exact group name is absent from CEITI's current catalogue."""


class CeitiClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def get_json(self, path: str, params: dict | None = None):
        for attempt in range(3):
            try:
                response = await self.http.get(BASE_URL + path, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError):
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * 2**attempt)

    async def fetch(self, group: str) -> Snapshot:
        log.info("Loading CEITI group=%s", group)
        groups = await self.get_json("/grupe")
        if not isinstance(groups, list) or any(not isinstance(g, dict) or "name" not in g or "_id" not in g for g in groups):
            raise ValueError("Invalid CEITI group catalogue")
        match = next((g for g in groups if g["name"] == group), None)
        if match is None:
            raise GroupNotFound(group)
        return Snapshot.model_validate(await self.get_json("/orar", {"_id": match["_id"], "tip": "class"}))
