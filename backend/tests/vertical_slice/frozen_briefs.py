"""Loader for the #142E frozen-brief regression fixture (`tests/fixtures/frozen_briefs_142.json`):
turns a fixture brief into a `band_pipeline.PipelineInput` exactly the way the #142A–#142D harness
drivers did (zone bounds from the fixture = ROOM_TEMPLATES, wet rooms resolved from the proposal's
own access graph: a BEDROOM/MASTER_BEDROOM entering a BATHROOM/TOILET makes it that room's ENSUITE,
otherwise a shared bathroom / guest WC entered from circulation)."""
from __future__ import annotations

import json
import os

from app.vertical_slice.band_pipeline import PipelineInput
from app.vertical_slice.geometry_core.model import ProgramRole
from app.vertical_slice.rectilinear_realizer import ZoneIntent
from app.vertical_slice.spec import WetRoomKind, WetRoomStrength
from app.vertical_slice.wet_rooms import ResolvedWetRoom

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures",
                       "frozen_briefs_142.json")
ENTRANCE_ID = "ENTRANCE"


def load_fixture() -> dict:
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def zones_of(brief: dict) -> dict[str, ZoneIntent]:
    return {z: ZoneIntent(z, ProgramRole(v["role"]), v["target"], v["min"], v["max"], v["min_short"],
                          v["max_aspect"]) for z, v in brief["zones"].items()}


def wet_rooms_of(brief: dict) -> tuple[ResolvedWetRoom, ...]:
    roles = {r["id"]: ProgramRole(r["role"]) for r in brief["rooms"]}
    incoming: dict[str, list[str]] = {}
    for a, b in brief["access_graph"]:
        incoming.setdefault(b, []).append(a)
    out = []
    for rid, role in roles.items():
        if role not in (ProgramRole.BATHROOM, ProgramRole.TOILET):
            continue
        hosts = [a for a in incoming.get(rid, ()) if roles.get(a) in (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)]
        if hosts:
            out.append(ResolvedWetRoom(rid, WetRoomKind.ENSUITE, hosts[0], WetRoomStrength.REQUIRED, True))
        else:
            kind = WetRoomKind.GUEST_WC if role is ProgramRole.TOILET else WetRoomKind.SHARED_BATHROOM
            out.append(ResolvedWetRoom(rid, kind, None, WetRoomStrength.REQUIRED, True))
    return tuple(out)


def pipeline_input(brief_id: str, brief: dict) -> PipelineInput:
    return PipelineInput(
        name=brief_id, zones=zones_of(brief),
        required_edges=tuple(tuple(e) for e in brief["spatial_adjacency"]),
        footprint_m=tuple(brief["footprint_m"]), wet_rooms=wet_rooms_of(brief),
        access_edges=tuple((a, b) for a, b in brief["access_graph"] if a != ENTRANCE_ID))
