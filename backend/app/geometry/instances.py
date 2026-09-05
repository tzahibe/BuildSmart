from app.architect.models import ProgramItem


def expand_program_to_instances(program: list[ProgramItem]) -> list[tuple[str, str, ProgramItem]]:
    """Type-to-instance mapping: turns each `ProgramItem` (a room type + how many) into concrete,
    individually addressable instance ids.

    `bedroom` count=3 -> `BEDROOM_1`, `BEDROOM_2`, `BEDROOM_3`. A count of exactly 1 gets the bare
    uppercased type name with no suffix (e.g. `KITCHEN`, not `KITCHEN_1`) — there's nothing to
    disambiguate when only one instance of a type exists.

    Returns `(instance_id, room_type, program_item)` tuples, preserving `program`'s order, so callers
    have the originating `ProgramItem` (areas/widths) alongside each instance without a second lookup.
    """
    instances: list[tuple[str, str, ProgramItem]] = []
    for item in program:
        base_id = item.room_type.upper()
        if item.count == 1:
            instances.append((base_id, item.room_type, item))
        else:
            for index in range(1, item.count + 1):
                instances.append((f"{base_id}_{index}", item.room_type, item))
    return instances
