from datetime import date, datetime, timedelta

from config import TZ, Settings
from models.lesson import DAYS, DaySchedule, Lesson, Snapshot, parse_time, subgroup_of


def week_type(day: date, settings: Settings) -> str | None:
    monday = day - timedelta(days=day.weekday())
    if monday in settings.week_overrides:
        return settings.week_overrides[monday]
    if settings.week_anchor_date is None:
        return None
    offset = (monday - settings.week_anchor_date).days // 7
    anchor = settings.week_anchor_type
    return anchor if offset % 2 == 0 else {"par": "impar", "impar": "par"}[anchor]


def project(snapshot: Snapshot, fetched_at: datetime, stale: bool, day: date,
            group: str, subgroup: int, settings: Settings) -> DaySchedule:
    kind = week_type(day, settings)
    lessons = []
    complete = True
    warnings = ["Using last successfully fetched snapshot"] if stale else []
    if day.weekday() < 5 and day not in settings.closed_dates:
        for number, slot in snapshot.data[DAYS[day.weekday()]].items():
            relevant = lambda entries: [e for e in entries if subgroup_of(e) in (None, subgroup)]
            if kind is None and (relevant(slot.par) or relevant(slot.impar)):
                complete = False
            # Matches site: split weeks take precedence over 'both' within a cell.
            branches = ((kind, getattr(slot, kind)),) if kind and (slot.par or slot.impar) else (("both", slot.both),) if not (slot.par or slot.impar) else ()
            for branch, entries in branches:
                for entry in relevant(entries):
                    period = snapshot.periods[int(number) - 1]
                    start, end = parse_time(period.starttime), parse_time(period.endtime)
                    lessons.append(Lesson(
                        date=day, lesson_number=int(number), start=start.strftime("%H:%M"),
                        end=end.strftime("%H:%M"), start_at=datetime.combine(day, start, TZ),
                        end_at=datetime.combine(day, end, TZ), subject=entry.subjectid.name,
                        room=entry.classroomids.name if entry.classroomids else None,
                        teacher=entry.teacherids.name if entry.teacherids else None,
                        subgroup=subgroup_of(entry), week_type=branch,
                    ))
    if not complete:
        warnings.append("Week type is unconfirmed; notifications for this day are disabled. Configure WEEK_ANCHOR_DATE/TYPE or WEEK_OVERRIDES.")
    return DaySchedule(date=day, group=group, subgroup=subgroup, week_type=kind,
                       complete=complete, stale=stale, fetched_at=fetched_at,
                       warnings=warnings, lessons=sorted(lessons, key=lambda x: (x.start_at, x.lesson_number, x.subject)))
