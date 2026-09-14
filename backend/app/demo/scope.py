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

from app.vertical_slice.site import PARKING_BAY_DEPTH_M

from . import site_geometry

#: 4 and 5 bedrooms became reachable once a shared wet room could sit off a bedroom instead of the
#: corridor (`programme_variants`): that removes a private row, and a row was costing ~40 m² of
#: footprint. Measured smallest plannable area: 3BR/2wet 135 m², 4BR/2wet 130 m², 5BR/2wet 165 m².
#:
#: 1 and 6 were added on measurement, not on principle. A 216-run sweep (bedrooms x wet rooms x
#: safe room x six footprints) asked the ENGINE what it can actually realize:
#:
#:      1BR 22%   2BR 50%   3BR 44%   4BR 47%   5BR 33%   6BR 33%
#:
#: 6 bedrooms plan at exactly the rate 5 does, and 5 was already supported; 1 plans on a 14 x 12 m
#: footprint. Refusing them was a guard that had stopped matching the engine behind it — and the
#: refusal is the worst kind, since it arrives after the person has entered everything.
SUPPORTED_BEDROOMS = (1, 2, 3, 4, 5, 6)
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
    #: The project carries no authoritative parcel geometry. The planner refuses rather than
    #: inventing one from the building, which is what it used to do.
    SITE_GEOMETRY_REQUIRED = "SITE_GEOMETRY_REQUIRED"
    #: The chosen outline does not fit the land that is left after the demo setbacks.
    FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION = "FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION"
    #: The outline fits the setbacks, but not once the parking bays take their band at the street.
    #: Kept apart from the code above because the setbacks are not what failed: the person can
    #: lower those to zero and the cars are still 5 m long. The numbers worth changing are the
    #: parking count, the outline's depth, or the parcel.
    FOOTPRINT_LEAVES_NO_ROOM_FOR_PARKING = "FOOTPRINT_LEAVES_NO_ROOM_FOR_PARKING"
    #: There is no land left at all — the setbacks alone use up a whole side of the parcel. Kept
    #: apart from the code above because the outline is not what failed: no outline of any size
    #: would pass, and the numbers worth changing are the site's, not the building's.
    NO_BUILDABLE_AREA = site_geometry.NO_BUILDABLE_AREA_CODE


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

    # AUTHORITATIVE SITE. Without real parcel dimensions there is nothing honest to plan inside, and
    # the old behaviour — deriving a plot from the footprint — could only ever invent land.
    site = site_geometry.derive(project)
    if site is None:
        return ScopeRejection(
            ScopeCode.SITE_GEOMETRY_REQUIRED,
            "כדי לתכנן צריך את מידות המגרש עצמו — רוחב, עומק, ואיזו חזית פונה לרחוב. "
            "שטח בלבד אינו מספיק: אותו שטח בצורות שונות נותן תוצאות שונות.",
            f"plot_width_m={project.plot_width_m}, plot_depth_m={project.plot_depth_m}, "
            f"street_facing_side={project.street_facing_side}")

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

    # FIT. The site is not enlarged and the footprint is not shrunk — the person is told both sets
    # of numbers and decides which to change.
    fit = site_geometry.check_footprint_fits(
        site, project.selected_footprint.width_m, project.selected_footprint.depth_m)
    if not fit.fits:
        # No buildable region at all is a different answer from an outline that is too big for one,
        # and it gets the message that names its own cause rather than one comparing the outline
        # against a rectangle that does not exist.
        no_area = site_geometry.no_buildable_area_message(site)
        if no_area is not None:
            return ScopeRejection(ScopeCode.NO_BUILDABLE_AREA, no_area, fit.detail)
        return ScopeRejection(
            ScopeCode.FOOTPRINT_DOES_NOT_FIT_BUILDABLE_REGION,
            f"המתאר שנבחר ({project.selected_footprint.width_m:.2f} × "
            f"{project.selected_footprint.depth_m:.2f} מ׳) אינו נכנס בשטח שנותר לבנייה. "
            f"המגרש הוא {site.plot_width_m:.2f} × {site.plot_depth_m:.2f} מ׳, ואחרי נסיגות הדמו "
            f"(חזית {site.front_setback_m}, אחורית {site.rear_setback_m}, צדדים "
            f"{site.side_setback_m}) נשאר שטח בנייה של "
            f"{site_geometry.buildable_dimensions_he(site)}. "
            f"אפשר לבחור מתאר קטן יותר או לעדכן את מידות המגרש. "
            f"{site_geometry.SETBACK_DISCLAIMER}",
            fit.detail)

    # PARKING TAKES LAND TOO. The bays stand in the street-side band and the house is placed
    # behind them (`site.front_band_m`), so when the front setback is shallower than a bay the
    # depth left for the house is less than the buildable rectangle promised. Decided here, before
    # anything is planned, for the same reason the fit check above is: the person is told both sets
    # of numbers and chooses which to change. Validation C18 then proves the delivered plan kept
    # the bays clear of the house.
    if parking > 0 and site.near_setback_m < PARKING_BAY_DEPTH_M:
        depth_left = round(site.canonical_depth_m - PARKING_BAY_DEPTH_M - site.far_setback_m, 2)
        if project.selected_footprint.depth_m > depth_left + 1e-9:
            return ScopeRejection(
                ScopeCode.FOOTPRINT_LEAVES_NO_ROOM_FOR_PARKING,
                f"המתאר שנבחר ({project.selected_footprint.width_m:.2f} × "
                f"{project.selected_footprint.depth_m:.2f} מ׳) נכנס במגרש, אבל לא נשאר מקום "
                f"ל-{parking} מקומות חניה לפניו: חניה צריכה רצועה בעומק {PARKING_BAY_DEPTH_M:.1f} מ׳ "
                f"מקו הרחוב, ואחריה נשאר לבית עומק של {max(depth_left, 0.0):.2f} מ׳ בלבד. "
                f"אפשר לבחור מתאר פחות עמוק, להקטין את מספר החניות, או לעדכן את מידות המגרש.",
                f"footprint depth {project.selected_footprint.depth_m} m > {depth_left} m left behind "
                f"a {PARKING_BAY_DEPTH_M} m parking band (front setback {site.near_setback_m} m, "
                f"rear {site.far_setback_m} m, plot depth {site.canonical_depth_m} m)")

    return None
