"""Generic transit roles by room TYPE -- which rooms can act as access hubs (a person may pass
through them to reach other rooms) versus destinations (rooms you enter and stop in, never used as
a corridor to somewhere else). Keyed by BuildSmart's real room-type vocabulary
(`app.architect.adapter._ROOM_TYPE_MAP`) -- generic architectural knowledge, not scenario-specific.

Unknown types fail SAFE to DESTINATION: an unrecognized room is never silently used as a
thoroughfare.
"""
from typing import Literal

TransitRole = Literal["HUB", "LIMITED_HUB", "DESTINATION"]

# Rooms one legitimately walks THROUGH to reach other rooms.
_HUB_TYPES: frozenset[str] = frozenset({"living_room", "entrance", "corridor", "staircase", "dining"})
# Rooms that can serve a small number of others (a kitchen typically links living and one
# service/utility room) but are not general-purpose circulation.
_LIMITED_HUB_TYPES: frozenset[str] = frozenset({"kitchen"})

# Preference order when the spec does not name an entry room: the first type present wins.
ENTRY_HUB_PREFERENCE: tuple[str, ...] = ("living_room", "entrance", "dining", "corridor", "staircase", "kitchen")

LIMITED_HUB_MAX_DESTINATIONS = 1


def transit_role(room_type: str) -> TransitRole:
    if room_type in _HUB_TYPES:
        return "HUB"
    if room_type in _LIMITED_HUB_TYPES:
        return "LIMITED_HUB"
    return "DESTINATION"
