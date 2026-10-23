"""R1 (#242) — everything that was FROZEN before the first realizer run.

This module is committed together with the pre-registered expectation
(`docs/reports/architectural-intelligence/R1-representation-ceiling.md`) and before any result
exists. Nothing in it may be edited after the run: the role mapping, the conversion constants, the
orientation rule, the arm definitions' parameters, the thresholds and the verdict function are the
experiment. A refusal is a result; relaxing a check, a bound or a threshold to carry a plan
invalidates it.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.vertical_slice.concept_generator import ROOM_TEMPLATES
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.rectilinear_realizer import ZoneIntent

PLANS_DIR = (Path(__file__).resolve().parents[3] / "tests" / "spikes" / "fixtures" / "geometry_shapes" / "plans")

#: The fixture directory holds 20 plans: 19 real ResPlan plans and ONE synthetic one. It is
#: identified by NAME and, independently, by its provenance; both must agree or the loader raises.
SYNTHETIC_FIXTURES = frozenset({"synthetic-spine-01"})
REAL_SOURCE_DATASET = "ResPlan"
EXPECTED_REAL_PLANS = 19

# --------------------------------------------------------------------------- role-mapping table

#: ResPlan room label -> `ProgramRole`. Complete over every label present in the 19 real plans
#: (BEDROOM, BATHROOM, LIVING, KITCHEN, CIRCULATION, TOILET, STORAGE). CIRCULATION maps to HALL, the
#: product's own circulation role (the arrival-room policy ranks HALL first and C20/C21/C26 treat it
#: as circulation); the product has no template row for the bare CIRCULATION role.
ROLE_MAP: dict[str, ProgramRole] = {
    "LIVING": ProgramRole.LIVING,
    "KITCHEN": ProgramRole.KITCHEN,
    "BEDROOM": ProgramRole.BEDROOM,
    "BATHROOM": ProgramRole.BATHROOM,
    "TOILET": ProgramRole.TOILET,
    "STORAGE": ProgramRole.STORAGE,
    "CIRCULATION": ProgramRole.HALL,
}
#: ResPlan does not label a master bedroom. The LARGEST bedroom of a plan (ResPlan `area_m2`; ties
#: to the lexicographically smallest id) maps to MASTER_BEDROOM, every other bedroom to BEDROOM,
#: whenever the plan has two or more bedrooms.
MASTER_RULE_MIN_BEDROOMS = 2

#: A ResPlan "room" under this area is a segmentation artefact (the LIVING_1/LIVING_2 fragments of
#: 0.02-0.4 m2 that sit in wall recesses), not a room. 1.5 m2 is the smallest minimum area of any
#: role in `ROOM_TEMPLATES` (STORAGE); anything smaller cannot be a room the product could name.
#: Dropped rooms are not given to anyone: they are simply not in the plan, and their space is
#: whatever the snapped neighbours leave.
SLIVER_MIN_M2 = 1.5

# --------------------------------------------------------------------------- conversion constants

#: Wall-face snapping, per axis. ResPlan rooms are interior regions, so the two faces of one wall
#: are 0.15-0.23 m apart. All vertex coordinates of the kept rooms are clustered greedily from the
#: low end (a cluster accepts a value within SNAP_GAP_M of its last member AND within SNAP_SPAN_M of
#: its first); every member moves to the cluster mean rounded to the 0.05 m grid. The two faces of a
#: wall land on one line, so the rooms tile with no gap and no overlap along it.
SNAP_GAP_M = 0.30
SNAP_SPAN_M = 0.60
GRID_M = 0.05
#: A snapped room that still overlaps an earlier one (processed in id order) loses the overlap; a
#: room that falls into several parts keeps its largest part; a room under SLIVER_MIN_M2 after
#: snapping is dropped. Every such event is recorded per plan.

#: The plan's declared entrance side is NOT used: it is UNKNOWN in 5 of 19 plans and a coarse
#: position, not a wall, in the rest. The street is the realizer's own y-min wall (`build_entrance`),
#: so each plan is tried in all four rotations (0, 90, 180, 270 degrees; no mirror), and it is
#: CARRIED when any rotation carries. A refused plan reports the rotation with the fewest failing
#: checks, a run in which the validators ran ranking before one that stopped earlier (no entrance,
#: a cell outside the wings); ties: the smallest rotation.
ROTATIONS_DEG = (0, 90, 180, 270)

#: Wet rooms MUST be declared: C17 fails closed ("kind unknown — no requirement covers it") on any
#: BATHROOM/TOILET zone that no `ResolvedWetRoom` covers, so leaving them out refuses every plan on
#: C17 and says nothing about the representation (found while testing the wrapper on a synthetic
#: layout, before any real plan was run). ResPlan carries no kind, so it is read off the plan's OWN
#: door graph, the one place the architect stated who enters what:
#:   * a BATHROOM whose every door leads to exactly ONE bedroom -> ENSUITE of that bedroom;
#:   * a TOILET -> GUEST_WC;  any other BATHROOM -> SHARED_BATHROOM.
#: Strength REQUIRED, explicit. A wet room that is several cells declares each cell with the zone's
#: kind (an ensuite's host is the host cell the door lands on, or the host's first cell).
ENSUITE_BEDROOM_ROLES = ("BEDROOM", "MASTER_BEDROOM")

# --------------------------------------------------------------------------- arms

ARM_1 = "arm1"      # each room a single rectangle
ARM_2 = "arm2"      # each room a group of same-zone OPEN-walled cells, validated on the union
#: NOT scored and not able to change the verdict: arm 2 plus a refinement that splits cells until
#: every cell side is either fully shared with neighbours or fully exterior (the realizer types a
#: side with ONE wall type). Reported so a STOP cannot be mistaken for a conversion artefact.
ARM_2R = "arm2R"
SCORED_ARMS = (ARM_1, ARM_2)

# --------------------------------------------------------------------------- thresholds

N_PLANS = 19
GO_MIN_CARRIED = 13
GO_MIN_GAIN = 6
PIVOT_MIN, PIVOT_MAX = 7, 12
STOP_MAX_CARRIED = 6
#: STOP also fires when at least STOP_CHECKS_MIN_COUNT of these check ids each fail on MORE THAN
#: half of the plans (i.e. on at least 10 of 19), measured on arm 2, per plan on the reported
#: rotation.
STOP_CHECKS = ("C27", "C9", "C14", "C30")
STOP_CHECKS_MIN_COUNT = 3
STOP_FAIL_MORE_THAN = N_PLANS / 2


def zone_intent(zone_id: str, role: ProgramRole) -> ZoneIntent:
    """The bounds the PRODUCT would hold this role to: its `ROOM_TEMPLATES` row (min area, the
    template's target, the HARD maximum that C21 gates on, minimum short side, maximum aspect)."""
    t = ROOM_TEMPLATES[role]
    return ZoneIntent(zone_id, role, t.target_area_m2, t.min_area_m2, t.hard_max,
                      t.min_short_side_m, t.max_aspect_ratio)


def verdict(carried_arm1: int, carried_arm2: int, check_fail_counts_arm2: dict[str, int]) -> tuple[str, str]:
    """GO / PIVOT / STOP, applying the thresholds exactly as written in the Issue.

    STOP first (6 or fewer carried, or >= 3 of C27/C9/C14/C30 each failing on more than half the
    plans). Then GO (arm 2 carries >= 13 AND gains >= 6 over arm 1). Then PIVOT (7..12). The one
    case the Issue leaves open — arm 2 carries >= 13 but the gain over arm 1 is under 6 — is
    classified PIVOT here, in advance: GO's conditions are not met and no concept work may start.
    """
    over = [c for c in STOP_CHECKS if check_fail_counts_arm2.get(c, 0) > STOP_FAIL_MORE_THAN]
    if carried_arm2 <= STOP_MAX_CARRIED:
        return "STOP", f"arm 2 carries {carried_arm2} <= {STOP_MAX_CARRIED} of {N_PLANS}"
    if len(over) >= STOP_CHECKS_MIN_COUNT:
        return "STOP", (f"{len(over)} of {list(STOP_CHECKS)} fail on more than half the plans: {over}")
    gain = carried_arm2 - carried_arm1
    if carried_arm2 >= GO_MIN_CARRIED and gain >= GO_MIN_GAIN:
        return "GO", f"arm 2 carries {carried_arm2} >= {GO_MIN_CARRIED} and gains {gain} >= {GO_MIN_GAIN} over arm 1"
    if PIVOT_MIN <= carried_arm2 <= PIVOT_MAX:
        return "PIVOT", f"arm 2 carries {carried_arm2} in [{PIVOT_MIN},{PIVOT_MAX}]"
    return "PIVOT", (f"arm 2 carries {carried_arm2} but gains only {gain} over arm 1 (< {GO_MIN_GAIN}): "
                     f"GO is not met; classified PIVOT in advance")


def load_real_plans() -> dict[str, dict]:
    """The 19 real plans, keyed by file stem. The synthetic fixture is excluded by name AND by
    provenance; the two must agree and exactly 19 must remain."""
    out: dict[str, dict] = {}
    seen_synthetic: set[str] = set()
    for path in sorted(PLANS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        source = data["plan_reference"]["provenance"]["source_dataset"]
        by_name = path.stem in SYNTHETIC_FIXTURES
        by_source = source != REAL_SOURCE_DATASET
        if by_name != by_source:
            raise ValueError(f"{path.name}: name says synthetic={by_name}, provenance says {source!r}")
        if by_name:
            seen_synthetic.add(path.stem)
            continue
        out[path.stem] = data["plan_reference"]
    if seen_synthetic != set(SYNTHETIC_FIXTURES):
        raise ValueError(f"synthetic fixture(s) not found: {sorted(SYNTHETIC_FIXTURES - seen_synthetic)}")
    if len(out) != EXPECTED_REAL_PLANS:
        raise ValueError(f"expected {EXPECTED_REAL_PLANS} real plans, found {len(out)}")
    return out
