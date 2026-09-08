"""Explicit supported-scope validation for the demo path.

Everything outside the envelope is REFUSED with a product-level reason. Nothing is silently
downgraded: a four-bedroom brief never becomes a three-bedroom house, and a missing footprint
never becomes an invented one.

The envelope is exactly what the pipeline has been proven on — see
`docs/DEMO_END_TO_END_AND_UI_GAP_REPORT.md` §7.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.projects.models import Project

SUPPORTED_BEDROOMS = (2, 3)
SUPPORTED_WET_ROOMS = (1, 2, 3)
MAX_PARKING_SPACES = 2
SUPPORTED_FLOORS = 1


class ScopeCode(str, Enum):
    BEDROOMS_UNSUPPORTED = "BEDROOMS_UNSUPPORTED"
    WET_ROOMS_UNSUPPORTED = "WET_ROOMS_UNSUPPORTED"
    FLOORS_UNSUPPORTED = "FLOORS_UNSUPPORTED"
    PARKING_UNSUPPORTED = "PARKING_UNSUPPORTED"
    POOL_UNSUPPORTED = "POOL_UNSUPPORTED"
    FOOTPRINT_REQUIRED = "FOOTPRINT_REQUIRED"
    REQUIREMENTS_NOT_PARSED = "REQUIREMENTS_NOT_PARSED"
    BEDROOMS_UNKNOWN = "BEDROOMS_UNKNOWN"


@dataclass(frozen=True)
class ScopeRejection:
    code: ScopeCode
    message: str          # product language, shown to the user
    detail: str           # what was actually asked for


def _value(tagged, default=None):
    return default if tagged is None or tagged.value is None else tagged.value


def check_supported(project: Project) -> ScopeRejection | None:
    """None when the request is inside the demo envelope."""
    if project.requirements_parsed_at is None:
        return ScopeRejection(
            ScopeCode.REQUIREMENTS_NOT_PARSED,
            "עדיין לא הבנו את הדרישות. יש להריץ ניתוח דרישות לפני יצירת תוכנית.",
            "requirements_parsed_at is None")

    floors = _value(project.floors, 1)
    if floors != SUPPORTED_FLOORS:
        return ScopeRejection(
            ScopeCode.FLOORS_UNSUPPORTED,
            "בשלב זה הדמו תומך בבית בקומה אחת בלבד.",
            f"floors={floors}")

    bedrooms = _value(project.bedrooms)
    if bedrooms is None:
        return ScopeRejection(
            ScopeCode.BEDROOMS_UNKNOWN,
            "לא הצלחנו להבין כמה חדרי שינה נדרשים. אפשר להשלים זאת במסך הסקירה.",
            "bedrooms is unknown")
    if bedrooms not in SUPPORTED_BEDROOMS:
        return ScopeRejection(
            ScopeCode.BEDROOMS_UNSUPPORTED,
            f"בשלב זה הדמו תומך ב-{SUPPORTED_BEDROOMS[0]} עד {SUPPORTED_BEDROOMS[-1]} "
            f"חדרי שינה. התצורה הזו עדיין לא נתמכת.",
            f"bedrooms={bedrooms}")

    wet_rooms = _value(project.wet_rooms, 1)
    if wet_rooms not in SUPPORTED_WET_ROOMS:
        return ScopeRejection(
            ScopeCode.WET_ROOMS_UNSUPPORTED,
            f"בשלב זה הדמו תומך עד {SUPPORTED_WET_ROOMS[-1]} חדרי רחצה.",
            f"wet_rooms={wet_rooms}")

    parking = _value(project.parking_spaces, 0)
    if parking > MAX_PARKING_SPACES:
        return ScopeRejection(
            ScopeCode.PARKING_UNSUPPORTED,
            f"בשלב זה הדמו תומך עד {MAX_PARKING_SPACES} מקומות חניה.",
            f"parking_spaces={parking}")

    if project.pool is not None and project.pool.requested.value is True:
        return ScopeRejection(
            ScopeCode.POOL_UNSUPPORTED,
            "תכנון בריכה עדיין לא נתמך בדמו.",
            "pool.requested=True")

    if project.selected_footprint is None:
        return ScopeRejection(
            ScopeCode.FOOTPRINT_REQUIRED,
            "צריך לבחור מתאר בניין מלבני לפני יצירת התוכנית.",
            "selected_footprint is None")
    if project.selected_footprint.shape_type != "RECTANGLE":
        return ScopeRejection(
            ScopeCode.FOOTPRINT_REQUIRED,
            "בשלב זה הדמו תומך במתאר מלבני בלבד.",
            f"shape_type={project.selected_footprint.shape_type}")

    return None
