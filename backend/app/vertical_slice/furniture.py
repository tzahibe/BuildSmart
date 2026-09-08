"""Stage 6 — minimum furniture feasibility.

Thin wrapper over the frozen Geometry Core's own furniture-envelope screen (patch 4 from the
Fable review: a bounding-box inscribe test, not a placement engine — see
`geometry_core.model.furniture_envelope_fits`). No new furniture logic is introduced here;
this stage exists as its own pipeline step only so it can be extended independently later
(e.g. real multi-item placement) without touching Geometry Core or validation.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry_core.engine import WallMap, net_rect_m
from .geometry_core.model import Fixture, Rect, furniture_envelope_fits, min_furniture_envelope_m


@dataclass(frozen=True)
class FurnitureCheck:
    zone_id: str
    net_w_m: float
    net_h_m: float
    envelope_m: tuple[float, float] | None
    fits: bool | None  # None = role has no furniture requirement in this scope


def check_furniture_feasibility(fixture: Fixture, rects: dict[str, Rect], walls: WallMap) -> list[FurnitureCheck]:
    out = []
    for zone in fixture.zones:
        rect = rects.get(zone.zone_id)
        if rect is None:
            continue
        nw, nh, _ = net_rect_m(zone.zone_id, rect, walls)
        out.append(FurnitureCheck(
            zone.zone_id, nw, nh,
            min_furniture_envelope_m(zone),
            furniture_envelope_fits(zone, nw, nh),
        ))
    return out
