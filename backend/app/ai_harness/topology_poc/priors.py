"""Grounding priors for the topology critic (Issue #151, AC-2, AC-11, AC-12).

HARD DEPENDENCY ON CORRECTED #149, WITH A PREFLIGHT (owner update 2026-09-28): before any of this
module's tables are used for scoring, `preflight()` verifies that the corrected #149 artifact
(`docs/reports/real-plan-priors/adjacency-fullcorpus.json`) is present and carries all THREE
distinct semantics that artifact's own producer (`app.knowledge.adjacency_priors_fullcorpus`)
documents:

  - `spatial_touching` = `adjacency` UNION `via_door`     -> THE adjacency prior (AC-12)
  - `touching_without_door` = `adjacency` alone            -> diagnostic only, NEVER scored (AC-12)
  - `access` = `via_door`/`direct`                         -> THE access prior (AC-12)

If the artifact is missing, unreadable, or any one of the three keys is absent (or carries zero
rows), `preflight()` raises `PriorsPreflightError` and this module refuses to build a usable table
— never a silent fallback to the OLDER `adjacency.json` (Issue #141's 19-plan, in-sample artifact),
which is exactly the contamination path the owner update names explicitly.

`load_priors()` builds the adjacency prior ONLY from `spatial_touching` rows and the access prior
ONLY from `access` rows — `touching_without_door` is loaded and exposed on `Priors.diagnostic_
touching_without_door` for reporting/disclosure, but no function in this module ever wraps it in a
`row_for`-capable table, so it cannot reach `plan_log_likelihood` and cannot reach a proposal's
quality score (AC-12, proven by `tests/ai_harness/test_topology_priors_preflight.py`).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app.knowledge.adjacency_priors import eligible_pairs_for_roles, plan_log_likelihood

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)

DEFAULT_FULLCORPUS_JSON = os.path.join(
    _REPO_ROOT, "docs", "reports", "real-plan-priors", "adjacency-fullcorpus.json")
DEFAULT_ROOM_PROPORTIONS_JSON = os.path.join(
    _REPO_ROOT, "docs", "reports", "real-plan-priors", "room-proportions.json")

#: The three semantics the preflight requires — see module docstring.
REQUIRED_ADJACENCY_SEMANTICS = ("spatial_touching", "touching_without_door", "access")

#: Roles the corrected #149 corpus cannot measure at all (its own node vocabulary is
#: LIVING/KITCHEN/BEDROOM/BATHROOM/BALCONY only — see `adjacency_priors_fullcorpus.py`'s own
#: "ROLE VOCABULARY" section). Every OTHER `ProgramRole` the engine's programme can produce is
#: unmeasurable from this corpus and must be disclosed as such (AC-2), never silently treated as
#: "no evidence either way".
UNMEASURABLE_ROLES = (
    "ENTRANCE", "HALL", "DINING", "FAMILY_ROOM", "MASTER_BEDROOM", "STUDY", "DRESSING_ROOM",
    "SAFE_ROOM", "TOILET", "LAUNDRY", "STORAGE", "CIRCULATION", "STAIRWELL", "FLEX",
)

MEASURABLE_ROLES = ("LIVING", "KITCHEN", "BEDROOM", "BATHROOM", "BALCONY")


class PriorsPreflightError(RuntimeError):
    """Raised when the corrected #149 artifact is missing or does not carry all three required
    adjacency semantics — never caught and hidden, never a trigger to fall back to an older
    table (AC-11)."""


@dataclass(frozen=True)
class PriorRow:
    role_a: str
    role_b: str
    sample_count: int
    positive_count: int
    p_smoothed: float
    lift: float
    meets_min_support: bool

    @property
    def p_adjacent(self) -> float:
        """Named to match `AdjacencyPriorsTable`'s own row attribute so `plan_log_likelihood`
        (generic over any `row_for`-exposing table) works unmodified against this table too."""
        return self.p_smoothed


@dataclass(frozen=True)
class PriorTable:
    """Duck-typed exactly like `app.knowledge.adjacency_priors.AdjacencyPriorsTable` — same
    `row_for` signature — so `plan_log_likelihood` is reused, never re-derived."""

    rows: tuple
    baseline_rate: float
    semantic: str  # "spatial_touching" or "access" — informational only, never read by scoring

    def row_for(self, role_a: str, role_b: str) -> "PriorRow | None":
        a, b = sorted((role_a, role_b))
        for row in self.rows:
            if row.role_a == a and row.role_b == b:
                return row
        return None


@dataclass(frozen=True)
class Priors:
    adjacency_table: PriorTable  # built ONLY from spatial_touching (AC-12)
    access_table: PriorTable  # built ONLY from access (AC-12)
    front_door_direct_access: dict
    diagnostic_touching_without_door_rows: tuple  # never wrapped in a row_for table (AC-12)
    train_count: int
    holdout_count: int
    fullcorpus_json_path: str
    room_proportions_json_path: str
    room_proportions_rows: tuple


def _rows_from_section(section: dict) -> tuple:
    return tuple(
        PriorRow(role_a=r["role_a"], role_b=r["role_b"], sample_count=r["sample_count"],
                 positive_count=r["positive_count"], p_smoothed=r["p_smoothed"], lift=r["lift"],
                 meets_min_support=r["meets_min_support"])
        for r in section["rows"])


def preflight(fullcorpus_json_path: str = DEFAULT_FULLCORPUS_JSON) -> dict:
    """Verifies the corrected #149 artifact exists and carries all three required semantics, each
    with at least one row. Returns the parsed JSON dict on success. Raises `PriorsPreflightError`
    otherwise (AC-11) — never falls back to `adjacency.json` (the older, in-sample artifact) and
    never proceeds on partial data."""
    if not os.path.exists(fullcorpus_json_path):
        raise PriorsPreflightError(
            f"corrected #149 artifact missing at {fullcorpus_json_path} — cannot proceed. "
            "This is a hard dependency (Issue #151 requirement 8): scoring never falls back to "
            "the older docs/reports/real-plan-priors/adjacency.json (Issue #141's in-sample "
            "19-plan artifact).")
    with open(fullcorpus_json_path, encoding="utf-8") as f:
        data = json.load(f)

    missing = [key for key in REQUIRED_ADJACENCY_SEMANTICS if key not in data]
    if missing:
        raise PriorsPreflightError(
            f"{fullcorpus_json_path} is missing required semantic(s) {missing} — expected all of "
            f"{REQUIRED_ADJACENCY_SEMANTICS} (AC-11). Refusing to proceed on partial data.")

    empty = [key for key in REQUIRED_ADJACENCY_SEMANTICS if not data[key].get("rows")]
    if empty:
        raise PriorsPreflightError(
            f"{fullcorpus_json_path} carries zero rows for semantic(s) {empty} — a stale or "
            "corrupt artifact. Refusing to proceed on partial data.")

    if "train_count" not in data or "holdout_count" not in data:
        raise PriorsPreflightError(
            f"{fullcorpus_json_path} is missing train_count/holdout_count — cannot record "
            "ground-truth provenance (AC-13). Refusing to proceed.")

    return data


def load_priors(fullcorpus_json_path: str = DEFAULT_FULLCORPUS_JSON,
                room_proportions_json_path: str = DEFAULT_ROOM_PROPORTIONS_JSON) -> Priors:
    """Runs the preflight, then builds the adjacency prior ONLY from `spatial_touching` and the
    access prior ONLY from `access` (AC-12). Raises `PriorsPreflightError` loudly rather than
    building a partial/degraded `Priors` object."""
    data = preflight(fullcorpus_json_path)

    adjacency_table = PriorTable(
        rows=_rows_from_section(data["spatial_touching"]),
        baseline_rate=data["spatial_touching"]["baseline_rate"], semantic="spatial_touching")
    access_table = PriorTable(
        rows=_rows_from_section(data["access"]),
        baseline_rate=data["access"]["baseline_rate"], semantic="access")
    diagnostic_touching_without_door_rows = _rows_from_section(data["touching_without_door"])

    if not os.path.exists(room_proportions_json_path):
        raise PriorsPreflightError(
            f"#140 room-proportions artifact missing at {room_proportions_json_path} — required "
            "for prompt-context grounding (AC-2).")
    with open(room_proportions_json_path, encoding="utf-8") as f:
        proportions_data = json.load(f)

    return Priors(
        adjacency_table=adjacency_table, access_table=access_table,
        front_door_direct_access=data.get("front_door_direct_access", {}),
        diagnostic_touching_without_door_rows=diagnostic_touching_without_door_rows,
        train_count=data["train_count"], holdout_count=data["holdout_count"],
        fullcorpus_json_path=fullcorpus_json_path,
        room_proportions_json_path=room_proportions_json_path,
        room_proportions_rows=tuple(proportions_data.get("rows", ())))


def score_role_pairs(role_pairs_with_outcomes, table: PriorTable) -> "float | None":
    """Thin re-export of `plan_log_likelihood` under this module's own vocabulary — every caller in
    this package scores through this one function, never a re-derived formula (AC-12)."""
    return plan_log_likelihood(role_pairs_with_outcomes, table)


__all__ = [
    "PriorsPreflightError", "PriorRow", "PriorTable", "Priors", "preflight", "load_priors",
    "score_role_pairs", "eligible_pairs_for_roles", "REQUIRED_ADJACENCY_SEMANTICS",
    "UNMEASURABLE_ROLES", "MEASURABLE_ROLES", "DEFAULT_FULLCORPUS_JSON",
    "DEFAULT_ROOM_PROPORTIONS_JSON",
]
