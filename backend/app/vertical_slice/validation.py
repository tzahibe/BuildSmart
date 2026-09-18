"""Stage 8 — Validation.

Aggregates the checks the review's acceptance list named, reusing the geometry-core spike's
PROVEN proof logic (P1-P11) wherever the same question applies to solved production rects, and
adding the ones the spike explicitly did not attempt: a real accessibility-graph reachability
check (closing part of the "RealizedAccessGraph" gap the Fable review's §5 flagged — this
vertical slice does not build a full graph type, but it does verify the graph-level property:
every room is reachable from the entrance), door/window placeability, and the two site checks
(parking-to-street, entrance-to-house).

Returns one `ValidationReport`: a flat, ordered list of named checks with pass/fail + detail,
in the same spirit as `spikes/geometry_core/validate.py`'s `Report`, but this is production
code, not a pytest fixture-proof — it is meant to be read by a caller deciding whether to
accept the candidate, not just asserted on in a test.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import access_rules
from . import footprint as footprint_module
from .concept_generator import ROOM_TEMPLATES
from .doors import Door
from .exposure_policy import REQUIRED_EXTERIOR_ROLES
from .furniture import FurnitureCheck
from .geometry_adapter import envelope_sides
from .geometry_core.engine import WallMap, net_rect_m
from .geometry_core.model import (
    ConnectionKind,
    Fixture,
    ProgramRole,
    OutdoorClassification,
    Rect,
    Side,
    WallType,
    leaves_of,
    u_to_m,
)
from .site import SitePlan
from .spec import CorridorRequirement, WetRoomKind
from .wet_rooms import ResolvedWetRoom
from .windows import DAYLIGHT_ROLES, Window, seam_sides_of

TOL_M2 = 0.01

_OPPOSITE_SIDE = {Side.N: Side.S, Side.S: Side.N, Side.E: Side.W, Side.W: Side.E}


@dataclass(frozen=True)
class RealizedConnection:
    """A physically traversable connection, evidenced by the built geometry.

    THE INVARIANT THIS TYPE EXISTS FOR: a declared access edge is never treated as realized
    because the graph contains it. The realized plan — walls, openings and generated doors — is
    the source of truth for physical accessibility.
    """

    a: str
    b: str
    kind: str      # "DOOR" | "OPEN"
    evidence: str


def realized_connections(rects: dict[str, Rect], walls: WallMap,
                         interior_doors: list[Door]) -> list[RealizedConnection]:
    """Every traversable connection the BUILT geometry actually provides.

    Two, and only two, forms of physical evidence are accepted:

      * a generated door or cased opening that is placeable — an unplaceable one is a hole that
        does not fit, so it carries no traffic;
      * a shared boundary whose facing wall sides are BOTH `OPEN` — a genuine wall-less join.

    Anything a declared edge asserts beyond these is intent, not fact.
    """
    out: list[RealizedConnection] = []
    for door in interior_doors:
        if door.placeable and door.shared_length_m > 0:
            out.append(RealizedConnection(
                door.a, door.b, "DOOR",
                f"{door.kind.value.lower()} {door.width_m} m on a "
                f"{door.shared_length_m:.2f} m shared wall"))

    ids = sorted(rects)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            ra, rb = rects[a], rects[b]
            if ra.shared_edge_len_u(rb) <= 0:
                continue
            side = _side_between(ra, rb)
            if side is None:
                continue
            if (walls.get((a, side)) is WallType.OPEN
                    and walls.get((b, _OPPOSITE_SIDE[side])) is WallType.OPEN):
                out.append(RealizedConnection(
                    a, b, "OPEN",
                    f"wall-less join over {u_to_m(ra.shared_edge_len_u(rb)):.2f} m"))
    return out


@dataclass
class Check:
    check_id: str
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, check_id: str, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(check_id, name, passed, detail))

    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


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


def realized_corridor_width_m(fixture: Fixture, rects: dict[str, Rect],
                              walls: WallMap) -> float | None:
    """The NET width of the realized circulation zone, in metres — measured, never assumed.

    A corridor is the narrow dimension of its own rectangle after wall insets, so this reports the
    short side. With several circulation zones (a hall split across a parti) the NARROWEST is what
    a person actually has to walk through, so that is what is reported.
    """
    widths = []
    for zone in fixture.zones:
        if ProgramRole.CIRCULATION not in zone.roles and ProgramRole.HALL not in zone.roles:
            continue
        if zone.zone_id not in rects:
            continue
        nw, nh, _ = net_rect_m(zone.zone_id, rects[zone.zone_id], walls)
        widths.append(min(nw, nh))
    return min(widths) if widths else None


def validate(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
             interior_doors: list[Door], entrance_door: Door, windows: list[Window],
             furniture: list[FurnitureCheck], site: SitePlan,
             corridor: CorridorRequirement | None = None,
             relationships: tuple = (),
             wet_rooms: tuple[ResolvedWetRoom, ...] = (),
             entry_seed: str = "OUTSIDE",
             skip_site_checks: bool = False) -> ValidationReport:
    """`entry_seed`/`skip_site_checks` (multi-level Phase 1, additive): a level with no street —
    an upper storey, entered by its `VerticalCore` — seeds C5 from the core's zone id instead of
    `OUTSIDE` (which the fixture does not have) and does not run the SITE checks (C10-C12, C16,
    C18) at all, rather than trusting a synthetic site plan to pass them.

    BOTH DEFAULT TO TODAY'S SINGLE-LEVEL BEHAVIOUR EXACTLY: a caller that passes neither gets the
    identical seed and the identical set of checks it always got. `ONLY CHECKS THAT ACTUALLY RUN
    APPEAR IN THE REPORT` (the same discipline `building_validation.py` states for its own V
    checks) — a skipped site check is simply absent, never reported as an unearned pass.
    """
    rep = ValidationReport()

    # C1 — no overlap
    ids = sorted(rects)
    worst, pair = 0, ""
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            ov = rects[ids[i]].overlap_area_u(rects[ids[j]])
            if ov > worst:
                worst, pair = ov, f"{ids[i]}/{ids[j]}"
    rep.add("C1", "no overlap between rooms", worst == 0, "none" if worst == 0 else f"{pair} overlap")

    # C2 — no residual interior area (the whole footprint is fully consumed by rooms). The
    # footprint is its WINGS' area, not the bounding box's: the crook of an L is outside.
    covered = sum(r.w * r.h for r in rects.values())
    footprint_area_u = footprint_module.area_u(site.wings)
    rep.add("C2", "no residual interior area", covered == footprint_area_u,
            "footprint fully consumed by rooms" if covered == footprint_area_u
            else f"{footprint_area_u - covered} unit^2 unassigned inside the footprint")

    # C3 — room areas and dimensions valid
    bad = []
    for z in fixture.zones:
        if z.zone_id not in rects:
            continue
        nw, nh, na = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        if not (z.net_area_min_m2 - TOL_M2 <= na <= z.net_area_max_m2 + TOL_M2):
            bad.append(f"{z.zone_id} net {na} m2 outside [{z.net_area_min_m2},{z.net_area_max_m2}]")
        if min(nw, nh) < z.min_short_side_m - 1e-6:
            bad.append(f"{z.zone_id} short side {min(nw, nh):.2f} < {z.min_short_side_m}")
        aspect = max(nw, nh) / min(nw, nh)
        if aspect > z.max_aspect_ratio + 1e-6:
            bad.append(f"{z.zone_id} aspect {aspect:.2f} > {z.max_aspect_ratio}")
    rep.add("C3", "room areas and dimensions valid", not bad, "; ".join(bad) or "all zones within spec")

    # C20 — realized rooms within their TEMPLATE's aspect ratio. (C19 is now the exterior-exposure
    # check below — Issue #19; the guest-WC access semantics of specs/009, if implemented, need a
    # different free code.)
    #
    # C3 holds every zone to its own ZoneSpec, and the ZoneSpec is authored by the same planner
    # that drew the rectangle. For a long time the planner set `max_aspect_ratio` to whatever the
    # rectangle it had just planned needed (+0.3), so C3 could not fail on shape BY CONSTRUCTION:
    # a 6.1 x 1.2 m WC arrived with a 5.38 ceiling and passed. This check never reads the ZoneSpec.
    # The ceiling is the role's `ROOM_TEMPLATES` entry, so a candidate that relaxes its own spec —
    # now or in some future sizing path — still cannot put a strip in front of a person.
    # Circulation is excluded on purpose: a corridor is a strip by definition, and its width is
    # what C14 measures. A role with no template row (ENTRANCE) has no shape rule to hold it to.
    bad = []
    for z in fixture.zones:
        if z.zone_id not in rects or {ProgramRole.HALL, ProgramRole.CIRCULATION} & set(z.roles):
            continue
        template = ROOM_TEMPLATES.get(z.primary_role)
        if template is None:
            continue
        nw, nh, _ = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        aspect = max(nw, nh) / max(min(nw, nh), 1e-6)
        if aspect > template.max_aspect_ratio + 1e-6:
            bad.append(f"{z.zone_id} realized {nw:.2f} x {nh:.2f} m (aspect {aspect:.2f}) past its "
                       f"{z.primary_role.value} template's {template.max_aspect_ratio}")
    rep.add("C20", "realized rooms within their template's aspect ratio", not bad,
            "; ".join(bad) or "no room is a strip")

    # C21 — realized rooms within their TEMPLATE's maximum area. The area twin of C20, for the
    # same reason: C3 holds a room to a ZoneSpec the planner wrote around the rectangle it had
    # just planned, so a planner that lets a bathroom reach 62 m2 (measured, front band, lone row
    # in a rear column) also wrote it a 105 m2 ceiling and C3 passed. `_zone_spec` now caps the
    # ZoneSpec at the template, but this check never reads the ZoneSpec — a future sizing path
    # that relaxes its own spec still cannot put an oversized room in front of a person. Read on
    # NET area, which is what the templates are written against. Circulation is excluded as in
    # C20 (the hub carries `HUB_TEMPLATE`, not the HALL row, and C14 governs a corridor); FLEX is
    # the zone that exists to absorb what the programme cannot, and its 500 m2 row says so.
    bad = []
    for z in fixture.zones:
        if z.zone_id not in rects or {ProgramRole.HALL, ProgramRole.CIRCULATION} & set(z.roles):
            continue
        template = ROOM_TEMPLATES.get(z.primary_role)
        if template is None:
            continue
        _, _, na = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        # The HARD maximum (`RoomTemplate.hard_max`): the preferred one is a quality target the
        # planner sizes to and the contract reports on, not a gate.
        if na > template.hard_max + TOL_M2:
            bad.append(f"{z.zone_id} realized {na:.2f} m2 past its {z.primary_role.value} "
                       f"template's {template.hard_max:.0f} m2 hard maximum")
    rep.add("C21", "realized rooms within their template's hard maximum area", not bad,
            "; ".join(bad) or "no room above its hard maximum")

    # C4 — safe room valid under current RuleSet parameters
    bad = []
    for z in fixture.zones:
        if not z.is_safe_room or z.zone_id not in rects:
            continue
        sides = {s: walls[(z.zone_id, s)] for s in Side}
        if any(v is not WallType.RC_SAFE_ROOM for v in sides.values()):
            bad.append(f"{z.zone_id} not RC on all sides: " + ",".join(f"{k.value}={v.value}" for k, v in sides.items()))
        _, _, na = net_rect_m(z.zone_id, rects[z.zone_id], walls)
        if na < z.net_area_min_m2 - 1e-6:
            bad.append(f"{z.zone_id} net {na} below regulated minimum {z.net_area_min_m2}")
    rep.add("C4", "safe room valid (RC envelope + regulated minimum)", not bad, "; ".join(bad) or "safe room compliant")

    # C5 — all required spaces accessible, over the REALIZED graph.
    #
    # This used to traverse `fixture.access.edges` — the DECLARED topology — and therefore
    # reported a room reachable whenever the graph said so, even with a solid wall in the way.
    # It now walks only connections the built geometry actually provides, so a declared edge can
    # no longer make anything reachable by assertion.
    realized = realized_connections(rects, walls, interior_doors)
    graph: dict[str, set[str]] = {}
    for connection in realized:
        graph.setdefault(connection.a, set()).add(connection.b)
        graph.setdefault(connection.b, set()).add(connection.a)
    if entry_seed == "OUTSIDE" and entrance_door.placeable:
        graph.setdefault("OUTSIDE", set()).add(entrance_door.b)
        graph.setdefault(entrance_door.b, set()).add("OUTSIDE")
    seen = {entry_seed}
    frontier = [entry_seed]
    while frontier:
        cur = frontier.pop()
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    all_zones = {z.zone_id for z in fixture.zones}
    unreachable = sorted(all_zones - seen)
    seed_note = "" if entry_seed == "OUTSIDE" else f" (seeded from {entry_seed})"
    rep.add("C5", "all required spaces physically reachable from the entrance", not unreachable,
            "; ".join(unreachable) or
            f"all {len(all_zones)} zones reachable over {len(realized)} realized connections{seed_note}")

    # C24 — access topology obeys the door rules (access_rules.py): every enclosed room has a
    # declared door, every declared edge's role pair is one the table allows (which is what rules
    # out a PRIVATE-to-PRIVATE door except an ensuite's own bedroom), and no room is reachable
    # from the entrance only by continuing on through another PRIVATE room — the last of these
    # walked over the same REALIZED `graph` C5 just built, not the declared topology, so a wall
    # accidentally typed OPEN between two rooms cannot create a silent chain either.
    access_defects = access_rules.check_access_topology(fixture, graph, entry_seed)
    rep.add("C24", "access topology obeys the door rules", not access_defects,
            "; ".join(access_defects) or "every enclosed room has a proper door from an allowed "
                                         "role, no private-to-private chain")

    # C6 — no artificial doors in open-plan
    open_pairs = {frozenset((e.a, e.b)) for e in fixture.access.edges if e.kind is ConnectionKind.OPEN_CONNECTION}
    bad = [f"{d.a}-{d.b}" for d in interior_doors if frozenset((d.a, d.b)) in open_pairs]
    for group in fixture.open_groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                pair = frozenset((group[i], group[j]))
                if any(frozenset((d.a, d.b)) == pair for d in interior_doors):
                    bad.append(f"artificial door inside open group: {group[i]}-{group[j]}")
    rep.add("C6", "no artificial doors in open-plan", not bad, "; ".join(bad) or "open-plan clean")

    # C7 — doors physically placeable
    bad = [f"{d.a}-{d.b} shared {d.shared_length_m:.2f} m too short for a {d.width_m} m door"
           for d in interior_doors if not d.placeable]
    if not entrance_door.placeable:
        bad.append("entrance door not placeable on the street-facing wall")
    rep.add("C7", "doors physically placeable", not bad, "; ".join(bad) or f"{len(interior_doors) + 1} doors placeable")

    # C19 — required rooms touch an exterior wall (exposure_policy.py, Issue #19). A GEOMETRIC
    # fact only (`envelope_sides`), deliberately separate from C8 below: this is a planning-
    # topology error (the room was placed with no exterior wall at all) rather than a
    # window-sizing error (an exterior wall too short for the minimum window), and runs first so
    # a refusal names the real cause. Fails closed, like C8.
    seams = seam_sides_of(fixture)
    exterior_required = {z.zone_id for z in fixture.zones if set(z.roles) & REQUIRED_EXTERIOR_ROLES}
    interior = []
    for zone_id in sorted(exterior_required):
        rect = rects.get(zone_id)
        if rect is None:
            continue
        sides = envelope_sides(rect, site.footprint, wings=site.wings,
                               seam_sides=seams.get(zone_id, frozenset()))
        if not sides:
            interior.append(f"{zone_id} has no exterior wall (interior room)")
    rep.add("C19", "required rooms touch an exterior wall", not interior,
            "; ".join(interior) or
            f"all {len(exterior_required)} exterior-required zones touch the envelope")

    # C8 — daylight/window exposure present where required
    windowed = {w.zone_id for w in windows if w.placeable}
    required = {z.zone_id for z in fixture.zones if set(z.roles) & DAYLIGHT_ROLES}
    missing = sorted(required - windowed)
    rep.add("C8", "daylight/window exposure present where required", not missing,
            "; ".join(missing) or f"all {len(required)} daylight-requiring zones windowed")

    # C9 — furniture-envelope feasibility
    bad = [f"{f.zone_id} net {f.net_w_m:.2f}x{f.net_h_m:.2f} cannot inscribe {f.envelope_m} m"
           for f in furniture if f.fits is False]
    rep.add("C9", "furniture-envelope feasibility", not bad, "; ".join(bad) or "all furnished zones fit")

    if not skip_site_checks:
        # C10 — parking connected to street (bay's own frontage lies on the plot's street edge)
        bad = [f"parking bay at x={p.x} does not front the street (y={p.y}, plot street at y={site.plot.y})"
               for p in site.parking if p.y != site.plot.y]
        rep.add("C10", "parking connected to street", not bad, "; ".join(bad) or f"{len(site.parking)} bays front the street")

        # C18 — parking bays clear of the house. C10 only proves a bay touches the street; a bay drawn
        # INSIDE the footprint touches it too, and that is exactly what a zero front setback produced —
        # the rooms were painted over the bays and every plan simply had no parking. Fails closed.
        bad = [f"parking bay at x={p.x} overlaps the house by "
               f"{sum(p.overlap_area_u(w) for w in site.wings)} u²"
               for p in site.parking if any(p.overlap_area_u(w) > 0 for w in site.wings)]
        rep.add("C18", "parking bays clear of the house", not bad,
                "; ".join(bad) or f"{len(site.parking)} bays outside the footprint")

        # C11 — pedestrian entrance connected to house
        bad = []
        if not entrance_door.placeable:
            bad.append("entrance door itself is not placeable")
        walk = site.entrance.path_rect
        if walk.y != site.plot.y:
            bad.append("entrance walk does not start at the street edge")
        if walk.y2 != site.footprint.y:
            bad.append("entrance walk does not reach the building line")
        for p in site.parking:
            if walk.overlap_area_u(p) > 0:
                bad.append(f"entrance walk overlaps a parking bay")
        rep.add("C11", "pedestrian entrance connected to house", not bad, "; ".join(bad) or "entrance walk clear, street to door")

        # C12 — garden explicitly classified (Correction 3 discipline carried into the site stage)
        unclassified = [o.region_id for o in site.garden if o.classification is OutdoorClassification.UNCLASSIFIED_REMAINDER]
        rep.add("C12", "outdoor regions explicitly classified", not unclassified,
                "; ".join(unclassified) or f"{len(site.garden)} garden region(s) explicitly classified")

        # C16 — the front door is on the wall of the room it says it opens into.
        #
        # THE HOLE THIS CLOSES. C13 enforces "a declared connection must be physically realized" over
        # the fixture's INTERIOR topology, and the entrance is deliberately not part of that graph — it
        # is resolved at site level. So the one connection nothing checked was the one the whole
        # accessibility graph is rooted at: C5 seeds reachability from `entrance_door.b` purely because
        # the door is `placeable`, which only ever meant "there is wall either side of it". A door drawn
        # in the dining room's exterior wall while claiming to open into a hall 6.7 m away satisfied
        # that, and every room was then reported reachable from a connection that did not exist.
        target = entrance_door.b
        if target not in rects:
            rep.add("C16", "the entrance opens into the room it names", False,
                    f"the entrance door names {target}, which is not a room in this plan")
        else:
            zone = rects[target]
            x, y = entrance_door.center_u
            on_zone_wall = (y == zone.y and zone.x <= x <= zone.x2)
            rep.add("C16", "the entrance opens into the room it names",
                    entrance_door.placeable and on_zone_wall,
                    f"entrance at x={u_to_m(x):.2f} m on the street wall; {target} spans "
                    f"{u_to_m(zone.x):.2f}-{u_to_m(zone.x2):.2f} m"
                    + ("" if on_zone_wall else " — the door is not on that room's wall"))

    # C13 — every DECLARED access edge is physically realized.
    #
    # DesiredAccessTopology is preserved as design INTENT; this check is the comparison between
    # that intent and the geometry actually built. It never repairs anything — it fails loudly
    # with the specific physical reason.
    realized_pairs = {frozenset((c.a, c.b)): c for c in realized}
    unrealized: list[str] = []
    for edge in fixture.access.edges:
        pair = frozenset((edge.a, edge.b))
        if pair in realized_pairs:
            continue
        ra, rb = rects.get(edge.a), rects.get(edge.b)
        if ra is None or rb is None:
            unrealized.append(f"{edge.a}-{edge.b} ({edge.kind.value}): zone missing from the plan")
            continue
        shared = ra.shared_edge_len_u(rb)
        if shared <= 0:
            unrealized.append(
                f"{edge.a}-{edge.b} ({edge.kind.value}): the zones share no physical interface, "
                f"so no connection could be built")
            continue
        side = _side_between(ra, rb)
        wall_a = walls.get((edge.a, side)) if side else None
        if edge.kind is ConnectionKind.OPEN_CONNECTION:
            unrealized.append(
                f"{edge.a}-{edge.b} (OPEN_CONNECTION): blocked by a "
                f"{wall_a.value if wall_a else 'unknown'} wall over their "
                f"{u_to_m(shared):.2f} m shared boundary — declared open, physically walled")
        else:
            unrealized.append(
                f"{edge.a}-{edge.b} ({edge.kind.value}): shares {u_to_m(shared):.2f} m of wall "
                f"but no placeable opening was generated")
    # C14 — the realized corridor actually meets the requested width.
    #
    # It is not enough that ProgramSpec carried corridor_width=1.8: the planner clamps to the 5 cm
    # grid, wall insets eat into the gross rectangle, and a later stage could narrow the hall. This
    # measures the NET width of the realized corridor rectangle and compares it to what was asked
    # for. Skipped entirely when the brief asked for no width, so the default path is unaffected.
    if corridor is not None:
        realized = realized_corridor_width_m(fixture, rects, walls)
        if realized is None:
            rep.add("C14", "corridor meets the requested width", False,
                    "no circulation zone was realized")
        else:
            rep.add("C14", "corridor meets the requested width",
                    corridor.satisfied_by(realized),
                    f"requested {corridor.mode.value} {corridor.width_m:.2f} m, "
                    f"realized {realized:.2f} m")

    # C15 — requested room relationships, measured on the REALIZED geometry.
    #
    # Not the declared concept graph: a plan is checked on the walls and doors it actually has, so
    # ADJACENT means a real shared wall and NOT_ADJACENT means no shared wall anywhere. Only HARD
    # relationships gate the plan; preferences are reported by the pipeline as warnings and never
    # fail a plan that is otherwise valid.
    if relationships:
        from .relationships import evaluate as _evaluate_relationships
        outcomes = _evaluate_relationships(
            fixture, rects, realized_connections(rects, walls, interior_doors), relationships)
        broken = [f"{o.statement}: {o.detail}" for o in outcomes if o.is_hard and not o.satisfied]
        rep.add("C15", "requested room relationships are realized", not broken,
                "; ".join(broken) or "every required relationship holds in the built plan")

    rep.add("C13", "declared access topology is physically realized", not unrealized,
            "; ".join(unrealized) or
            f"all {len(fixture.access.edges)} declared edges have a physical connection")

    # C17 — realized bathroom access matches the AUTHORITATIVE requirements (specs/007 FR-9).
    #
    # `wet_rooms` are the brief's wet-room kinds as the programme resolved them: which zone, what
    # kind, and — for an ensuite — which bedroom. This check compares the doors that were BUILT to
    # that. It never reads intent off the geometry: a bathroom that happens to be entered from a
    # bedroom is a failure against a SHARED_BATHROOM requirement, not evidence of an ensuite.
    #
    # FAILS CLOSED. A wet zone the requirements do not cover, a requirement naming a zone the plan
    # does not have, or no requirements at all for a plan that has wet rooms — every one of these
    # is a failure, never a pass by absence. Whatever candidate won and however ranking may change,
    # a drawing cannot contradict what the person was told about their bathrooms.
    bad = []
    circulation = {z.zone_id for z in fixture.zones
                   if {ProgramRole.HALL, ProgramRole.CIRCULATION} & set(z.roles)}
    wet_zones = {z.zone_id for z in fixture.zones
                 if {ProgramRole.BATHROOM, ProgramRole.TOILET} & set(z.roles)}
    covered = {w.zone_id for w in wet_rooms}
    for zone_id in sorted(wet_zones - covered):
        bad.append(f"{zone_id}: kind unknown — no requirement covers it")
    for w in wet_rooms:
        if w.zone_id not in rects:
            bad.append(f"{w.zone_id}: required but not in the plan")
            continue
        entered_from = sorted({d.a if d.b == w.zone_id else d.b for d in interior_doors
                               if w.zone_id in (d.a, d.b)})
        if w.kind is WetRoomKind.ENSUITE:
            expected = f"only from {w.host_zone}"
            ok = entered_from == [w.host_zone]
        else:
            expected = "only from circulation"
            ok = len(entered_from) == 1 and entered_from[0] in circulation
        if not ok:
            bad.append(f"{w.zone_id} ({w.kind.value}): entered from "
                       f"{', '.join(entered_from) or 'nothing'}, required {expected}")
    rep.add("C17", "bathroom access matches the requirements", not bad,
            "; ".join(bad) or f"all {len(wet_rooms)} wet rooms entered as required")

    # C22 — declared wing seams are real (the spike's proof P9, ported). Multi-wing fixtures only:
    # a one-wing house has no seam to prove, and a check that did not run makes no claim — which
    # is also what keeps every one-wing report and payload exactly as it was.
    if len(fixture.wings) > 1:
        bad = _seam_defects(fixture, rects, walls, windows, realized)
        seams = sum(len(w.seam_leaf_sides) for w in fixture.wings)
        rep.add("C22", "declared wing seams are real (P9)", not bad,
                "; ".join(bad) or f"{seams} declared seam sides abut the other wing in full, none "
                                  f"exterior or glazed; {len(fixture.wings)} wings joined by a "
                                  f"realized connection; every room inside its wing")

    return rep


def _seam_defects(fixture: Fixture, rects: dict[str, Rect], walls: WallMap,
                  windows: list[Window], realized: list[RealizedConnection]) -> list[str]:
    """Every way a two-wing fixture's seam can be a lie, as a list of defects (empty = P9 holds).

    A DECLARED seam side must be geometrically real: the leaf's side lies on its own wing's
    boundary, and leaves of ANOTHER wing abut it along its WHOLE length — a partial abutment is
    the spike's L2 defect, a side that is part exterior and part seam with no single wall type.
    The solver typed it as a partition, so it may carry no exterior semantics: not `EXTERIOR`, and
    no window. An UNDECLARED abutment — a leaf side on its wing's boundary that touches another
    wing without being declared — would be typed exterior against a room, so it is a defect too.
    The wings must be one house: at least one realized connection joins zones of different wings
    (an access edge that merely crosses the seam on paper is not that). And every room lies
    inside the wing whose tree placed it.
    """
    wing_of_zone: dict[str, int] = {}
    for index, wing in enumerate(fixture.wings):
        for zone_id in leaves_of(wing.tree):
            wing_of_zone[zone_id] = index
    wing_rects = [w.rect() for w in fixture.wings]
    declared = {(zone_id, side) for wing in fixture.wings for zone_id, side in wing.seam_leaf_sides}
    glazed = {(w.zone_id, w.side) for w in windows if w.width_m > 0 and w.placeable}
    defects: list[str] = []

    def on_wing_boundary(rect: Rect, wing: Rect, side: Side) -> bool:
        return {Side.W: rect.x == wing.x, Side.E: rect.x2 == wing.x2,
                Side.N: rect.y == wing.y, Side.S: rect.y2 == wing.y2}[side]

    def other_wing_abutment_u(zone_id: str, rect: Rect, side: Side) -> int:
        return sum(rect.shared_edge_len_u(other) for other_id, other in rects.items()
                   if other_id != zone_id and wing_of_zone.get(other_id) != wing_of_zone[zone_id]
                   and _side_between(rect, other) is side)

    for zone_id, rect in rects.items():
        if zone_id not in wing_of_zone:
            defects.append(f"{zone_id} belongs to no wing's tree")
            continue
        wing = wing_rects[wing_of_zone[zone_id]]
        if not (wing.x <= rect.x and rect.x2 <= wing.x2 and wing.y <= rect.y and rect.y2 <= wing.y2):
            defects.append(f"{zone_id} {rect} lies outside its wing {wing}")
            continue
        for side in Side:
            side_len = rect.h if side in (Side.E, Side.W) else rect.w
            abutting = other_wing_abutment_u(zone_id, rect, side)
            if (zone_id, side) in declared:
                if not on_wing_boundary(rect, wing, side):
                    defects.append(f"{zone_id}.{side.value} declared a seam but not on its wing's boundary")
                if abutting != side_len:
                    defects.append(f"{zone_id}.{side.value}: {u_to_m(abutting)}/{u_to_m(side_len)} m "
                                   f"abutted by the other wing — PARTIAL seam, wall type ambiguous")
                if walls[(zone_id, side)] is WallType.EXTERIOR:
                    defects.append(f"{zone_id}.{side.value} is a seam typed EXTERIOR")
                if (zone_id, side) in glazed:
                    defects.append(f"{zone_id}.{side.value} is a seam carrying a window")
            elif abutting > 0 and on_wing_boundary(rect, wing, side):
                defects.append(f"{zone_id}.{side.value} abuts the other wing for {u_to_m(abutting)} m "
                               f"but is not declared a seam")

    crossings = [c for c in realized
                 if c.a in wing_of_zone and c.b in wing_of_zone
                 and wing_of_zone[c.a] != wing_of_zone[c.b]]
    if not crossings:
        defects.append("no realized connection joins the wings — two buildings, not one house")
    return defects
