from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from config import TZ
from models.lesson import DaySchedule
from services.schedule_service import project

router = APIRouter(prefix="/api")
Group = Annotated[str, Query(min_length=1, max_length=60, pattern=r"^[\w .()-]+$")]
Subgroup = Annotated[int, Query(ge=1, le=2)]


async def get_day(request: Request, day: date, group: str, subgroup: int) -> DaySchedule:
    today = datetime.now(TZ).date()
    if not today - timedelta(days=7) <= day <= today + timedelta(days=14):
        raise HTTPException(422, "Only dates from 7 days ago to 14 days ahead are supported; CEITI provides no history")
    snapshot, fetched_at, stale = await request.app.state.cache.get(group)
    return project(snapshot, fetched_at, stale, day, group, subgroup, request.app.state.settings)


@router.get("/schedule/today", response_model=DaySchedule)
async def today(request: Request, group: Group = "P-2434R", subgroup: Subgroup = 1):
    return await get_day(request, datetime.now(TZ).date(), group, subgroup)


@router.get("/schedule/tomorrow", response_model=DaySchedule)
async def tomorrow(request: Request, group: Group = "P-2434R", subgroup: Subgroup = 1):
    return await get_day(request, datetime.now(TZ).date() + timedelta(days=1), group, subgroup)


@router.get("/schedule/date/{day}", response_model=DaySchedule)
async def by_date(request: Request, day: date, group: Group = "P-2434R", subgroup: Subgroup = 1):
    return await get_day(request, day, group, subgroup)


@router.get("/schedule/next")
async def next_lesson(request: Request, group: Group = "P-2434R", subgroup: Subgroup = 1):
    now = datetime.now(TZ)
    for offset in range(8):
        result = await get_day(request, now.date() + timedelta(days=offset), group, subgroup)
        if not result.complete:
            raise HTTPException(409, "Cannot determine next lesson: week type is unconfirmed")
        future = [x for x in result.lessons if x.start_at > now]
        if future:
            return {"lesson": future[0], "stale": result.stale, "fetched_at": result.fetched_at}
    return {"lesson": None, "searched_days": 8}


@router.get("/config")
async def config(request: Request):
    settings = request.app.state.settings
    return {"timezone": "Europe/Chisinau", "default_group": settings.default_group,
            "subgroups": [1, 2], "refresh_seconds": settings.refresh_seconds,
            "week_anchor_date": settings.week_anchor_date,
            "week_anchor_type": settings.week_anchor_type,
            "week_overrides": {str(k): v for k, v in settings.week_overrides.items()},
            "week_policy": "user-confirmed calendar-week anchor; no ISO parity inference"}


@router.get("/schedule/plan")
async def plan(request: Request, group: Group = "P-2434R", subgroup: Subgroup = 1,
               summary_hour: Annotated[int, Query(ge=0, le=23)] = 19,
               summary_minute: Annotated[int, Query(ge=0, le=59)] = 40):
    # One snapshot and one clock read prevent mixed revisions / midnight races.
    now = datetime.now(TZ)
    snapshot, fetched_at, stale = await request.app.state.cache.get(group)
    days = [project(snapshot, fetched_at, stale, now.date() + timedelta(days=i),
                    group, subgroup, request.app.state.settings) for i in range(2)]
    return {"generated_at": now, "timezone": "Europe/Chisinau", "days": days,
            "summary_at": datetime.combine(now.date(), time(summary_hour, summary_minute), TZ)}
