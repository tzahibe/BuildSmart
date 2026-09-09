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
    #: The brief states, as a requirement, something the planner cannot honour. Producing a plan
    #: anyway would mean overruling the person on a point they made binding.
    UNSUPPORTED_HARD_REQUIREMENT = "UNSUPPORTED_HARD_REQUIREMENT"
    #: The wording does not settle whether it was binding. Guessing either way is a decision that
    #: belongs to the person, so ask before planning.
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    #: A room in a requested relationship could not be resolved to one room the plan has.
    AMBIGUOUS_ROOM_REFERENCE = "AMBIGUOUS_ROOM_REFERENCE"


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

    # A relationship naming a room we cannot identify is not ours to resolve: guessing which room
    # was meant would silently plan something the person did not ask for.
    unresolved = [r for r in project.room_relationships
                  if r.ambiguous or not r.source_role or not r.target_role]
    if unresolved:
        quoted = "; ".join(f'"{r.source_text}"' for r in unresolved if r.source_text)
        return ScopeRejection(
            ScopeCode.AMBIGUOUS_ROOM_REFERENCE,
            f"לא הצלחנו לזהות בוודאות באיזה חדר מדובר: {quoted or 'אחת מהבקשות'}. "
            f"אפשר לנסח מחדש בתיאור בשם החדר כפי שהוא מופיע בתוכנית — למשל חדר הורים, חדר שינה, "
            f'ממ"ד, מטבח, סלון או חדר רחצה.',
            "; ".join(f"{r.source_role or '?'}->{r.target_role or '?'}" for r in unresolved))

    # Requests the planner cannot act on, graded by how the person worded them. A PREFERENCE may be
    # set aside with a visible warning and generation continues; a HARD REQUIREMENT may not, because
    # planning around it would overrule a point they made binding; an AMBIGUOUS one is not ours to
    # decide either way. Hard requirements are reported before ambiguous ones — a definite blocker
    # is more useful to hear about than an unclear one.
    hard = [r for r in project.unsupported_requests if r.severity == "hard_requirement"]
    if hard:
        quoted = "; ".join(f'"{r.text}"' for r in hard)
        return ScopeRejection(
            ScopeCode.UNSUPPORTED_HARD_REQUIREMENT,
            f"ביקשת כדרישה מחייבת משהו שהמתכנן עדיין לא יודע לכבד: {quoted}. "
            f"אפשר לנסח את זה כהעדפה, להסיר את הדרישה, או להמתין עד שנתמוך בה — "
            f"לא נייצר תוכנית שמתעלמת ממנה.",
            "; ".join(f"{r.topic}: {r.text}" for r in hard))

    unclear = [r for r in project.unsupported_requests if r.severity == "ambiguous"]
    if unclear:
        quoted = "; ".join(f'"{r.text}"' for r in unclear)
        return ScopeRejection(
            ScopeCode.CLARIFICATION_REQUIRED,
            f"לא ברור לנו אם זו דרישה מחייבת או העדפה: {quoted}. "
            f"אפשר לנסח מחדש בתיאור — למשל \"עדיף ש...\" להעדפה או \"חייב להיות...\" לדרישה — "
            f"ואז ניצור את התוכנית.",
            "; ".join(f"{r.topic}: {r.text}" for r in unclear))

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
