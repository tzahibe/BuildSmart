"""Wet-room access semantics: from the brief's kinds to rooms, and the invariants those rooms must satisfy.

The kinds (`spec.WetRoomKind`) say who reaches each wet room. `resolve_wet_rooms` turns the
brief's kinds into the rooms the programme builds; `check_wet_room_invariants` asks whether that
programme is one anybody should be handed — and if not, says exactly what is missing so the
person can answer. It decides nothing for them.

    I1  If any wet room is UNSPECIFIED, the programme keeps at least one SHARED_BATHROOM.
        A WC does not satisfy it: the unstated room's job is to be the bathroom anyone can use.
    I2  A GUEST_WC is entered from circulation.
    I3  An ENSUITE is entered only from its host bedroom.
    I4  If no wet room is shared and none is unspecified — the person named every one — then every
        bedroom must host an ensuite. Otherwise a bedroom has no bathroom it can reach, and that is
        a QUESTION for the person (decision A of specs/007), never a warning on a delivered plan.

I1–I3 cannot be broken by the resolver's own defaults; they guard edits, stored records and any
future default. I4 is the one a brief can genuinely produce ("חדר הורים עם מקלחת, שירותי אורחים",
two bedrooms).
"""
from __future__ import annotations

from dataclasses import dataclass

from .spec import (
    ENSUITE_HOST_BEDROOM,
    ENSUITE_HOST_MASTER,
    ProgramSpec,
    WetRoomKind,
    WetRoomRequirement,
    WetRoomStrength,
)


@dataclass(frozen=True)
class WetRoomProblem:
    """One reason the wet-room programme cannot be planned as stated."""

    invariant: str            # "I1" | "I2" | "I3" | "I4" | "RESOLUTION"
    detail: str               # engineering detail, for the failure log
    #: Bedrooms with no bathroom they can reach (I4), by zone id — what the person is asked about.
    bedrooms_without_bathroom: tuple[str, ...] = ()


class WetRoomResolutionError(ValueError):
    """The brief's wet-room kinds cannot be turned into rooms. Raised, never guessed around: more
    kinds than wet rooms, an ensuite for a bedroom the house does not have, or a host token the
    vocabulary does not know. `scope.check_supported` turns it into a refusal before planning."""


@dataclass(frozen=True)
class ResolvedWetRoom:
    """One wet room as the programme will build it: a zone, a kind, and who enters it.

    The authoritative form of the requirement. `kind` is never `UNSPECIFIED` here — an unspecified
    item has been given its default — and `specified` records whether the person or the default
    decided it, so the review screen can say which and C17 can hold the drawing to it.
    """

    zone_id: str
    kind: WetRoomKind
    #: Zone id of the host bedroom for an ENSUITE; `None` for a room entered from circulation.
    host_zone: str | None
    strength: WetRoomStrength
    specified: bool
    source_text: str = ""

    @property
    def entered_from_circulation(self) -> bool:
        return self.host_zone is None


def default_wet_room_kinds(count: int, has_master: bool) -> tuple[WetRoomRequirement, ...]:
    """The kinds a bare COUNT has always meant, in order — today's `build_room_program` rule.

    With two or more wet rooms and a master present, the first is the master's ensuite; the rest
    are shared and entered from circulation.

    NOT every shared wet room is a full bathroom. A house asking for more than one SHARED wet
    room is asking for a family bathroom AND a guest WC — two rooms with different jobs — not
    for the same room twice, and drawing two identical "חדר רחצה" side by side was reported as
    exactly the defect it looks like. So the FIRST shared wet room becomes a TOILET
    ("שירותים"): pan and basin, a shallower row, its own name on the plan. The first, not the
    last, because the guest WC is the one wet room that wants to stay near the entrance.

    The conversion needs TWO OR MORE shared wet rooms, never one: a house whose only shared wet
    room became a WC would have no bathroom anyone but the master could use. So 2 wet rooms with
    a master (ensuite + one shared) still produces two full bathrooms.
    """
    ensuite = 1 if count >= 2 and has_master else 0
    shared = count - ensuite
    kinds: list[WetRoomRequirement] = []
    if ensuite:
        kinds.append(WetRoomRequirement(WetRoomKind.ENSUITE, ENSUITE_HOST_MASTER))
    for i in range(shared):
        kind = WetRoomKind.GUEST_WC if (i == 0 and shared >= 2) else WetRoomKind.SHARED_BATHROOM
        kinds.append(WetRoomRequirement(kind))
    return tuple(kinds)


def resolve_wet_rooms(program: ProgramSpec) -> tuple[ResolvedWetRoom, ...]:
    """The brief's wet-room kinds -> the rooms the programme builds, in order.

    THE COUNT IS THE AUTHORITY on how many. Kinds shorter than the count are padded with
    `UNSPECIFIED`; longer is a defect (the parser reconciles the two, the engine does not guess).

    WHAT AN UNSPECIFIED ITEM BECOMES. When NOTHING is specified — the legacy brief, a bare count —
    the items take `default_wet_room_kinds`, so every plan for every existing brief is unchanged.
    When ANYTHING is specified the person has spoken about kinds, and the honest reading of what
    they left out is the plainest one: a shared bathroom entered from circulation. Applying the
    bare-count heuristic to a remainder would, for "שירותי אורחים + חדר רחצה", make the unstated
    room the master's ensuite and leave the house without a bathroom anyone else can reach.

    ZONE IDS follow today's naming: full bathrooms are BATH_n and WCs TOILET_n, numbered in order.
    An ENSUITE's host is the master, or — for `ENSUITE_HOST_BEDROOM` — the LAST secondary bedroom
    not yet hosting one (`programme_variants` attaches there too, and for the same reason: the
    guest WC wants to stay near the entrance, so a suite goes to the far end).
    """
    count = program.wet_rooms
    stated = tuple(program.wet_room_kinds)
    if len(stated) > count:
        raise WetRoomResolutionError(
            f"{len(stated)} wet-room kinds stated but wet_rooms={count}; the count is the authority")
    stated = stated + (WetRoomRequirement(),) * (count - len(stated))
    any_specified = any(k.kind is not WetRoomKind.UNSPECIFIED for k in stated)
    has_master = program.bedrooms >= 1
    defaults = default_wet_room_kinds(count, has_master)

    resolved: list[ResolvedWetRoom] = []
    baths = toilets = 0
    # Secondary bedrooms free to host an explicit BEDROOM ensuite, last first.
    free_hosts = [f"BEDROOM_{i}" for i in range(program.bedrooms - 1, 0, -1)]
    for index, item in enumerate(stated):
        specified = item.kind is not WetRoomKind.UNSPECIFIED
        if specified:
            kind, host, strength = item.kind, item.host, item.strength
        elif any_specified:
            kind, host, strength = WetRoomKind.SHARED_BATHROOM, None, item.strength
        else:
            kind, host, strength = defaults[index].kind, defaults[index].host, item.strength

        if kind is WetRoomKind.GUEST_WC:
            toilets += 1
            zone_id = f"TOILET_{toilets}"
        else:
            baths += 1
            zone_id = f"BATH_{baths}"

        host_zone: str | None = None
        if kind is WetRoomKind.ENSUITE:
            host = host or ENSUITE_HOST_MASTER
            if host == ENSUITE_HOST_MASTER:
                if not has_master:
                    raise WetRoomResolutionError(f"{zone_id}: an ensuite for the master, but the "
                                                 f"house has no bedroom")
                host_zone = "MASTER"
            elif host == ENSUITE_HOST_BEDROOM:
                if not free_hosts:
                    raise WetRoomResolutionError(f"{zone_id}: an ensuite for a secondary bedroom, "
                                                 f"but every secondary bedroom already has one or "
                                                 f"the house has none")
                host_zone = free_hosts.pop(0)
            else:
                raise WetRoomResolutionError(f"{zone_id}: unknown ensuite host {host!r}")
        elif host is not None:
            raise WetRoomResolutionError(f"{zone_id}: a host names an ensuite, not a {kind.value}")

        resolved.append(ResolvedWetRoom(zone_id, kind, host_zone, strength, specified,
                                        item.source_text))
    return tuple(resolved)


def requirement_from_record(kind: str, host: str | None, strength: str,
                            source_text: str = "") -> WetRoomRequirement:
    """A stored record (plain strings, so old projects always load) -> the engine's requirement.

    Fails closed: a kind or strength the vocabulary does not know is a `WetRoomResolutionError`,
    which `scope.check_supported` reports — never a silent fallback to UNSPECIFIED, which would
    plan a house the person did not describe.
    """
    try:
        return WetRoomRequirement(WetRoomKind(kind), host, WetRoomStrength(strength), source_text)
    except ValueError as exc:
        raise WetRoomResolutionError(f"unknown wet-room record {kind!r}/{strength!r}") from exc


def bedroom_zones(program: ProgramSpec) -> tuple[str, ...]:
    """The bedroom zone ids `build_room_program` creates, in its order."""
    if program.bedrooms < 1:
        return ()
    return ("MASTER",) + tuple(f"BEDROOM_{i}" for i in range(1, program.bedrooms))


def check_wet_room_invariants(program: ProgramSpec) -> tuple[WetRoomProblem, ...]:
    """Every invariant the programme breaks, in order. Empty means it may be planned."""
    try:
        resolved = resolve_wet_rooms(program)
    except WetRoomResolutionError as exc:
        return (WetRoomProblem("RESOLUTION", str(exc)),)

    problems: list[WetRoomProblem] = []
    any_unspecified = any(not r.specified for r in resolved)
    shared = [r for r in resolved if r.kind is WetRoomKind.SHARED_BATHROOM]

    if any_unspecified and not shared:
        problems.append(WetRoomProblem(
            "I1", "an unstated wet room, and no shared full bathroom for it to be"))
    for r in resolved:
        if r.kind is WetRoomKind.GUEST_WC and not r.entered_from_circulation:
            problems.append(WetRoomProblem("I2", f"{r.zone_id}: a guest WC entered from {r.host_zone}"))
        if r.kind is WetRoomKind.ENSUITE and r.entered_from_circulation:
            problems.append(WetRoomProblem("I3", f"{r.zone_id}: an ensuite with no host bedroom"))

    if not shared and not any_unspecified:
        hosts = {r.host_zone for r in resolved if r.kind is WetRoomKind.ENSUITE}
        without = tuple(b for b in bedroom_zones(program) if b not in hosts)
        if without:
            problems.append(WetRoomProblem(
                "I4", f"no shared full bathroom and no ensuite for {', '.join(without)}", without))
    return tuple(problems)

