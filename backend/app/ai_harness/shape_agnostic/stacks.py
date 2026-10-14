"""The 2D wing, minimal form (ADR-001 path B, first half; #197 day 4+): a STACK — two small rooms
one above the other inside one band column, sharing the column's width and splitting its depth.

Why: in the band family every room spans its band's full depth, so a 5 m² toilet in a 3.6 m deep
bedroom band becomes a 1.4 m strip and the bathroom beside it another; the band's depth is set by
the bedrooms and the small rooms pay for it in proportion (`DAY-3-objective-and-stop.md` §3 — the
tie is structural, not the objective's). A stack gives the two small rooms ONE column of the band
and their own depths. Nothing names a shape; a stack is a property of two rooms, not of a footprint.

How it travels: the embedding sees a stack as one pseudo-zone (`merge_stack`), so `embed_band`,
the SELECTION screen and the alignment rule are untouched; the exact sizer expands it into its
members (`milp_oracle` with `stacks=`), sizing each member's own height under the band's; the
geometry expands the pseudo-cell's rectangle into two (`expand_rects`); the realizer sees two
ordinary cells and the stack column as its own wing (`expand_wings`) so C22's one-wall-type-per-side
rule holds on every side it declares.
"""
from __future__ import annotations

from dataclasses import replace

from app.vertical_slice.geometry_core.model import ProgramRole, Rect

#: Circulation and the safe room never stack (a foyer must front the street; a safe room sits on
#: the envelope behind RC walls). Everything else may, in three tiers tried in order: the wet and
#: service rooms a band's depth wastes most, then the public rooms (KITCHEN over DINING beside a
#: LIVING that then gets a deep band), then bedroom pairs (at a band's end, so both keep an
#: exterior wall — the exposure screen and C19 decide, not this list).
STACK_MAX_TARGET_M2 = 32.0
WET_ROLES = frozenset({ProgramRole.BATHROOM, ProgramRole.TOILET, ProgramRole.STORAGE})
PUBLIC_ROLES = frozenset({ProgramRole.KITCHEN, ProgramRole.DINING})
BED_ROLES = frozenset({ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM})
STACKABLE_ROLES = WET_ROLES | PUBLIC_ROLES | BED_ROLES
PSEUDO_PREFIX = "STACK:"


def _tier(role) -> int:
    return 0 if role in WET_ROLES else 1 if role in PUBLIC_ROLES else 2


def propose_stacks(zones: dict, edges) -> list[tuple[str, str]]:
    """Candidate stacks, most plausible first: pairs of stackable rooms of the same tier (wet, then
    public, then bedrooms), those sharing a neighbour (one column serves both doors) before those
    that do not. Each pair is returned once per vertical order (top, bottom) — the sizer decides
    nothing about order, the embedding does."""
    small = sorted(z for z, zi in zones.items()
                   if getattr(zi, "role", None) in STACKABLE_ROLES and zi.target_area_m2 <= STACK_MAX_TARGET_M2)
    nbrs: dict[str, set[str]] = {z: set() for z in zones}
    for a, b in edges:
        nbrs[a].add(b); nbrs[b].add(a)
    pairs = []
    for i, a in enumerate(small):
        for b in small[i + 1:]:
            ta, tb = _tier(zones[a].role), _tier(zones[b].role)
            if ta != tb:
                continue                                   # a pair stacks within its own tier
            shared = len(nbrs[a] & nbrs[b])
            pairs.append((ta, -shared, a, b))
    out: list[tuple[str, str]] = []
    for _, _, a, b in sorted(pairs):
        out.append((a, b)); out.append((b, a))
    return out


def pseudo_id(stack: tuple[str, ...]) -> str:
    return PSEUDO_PREFIX + "+".join(stack)


def merge_stack(zones: dict, edges, access, stack: tuple[str, ...]):
    """The programme with `stack`'s members replaced by one pseudo-zone whose contacts are the
    union of theirs (an edge between members disappears — they touch by construction). Its bounds
    are only for the embedding and the screens: the sizer never applies them, it sizes the members.
    Returns (zones, edges, access, pseudo_id)."""
    pid = pseudo_id(stack)
    members = [zones[z] for z in stack]
    pseudo = replace(members[0], zone_id=pid,
                     target_area_m2=sum(m.target_area_m2 for m in members),
                     min_area_m2=sum(m.min_area_m2 for m in members),
                     max_area_m2=sum(m.max_area_m2 for m in members),
                     min_short_side_m=max(m.min_short_side_m for m in members),
                     max_aspect_ratio=max(4.0, max(m.max_aspect_ratio for m in members)))
    z2 = {z: zi for z, zi in zones.items() if z not in stack}
    z2[pid] = pseudo

    def remap(pairs):
        seen, out = set(), []
        for a, b in pairs:
            a2 = pid if a in stack else a
            b2 = pid if b in stack else b
            if a2 == b2:
                continue
            key = frozenset((a2, b2))
            if key in seen:
                continue
            seen.add(key); out.append((a2, b2))
        return out
    return z2, remap(edges), remap(access), pid


def expand_rects(rects: dict[str, Rect], stacks: dict[str, tuple[str, ...]], heights_u: dict[str, int]) -> dict[str, Rect]:
    """Each pseudo-cell's rectangle split top-to-bottom into its members at the sizer's heights."""
    out = {}
    for zid, r in rects.items():
        if zid not in stacks:
            out[zid] = r; continue
        y = r.y
        for m in stacks[zid]:
            h = heights_u[m]
            out[m] = Rect(r.x, y, r.w, h); y += h
        assert y == r.y2, (zid, heights_u, r)
    return out


def expand_wings(wing_rects, rects: dict[str, Rect], stacks: dict[str, tuple[str, ...]]):
    """Every stack column becomes its own wing and the band wing it sat in splits around it, so a
    wing's declared seams are each abutted in full (C22). `rects` holds the pseudo-cells (before
    `expand_rects`)."""
    out = []
    for w in wing_rects:
        cols = sorted(rects[p] for p in stacks if w.x <= rects[p].x and rects[p].x2 <= w.x2
                      and w.y <= rects[p].y and rects[p].y2 <= w.y2)
        if not cols:
            out.append(w); continue
        x = w.x
        for c in cols:
            if c.x > x:
                out.append(Rect(x, w.y, c.x - x, w.h))
            out.append(Rect(c.x, w.y, c.w, w.h))
            x = c.x2
        if x < w.x2:
            out.append(Rect(x, w.y, w.x2 - x, w.h))
    return tuple(out)
