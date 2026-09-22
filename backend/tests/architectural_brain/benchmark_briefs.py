"""Three benchmark briefs shared by ``test_retrieval.py`` and ``test_synthesis.py`` (Issue #95,
AC-1/AC-2) plus the fixture-corpus loader both use. Each brief is a genuinely different typology
so the ACs' "not by area alone" / "topologically distinct candidates" claims are real, not
incidental.
"""
from __future__ import annotations

import os

from spikes.architectural_brain.brief import Brief
from spikes.architectural_brain.corpus_io import CorpusEntry, load_corpus_dir

from app.vertical_slice.spec import (
    PlotSpec,
    ProgramSpec,
    RelationStrength,
    RoomRelation,
    RoomRelationshipRequirement,
    WetRoomKind,
    WetRoomRequirement,
)

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "plans")


def load_fixture_corpus() -> list[CorpusEntry]:
    return load_corpus_dir(FIXTURES_DIR)


# Compact family house: 3 bedrooms, an ensuite + a shared bathroom, a stated kitchen<->living
# adjacency preference, rectangular outline, 140 m2 -- the plainest, most common typology.
COMPACT_FAMILY = Brief(
    program=ProgramSpec(
        bedrooms=3, safe_room=True, open_plan_living=True, wet_rooms=2,
        target_built_area_m2=140.0,
        relationships=(
            RoomRelationshipRequirement(source_role="KITCHEN", target_role="LIVING",
                                        relation=RoomRelation.ADJACENT,
                                        strength=RelationStrength.PREFERENCE),
        ),
        wet_room_kinds=(
            WetRoomRequirement(kind=WetRoomKind.ENSUITE, host="MASTER_BEDROOM"),
            WetRoomRequirement(kind=WetRoomKind.SHARED_BATHROOM),
        ),
    ),
    stories=1,
    outline_preference="RECTANGULAR",
)

# Large two-wing house: SAME target area as COMPACT_FAMILY (140 m2) but a different programme (5
# bedrooms, no stated wet-room kind preference, an L/two-wing outline) -- this is AC-1's "same
# area, different programme -> different top-3" case.
LARGE_TWO_WING = Brief(
    program=ProgramSpec(
        bedrooms=5, safe_room=True, open_plan_living=False, wet_rooms=3,
        target_built_area_m2=140.0,
    ),
    stories=1,
    outline_preference="TWO_WING",
    circulation_preference="TWO_WING",
)

# Hub-lobby, open-plan house: 4 bedrooms, a central-public zoning + hub-lobby circulation
# preference, larger target area -- a third, distinct typology.
HUB_LOBBY_OPEN_PLAN = Brief(
    program=ProgramSpec(
        bedrooms=4, safe_room=True, open_plan_living=True, wet_rooms=2,
        target_built_area_m2=200.0,
        wet_room_kinds=(
            WetRoomRequirement(kind=WetRoomKind.SHARED_BATHROOM),
            WetRoomRequirement(kind=WetRoomKind.SHARED_BATHROOM),
        ),
    ),
    stories=1,
    circulation_preference="HUB_LOBBY",
    zoning_preference="CENTRAL_PUBLIC",
)

BENCHMARK_BRIEFS = (COMPACT_FAMILY, LARGE_TWO_WING, HUB_LOBBY_OPEN_PLAN)

#: A plausible 20x24m plot for every benchmark brief -- the same site each brief is asked against.
BENCHMARK_SITE = PlotSpec(width_m=20.0, depth_m=24.0)
