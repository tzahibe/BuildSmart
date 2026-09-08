"""Geometry Core Proof Spike — the proofs.

P1 full tiling                     P6 wall-thickness-aware net area
P2 no overlap                      P7 required adjacency / access realizable
P3 no unassigned interior area     P8 open-plan carries NO artificial doors
P4 room area tolerance             P9 declared wing seams are real (L-shape honesty check)
P5 min short side + aspect
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine import SolveResult, net_rect_m
from model import (
    ConnectionKind,
    Fixture,
    OutdoorClassification,
    ProgramRole,
    Rect,
    Side,
    WallType,
    furniture_envelope_fits,
    min_furniture_envelope_m,
    m_to_u,
    u_to_m,
)

TOL_M2 = 0.01
TOL_M = 0.01
EFFICIENCY_BAND = (0.70, 0.92)
_CIRCULATION_ROLES = (ProgramRole.HALL, ProgramRole.CIRCULATION)


@dataclass
class Proof:
    proof_id: str
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    fixture: str
    proofs: list[Proof] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(p.passed for p in self.proofs)

    def add(self, pid: str, name: str, passed: bool, detail: str = "") -> None:
        self.proofs.append(Proof(pid, name, passed, detail))


# ------------------------------------------------------------------ openings

@dataclass(frozen=True)
class GeneratedOpening:
    a: str
    b: str
    kind: ConnectionKind
    shared_len_m: float


def generate_openings(fixture: Fixture, res: SolveResult) -> list[GeneratedOpening]:
    """Openings come ONLY from DesiredAccessTopology, and ONLY for kinds that need a hole in
    a wall. OPEN_CONNECTION is deliberately skipped — that is the whole point of P8."""
    out: list[GeneratedOpening] = []
    for e in fixture.access.edges:
        if e.kind is ConnectionKind.OPEN_CONNECTION:
            continue
        ra, rb = res.rects.get(e.a), res.rects.get(e.b)
        if ra is None or rb is None:
            continue
        shared = ra.shared_edge_len_u(rb)
        if shared > 0:
            out.append(GeneratedOpening(e.a, e.b, e.kind, u_to_m(shared)))
    return out


def _side_between(a: Rect, b: Rect) -> Side | None:
    if a.x2 == b.x:
        return Side.E
    if b.x2 == a.x:
        return Side.W
    if a.y2 == b.y:
        return Side.S
    if b.y2 == a.y:
        return Side.N
    return None


# ------------------------------------------------------------------ proofs

def validate(fixture: Fixture, res: SolveResult) -> Report:
    rep = Report(fixture.name)
    rects = res.rects
    walls = res.walls

    # -------- P1 full tiling
    gross = fixture.footprint_area_m2()
    tiled = round(sum(r.area_m2() for r in rects.values()), 4)
    rep.add("P1", "full tiling", abs(tiled - gross) < TOL_M2,
            f"tiled {tiled} m² vs footprint {gross} m²")

    # -------- P2 no overlap
    ids = sorted(rects)
    worst = 0
    pair = ""
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            ov = rects[ids[i]].overlap_area_u(rects[ids[j]])
            if ov > worst:
                worst, pair = ov, f"{ids[i]}/{ids[j]}"
    rep.add("P2", "no overlap", worst == 0, "none" if worst == 0 else f"{pair} overlap {worst}u²")

    # -------- P3 no unassigned interior area
    # Every leaf must sit inside exactly one wing, and each wing's area must be fully consumed.
    unassigned: list[str] = []
    for wing in fixture.wings:
        wr = wing.rect()
        inside = [r for r in rects.values()
                  if r.x >= wr.x and r.y >= wr.y and r.x2 <= wr.x2 and r.y2 <= wr.y2]
        covered = sum(r.w * r.h for r in inside)
        if covered != wr.w * wr.h:
            unassigned.append(
                f"wing {wing.wing_id}: {u_to_m(wr.w * wr.h - covered) * 20:.2f} m² unassigned"
            )
    rep.add("P3", "no unassigned interior area", not unassigned,
            "; ".join(unassigned) or "every wing fully consumed by leaves")

    # -------- P4 area tolerance (NET)
    bad = []
    for z in fixture.zones:
        if z.zone_id not in rects:
            continue
        _, _, net = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        if not (z.net_area_min_m2 - TOL_M2 <= net <= z.net_area_max_m2 + TOL_M2):
            bad.append(f"{z.zone_id} net {net} ∉ [{z.net_area_min_m2},{z.net_area_max_m2}]")
    rep.add("P4", "room area tolerance", not bad, "; ".join(bad) or "all zones within net range")

    # -------- P5 min short side + aspect
    bad = []
    for z in fixture.zones:
        if z.zone_id not in rects:
            continue
        nw, nh, _ = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        if min(nw, nh) < z.min_short_side_m - 1e-6:
            bad.append(f"{z.zone_id} short side {min(nw, nh)} < {z.min_short_side_m}")
        aspect = max(nw, nh) / min(nw, nh)
        if aspect > z.max_aspect_ratio + 1e-6:
            bad.append(f"{z.zone_id} aspect {aspect:.2f} > {z.max_aspect_ratio}")
    rep.add("P5", "min short side + aspect", not bad, "; ".join(bad) or "all zones proportionate")

    # -------- P6 wall-thickness-aware net area
    net_total = round(sum(net_rect_m(z.zone_id, rects[z.zone_id], walls)[2]
                          for z in fixture.zones if z.zone_id in rects), 3)
    eff = round(net_total / gross, 4)
    issues = []
    if not (EFFICIENCY_BAND[0] <= eff <= EFFICIENCY_BAND[1]):
        issues.append(f"net/gross {eff} outside {EFFICIENCY_BAND}")
    for z in fixture.zones:
        if z.is_safe_room and z.zone_id in rects:
            sides = {s: walls[(z.zone_id, s)] for s in Side}
            if any(v is not WallType.RC_SAFE_ROOM for v in sides.values()):
                issues.append(f"{z.zone_id} not RC on all sides: "
                              + ",".join(f"{k.value}={v.value}" for k, v in sides.items()))
            _, _, net = net_rect_m(z.zone_id, rects[z.zone_id], walls)
            if net < z.net_area_min_m2 - 1e-6:
                issues.append(f"{z.zone_id} net {net} below regulated minimum {z.net_area_min_m2}")
    rep.add("P6", "wall-thickness-aware net area", not issues,
            "; ".join(issues) or f"net {net_total} m² / gross {gross} m² = {eff}")
    rep.facts["net_m2"] = f"{net_total}"
    rep.facts["gross_m2"] = f"{gross}"
    rep.facts["efficiency"] = f"{eff}"

    # -------- P7 required adjacency / access
    bad = []
    for e in fixture.access.edges:
        ra, rb = rects.get(e.a), rects.get(e.b)
        if ra is None or rb is None:
            bad.append(f"{e.a}-{e.b}: zone missing")
            continue
        shared_m = u_to_m(ra.shared_edge_len_u(rb))
        if e.kind is ConnectionKind.OPEN_CONNECTION:
            g = fixture.open_group_of(e.a)
            if not g or e.b not in g:
                bad.append(f"{e.a}-{e.b}: OPEN_CONNECTION but not in one open group")
            elif shared_m <= 0:
                bad.append(f"{e.a}-{e.b}: OPEN_CONNECTION with no shared boundary")
        elif shared_m + 1e-6 < e.min_clear_m:
            bad.append(f"{e.a}-{e.b}: shared {shared_m} m < required {e.min_clear_m} m")
    rep.add("P7", "required adjacency / access", not bad,
            "; ".join(bad) or f"all {len(fixture.access.edges)} desired edges realizable")

    # -------- P8 open plan without artificial doors
    openings = generate_openings(fixture, res)
    wanted = [e for e in fixture.access.edges if e.kind is not ConnectionKind.OPEN_CONNECTION]
    issues = []
    if len(openings) != len(wanted):
        issues.append(f"{len(openings)} openings generated for {len(wanted)} non-open edges")
    for o in openings:
        side = _side_between(rects[o.a], rects[o.b])
        if side and walls.get((o.a, side)) is WallType.OPEN:
            issues.append(f"opening {o.a}-{o.b} sits on a WALL-LESS boundary")
    for g in fixture.open_groups:
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                if any({o.a, o.b} == {g[i], g[j]} for o in openings):
                    issues.append(f"artificial door inside open group: {g[i]}-{g[j]}")
    rep.add("P8", "open plan without artificial doors", not issues,
            "; ".join(issues) or f"{len(openings)} openings, 0 inside any open group")

    # -------- P9 declared seams are real
    issues = []
    for wing in fixture.wings:
        for zid, side in wing.seam_leaf_sides:
            r = rects[zid]
            side_len = r.h if side in (Side.E, Side.W) else r.w
            abutting = sum(r.shared_edge_len_u(o) for k, o in rects.items()
                           if k != zid and _side_between(r, o) is side)
            if abutting != side_len:
                issues.append(
                    f"{wing.wing_id}.{zid}.{side.value}: {u_to_m(abutting)}/{u_to_m(side_len)} m "
                    f"abutted — PARTIAL seam, wall type is ambiguous on this side"
                )
    rep.add("P9", "declared wing seams are real", not issues,
            "; ".join(issues) or "every declared seam side fully abuts another wing")

    # -------- P10 clear-width continuity through a corridor joint (Fable review §4 patch 3)
    # Generic, not F4-specific: for every pair of CIRCULATION-roled leaves in the same open
    # group that actually touch, their NET dimension along the joint must match. Vacuously
    # passes on F1-F3 (no open_group there contains 2+ circulation leaves).
    issues = []
    checked = 0
    for group in fixture.open_groups:
        circ_members = [g for g in group
                        if g in rects and any(r in _CIRCULATION_ROLES for r in fixture.zone(g).roles)]
        for i in range(len(circ_members)):
            for j in range(i + 1, len(circ_members)):
                a, b = circ_members[i], circ_members[j]
                ra, rb = rects[a], rects[b]
                if ra.shared_edge_len_u(rb) <= 0:
                    continue
                checked += 1
                side = _side_between(ra, rb)
                na = net_rect_m(a, ra, walls)
                nb = net_rect_m(b, rb, walls)
                if side in (Side.N, Side.S):  # stacked -> the joint runs along the width
                    da, db, axis = na[0], nb[0], "width"
                else:  # side by side -> the joint runs along the height/depth
                    da, db, axis = na[1], nb[1], "depth"
                if abs(da - db) > TOL_M:
                    issues.append(f"{a}/{b} corridor joint {axis} mismatch: {da} vs {db} m")
    rep.add("P10", "clear-width continuity through corridor joint", not issues,
            "; ".join(issues) or (f"{checked} corridor joint(s) continuous" if checked else "n/a — no multi-leaf circulation group"))

    # -------- P11 per-role minimum furniture envelope (Fable review §6 patch 4 — a feasibility
    # SCREEN via bounding-box inscribe test, NOT a placement engine)
    bad = []
    skipped = []
    for z in fixture.zones:
        if z.zone_id not in rects:
            continue
        nw, nh, _ = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        fits = furniture_envelope_fits(z, nw, nh)
        if fits is None:
            skipped.append(z.zone_id)
            continue
        if not fits:
            ew, ed = min_furniture_envelope_m(z)
            bad.append(f"{z.zone_id} net {nw:.2f}x{nh:.2f} m cannot inscribe {ew}x{ed} m envelope")
    rep.add("P11", "per-role minimum furniture envelope", not bad,
            "; ".join(bad) or f"all furnished zones fit (not furnished here: {', '.join(skipped) or 'none'})")

    # -------- CORRECTION 3 check (not a geometry proof, a model-discipline one)
    unclassified = [o.region_id for o in fixture.outdoor if not o.is_classified]
    rep.facts["outdoor_regions"] = ", ".join(
        f"{o.region_id}={o.classification.value}" for o in fixture.outdoor) or "none"
    rep.facts["unclassified_remainders"] = ", ".join(unclassified) or "none"

    rep.facts["wall_iterations"] = str(res.wall_iterations)
    return rep
