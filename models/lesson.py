from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


class Named(BaseModel):
    name: str


class GroupInfo(Named):
    entireclass: Literal["0", "1"]


class Entry(BaseModel):
    subjectid: Named
    teacherids: Named | None = None
    classroomids: Named | None = None
    groupids: GroupInfo


class Slot(BaseModel):
    par: list[Entry]
    impar: list[Entry]
    both: list[Entry]


class Period(BaseModel):
    starttime: str
    endtime: str

    @model_validator(mode="after")
    def valid_times(self):
        if parse_time(self.starttime) >= parse_time(self.endtime):
            raise ValueError("Invalid CEITI period interval")
        return self


def parse_time(value: str) -> time:
    return datetime.strptime(value, "%H:%M").time()


class Snapshot(BaseModel):
    data: dict[str, dict[str, Slot]]
    periods: list[Period] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_structure(self):
        if set(self.data) != set(DAYS):
            raise ValueError("CEITI weekday schema changed")
        for slots in self.data.values():
            for number, slot in slots.items():
                if not number.isdigit() or int(number) < 1:
                    raise ValueError("Invalid period number")
                if (slot.both or slot.par or slot.impar) and int(number) > len(self.periods):
                    raise ValueError("Missing period times")
                for entry in slot.both + slot.par + slot.impar:
                    subgroup_of(entry)
                    if not entry.subjectid.name.strip():
                        raise ValueError("Missing subject")
        return self


def subgroup_of(entry: Entry) -> int | None:
    if entry.groupids.entireclass == "1":
        return None
    names = {"Grupa 1": 1, "Grupa 2": 2}
    if entry.groupids.name.strip() not in names:
        raise ValueError(f"Unknown subgroup: {entry.groupids.name}")
    return names[entry.groupids.name.strip()]


class Lesson(BaseModel):
    date: date
    lesson_number: int
    start: str
    end: str
    start_at: datetime
    end_at: datetime
    subject: str
    room: str | None
    teacher: str | None
    subgroup: int | None
    week_type: Literal["both", "par", "impar"]


class DaySchedule(BaseModel):
    date: date
    group: str
    subgroup: int
    timezone: str = "Europe/Chisinau"
    week_type: str | None
    complete: bool
    stale: bool
    fetched_at: datetime
    source: str = "https://orar-api.ceiti.md/v1/orar"
    warnings: list[str]
    lessons: list[Lesson]
