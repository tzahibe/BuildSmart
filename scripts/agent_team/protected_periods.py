"""Weekend / Jewish-holiday protected periods (owner governance §26–§41, 2026-09-18).

A protected period is a contiguous run of protected days in `Asia/Jerusalem`: the configured
weekdays (Friday, Saturday) and the configured Jewish holidays, each holiday taken from Erev Chag
through its last day. The Hebrew calendar comes from `pyluach` (a maintained implementation of
the fixed calendar) — never from hard-coded Gregorian dates. Everything here is pure and
deterministic so it can be unit-tested against known dates.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from pyluach import dates as _pl

TZ = "Asia/Jerusalem"

#: configured key -> pyluach's holiday name (Israel calendar: one-day Shavuot / Shemini Atzeret)
HOLIDAY_NAMES = {
    "yom_kippur": "Yom Kippur",
    "sukkot": "Succos",              # 15–21 Tishrei (Chol HaMoed included)
    "shemini_atzeret": "Shmini Atzeres",
    "shavuot": "Shavuos",
    "rosh_hashanah": "Rosh Hashana",
    "pesach": "Pesach",
}
#: slugs used in integration-branch names
HOLIDAY_SLUGS = {v: k.replace("_", "-") for k, v in HOLIDAY_NAMES.items()}

WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


@dataclass(frozen=True)
class Calendar:
    weekdays: tuple[int, ...] = (4, 5)                       # Friday, Saturday
    holidays: tuple[str, ...] = ("yom_kippur", "sukkot", "shemini_atzeret", "shavuot")
    erev: bool = True
    tz: str = TZ

    @classmethod
    def from_config(cls, raw: dict | None) -> "Calendar":
        raw = raw or {}
        days = tuple(WEEKDAYS[str(d).lower()[:3]] for d in raw.get("weekdays", ("fri", "sat")))
        hols = tuple(str(h).lower() for h in raw.get("holidays", cls.holidays))
        unknown = [h for h in hols if h not in HOLIDAY_NAMES]
        if unknown:
            raise ValueError(f"unknown holiday keys {unknown}; known: {sorted(HOLIDAY_NAMES)}")
        return cls(weekdays=days, holidays=hols, erev=bool(raw.get("erev", True)), tz=str(raw.get("timezone", TZ)))

    # -- day classification ---------------------------------------------------------------
    def holiday_of(self, day: dt.date) -> str | None:
        """pyluach's name of a CONFIGURED holiday on this Gregorian day, else None."""
        name = _pl.GregorianDate(day.year, day.month, day.day).to_heb().holiday(israel=True)
        if name and name in {HOLIDAY_NAMES[h] for h in self.holidays}:
            return name
        return None

    def classify(self, day: dt.date) -> tuple[str | None, str | None]:
        """(kind, name): kind is HOLIDAY / EREV / SHABBAT / None. Holidays win over weekdays so a
        Friday that is also Erev Sukkot names the period after the holiday."""
        h = self.holiday_of(day)
        if h:
            return "HOLIDAY", h
        if self.erev:
            nxt = self.holiday_of(day + dt.timedelta(days=1))
            if nxt:
                return "EREV", nxt
        if day.weekday() in self.weekdays:
            return "SHABBAT", "weekend"
        return None, None

    def is_protected(self, day: dt.date) -> bool:
        return self.classify(day)[0] is not None

    # -- periods --------------------------------------------------------------------------
    def period_containing(self, day: dt.date) -> "Period | None":
        """The contiguous protected span around `day` (adjacent weekend + holiday days merge into
        ONE period), or None when the day is not protected."""
        if not self.is_protected(day):
            return None
        start = day
        while self.is_protected(start - dt.timedelta(days=1)):
            start -= dt.timedelta(days=1)
        end = day
        while self.is_protected(end + dt.timedelta(days=1)):
            end += dt.timedelta(days=1)
        kinds = [self.classify(start + dt.timedelta(days=i)) for i in range((end - start).days + 1)]
        holiday = next((n for k, n in kinds if k == "HOLIDAY"), None)
        if holiday:
            return Period(start, end, "HOLIDAY", holiday, f"integration/holiday-{HOLIDAY_SLUGS.get(holiday, 'chag')}-{start.year}")
        return Period(start, end, "SHABBAT", "weekend", f"integration/weekend-{start.isoformat()}")

    def next_period(self, day: dt.date, horizon_days: int = 400) -> "Period | None":
        for i in range(horizon_days):
            p = self.period_containing(day + dt.timedelta(days=i))
            if p:
                return p
        return None

    def now(self, clock=None) -> dt.datetime:
        ts = clock() if clock else dt.datetime.now(tz=ZoneInfo(self.tz)).timestamp()
        return dt.datetime.fromtimestamp(ts, tz=ZoneInfo(self.tz))

    def today(self, clock=None) -> dt.date:
        return self.now(clock).date()


@dataclass(frozen=True)
class Period:
    start: dt.date            # first protected day (00:00 local)
    end: dt.date              # last protected day (through 24:00 local)
    kind: str                 # SHABBAT | HOLIDAY
    name: str                 # "weekend" or the holiday name
    branch: str               # the integration branch for this period

    @property
    def label(self) -> str:
        if self.kind == "HOLIDAY":
            return f"{self.name} {self.start.year}"
        return f"Weekend {self.start.strftime('%d')}–{self.end.strftime('%d %b %Y')}"

    def contains(self, day: dt.date) -> bool:
        return self.start <= day <= self.end

    def to_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "kind": self.kind, "name": self.name, "branch": self.branch}

    @classmethod
    def from_dict(cls, d: dict) -> "Period":
        return cls(dt.date.fromisoformat(d["start"]), dt.date.fromisoformat(d["end"]), d["kind"], d["name"], d["branch"])
