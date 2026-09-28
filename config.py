"""Environment settings; all calendar calculations use Moldova local time."""
import json
import os
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

TZ = ZoneInfo("Europe/Chisinau")


class Settings(BaseModel):
    default_group: str = "P-2434R"
    refresh_seconds: int = Field(default=600, ge=60, le=900)
    database_path: Path = Path("data/ceiti.sqlite3")
    http_timeout: float = Field(default=15, gt=0, le=60)
    week_anchor_date: date | None = None
    week_anchor_type: str | None = None
    week_overrides: dict[date, str] = Field(default_factory=dict)
    closed_dates: set[date] = Field(default_factory=set)

    @model_validator(mode="after")
    def validate_calendar(self):
        if bool(self.week_anchor_date) != bool(self.week_anchor_type):
            raise ValueError("Set both WEEK_ANCHOR_DATE and WEEK_ANCHOR_TYPE")
        dates = list(self.week_overrides)
        if self.week_anchor_date:
            dates.append(self.week_anchor_date)
        if any(d.weekday() != 0 for d in dates):
            raise ValueError("Week dates must be Mondays")
        kinds = list(self.week_overrides.values())
        if self.week_anchor_type:
            kinds.append(self.week_anchor_type)
        if any(k not in {"par", "impar"} for k in kinds):
            raise ValueError("Week type must be par or impar")
        return self


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        default_group=os.getenv("DEFAULT_GROUP", "P-2434R"),
        refresh_seconds=int(os.getenv("REFRESH_SECONDS", "600")),
        database_path=Path(os.getenv("DATABASE_PATH", "data/ceiti.sqlite3")),
        http_timeout=float(os.getenv("HTTP_TIMEOUT", "15")),
        week_anchor_date=os.getenv("WEEK_ANCHOR_DATE") or None,
        week_anchor_type=os.getenv("WEEK_ANCHOR_TYPE") or None,
        week_overrides=json.loads(os.getenv("WEEK_OVERRIDES", "{}")),
        closed_dates=json.loads(os.getenv("CLOSED_DATES", "[]")),
    )
