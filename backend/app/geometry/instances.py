from app.architect.models import ProgramItem


def expand_program_to_instances(program: list[ProgramItem]) -> list[tuple[str, str, ProgramItem]]:
    """Type-to-instance mapping: turns each `ProgramItem` (a room type + how many) into concrete,
    individually addressable instance ids.

    `bedroom` count=3 -> `BEDROOM_1`, `BEDROOM_2`, `BEDROOM_3`. A room type with exactly ONE
    instance TOTAL (whether that comes from a single `count=1` item, or is simply the only item of
    that type in the whole program) gets the bare uppercased type name with no suffix (e.g.
    `KITCHEN`, not `KITCHEN_1`) — there's nothing to disambiguate when only one instance exists.

    Numbering is GLOBAL per room type across every `ProgramItem` that declares it, not restarted
    per item -- this is what lets the program express multiple differently-sized instances of the
    SAME type (ROOM_INSTANCE_SIZE_FIDELITY: e.g. two separate `bedroom` ProgramItems, each
    count=1, with distinct `target_area_m2`) without colliding on the same id. A program that
    (as before this fix) only ever has ONE ProgramItem per room type sees no behavior change at
    all -- `total_for_type` always equals that single item's own `count` in that case.

    Returns `(instance_id, room_type, program_item)` tuples, preserving `program`'s order, so callers
    have the SPECIFIC originating `ProgramItem` (areas/widths) for each instance -- callers must use
    this tuple's own item, not a type-keyed re-lookup, or per-instance size fidelity is lost again.
    """
    total_count_by_type: dict[str, int] = {}
    for item in program:
        total_count_by_type[item.room_type] = total_count_by_type.get(item.room_type, 0) + item.count

    instances: list[tuple[str, str, ProgramItem]] = []
    next_index_by_type: dict[str, int] = {}
    for item in program:
        base_id = item.room_type.upper()
        singular = total_count_by_type[item.room_type] == 1
        for _ in range(item.count):
            if singular:
                instances.append((base_id, item.room_type, item))
            else:
                next_index_by_type[item.room_type] = next_index_by_type.get(item.room_type, 0) + 1
                instances.append((f"{base_id}_{next_index_by_type[item.room_type]}", item.room_type, item))
    return instances
