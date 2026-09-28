"""Durable last-known-good snapshots; replacement is a single transaction."""
from datetime import datetime
from pathlib import Path

import aiosqlite

from models.lesson import Snapshot


class Database:
    def __init__(self, path: Path):
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS snapshots (name TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)")
            await db.commit()

    async def read(self, group: str) -> tuple[Snapshot, datetime] | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT payload, fetched_at FROM snapshots WHERE name=?", (group,)) as cursor:
                row = await cursor.fetchone()
        return (Snapshot.model_validate_json(row[0]), datetime.fromisoformat(row[1])) if row else None

    async def write(self, group: str, snapshot: Snapshot, fetched_at: datetime) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO snapshots VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload, fetched_at=excluded.fetched_at", (group, snapshot.model_dump_json(), fetched_at.isoformat()))
            await db.commit()

    async def groups(self) -> list[str]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT name FROM snapshots") as cursor:
                return [row[0] for row in await cursor.fetchall()]
