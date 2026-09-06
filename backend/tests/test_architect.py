import pytest
from pydantic import ValidationError

from app.architect.gateway import MockArchitectModelGateway
from app.architect.models import (
    AdjacencyConstraint,
    ArchitecturalSpec,
    ArchitectModelRequest,
    Circulation,
    ConstraintSeverity,
    MaxAreaConstraint,
    MinAreaConstraint,
    MinWidthConstraint,
    ProgramItem,
    RequiredRoomConstraint,
    RequirementState,
    SiteSpec,
    Zone,
)


def _minimal_spec_kwargs(**overrides):
    kwargs = dict(
        program=[
            ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
            ProgramItem(room_type="living_room", count=1, target_area_m2=20.0, min_width_m=3.0),
        ],
        zones=[Zone(name="public", room_types=["kitchen", "living_room"])],
        relationships=[
            AdjacencyConstraint(room_type_a="kitchen", room_type_b="living_room", severity=ConstraintSeverity.hard)
        ],
        circulation=Circulation(entry_room_type="living_room"),
    )
    kwargs.update(overrides)
    return kwargs


# --- ArchitecturalSpec cross-reference validation --------------------------------------------


def test_valid_spec_constructs_without_error():
    spec = ArchitecturalSpec(**_minimal_spec_kwargs())
    assert len(spec.program) == 2


def test_duplicate_program_room_type_is_now_allowed():
    """ROOM_INSTANCE_SIZE_FIDELITY: multiple ProgramItems of the same room_type are explicitly
    ALLOWED now (previously rejected here) -- this is how a program represents several
    differently-sized instances of one type (e.g. two `bedroom` items, each count=1, at different
    explicit target areas). Cross-reference validation (zones/relationships/circulation) is
    unaffected: it already worked from the SET of declared types, duplicates or not."""
    spec = ArchitecturalSpec(
        **_minimal_spec_kwargs(
            program=[
                ProgramItem(room_type="kitchen", count=1, target_area_m2=12.0, min_width_m=2.4),
                ProgramItem(room_type="living_room", count=1, target_area_m2=20.0, min_width_m=3.0),
                ProgramItem(room_type="bedroom", count=1, target_area_m2=14.0),
                ProgramItem(room_type="bedroom", count=1, target_area_m2=10.0),
            ]
        )
    )
    assert len(spec.program) == 4
    bedroom_items = [item for item in spec.program if item.room_type == "bedroom"]
    assert len(bedroom_items) == 2
    assert {item.target_area_m2 for item in bedroom_items} == {14.0, 10.0}


def test_zone_referencing_unknown_room_type_is_rejected():
    with pytest.raises(ValidationError, match="unknown room type"):
        ArchitecturalSpec(
            **_minimal_spec_kwargs(zones=[Zone(name="public", room_types=["kitchen", "bathroom"])])
        )


def test_relationship_referencing_unknown_room_type_is_rejected():
    with pytest.raises(ValidationError, match="unknown room type"):
        ArchitecturalSpec(
            **_minimal_spec_kwargs(
                relationships=[
                    AdjacencyConstraint(
                        room_type_a="kitchen", room_type_b="bedroom", severity=ConstraintSeverity.hard
                    )
                ]
            )
        )


def test_relationship_same_room_type_twice_is_rejected():
    with pytest.raises(ValidationError, match="must differ"):
        AdjacencyConstraint(room_type_a="kitchen", room_type_b="kitchen", severity=ConstraintSeverity.hard)


def test_circulation_entry_referencing_unknown_room_type_is_rejected():
    with pytest.raises(ValidationError, match="circulation.entry_room_type"):
        ArchitecturalSpec(**_minimal_spec_kwargs(circulation=Circulation(entry_room_type="bedroom")))


# --- ProgramItem target/min/max area semantics ------------------------------------------------


def test_program_item_accepts_consistent_target_min_max():
    item = ProgramItem(room_type="bedroom", count=1, min_area_m2=9.0, target_area_m2=12.0, max_area_m2=14.0)
    assert item.min_area_m2 == 9.0 and item.max_area_m2 == 14.0


def test_program_item_rejects_min_area_above_max_area():
    with pytest.raises(ValidationError, match="exceeds max_area_m2"):
        ProgramItem(room_type="bedroom", count=1, min_area_m2=15.0, max_area_m2=10.0)


def test_program_item_rejects_target_below_min_area():
    with pytest.raises(ValidationError, match="below min_area_m2"):
        ProgramItem(room_type="bedroom", count=1, min_area_m2=10.0, target_area_m2=8.0)


def test_program_item_rejects_target_above_max_area():
    with pytest.raises(ValidationError, match="exceeds max_area_m2"):
        ProgramItem(room_type="bedroom", count=1, max_area_m2=10.0, target_area_m2=12.0)


# --- ArchitectModelRequest severity-consistency validation ------------------------------------


def test_hard_constraints_list_rejects_a_soft_severity_entry():
    with pytest.raises(ValidationError, match="must have severity='hard'"):
        ArchitectModelRequest(
            brief="test",
            site=SiteSpec(width_m=10, depth_m=10),
            hard_constraints=[
                RequiredRoomConstraint(room_type="bedroom", count=1, severity=ConstraintSeverity.soft)
            ],
        )


def test_soft_constraints_list_rejects_a_hard_severity_entry():
    with pytest.raises(ValidationError, match="must have severity='soft'"):
        ArchitectModelRequest(
            brief="test",
            site=SiteSpec(width_m=10, depth_m=10),
            soft_constraints=[
                RequiredRoomConstraint(room_type="bedroom", count=1, severity=ConstraintSeverity.hard)
            ],
        )


# --- MockArchitectModelGateway -----------------------------------------------------------------


def test_mock_gateway_defaults_to_one_bedroom_and_no_safe_room():
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(brief="a small home", site=SiteSpec(width_m=12, depth_m=10))

    spec = gateway.generate(request)

    bedroom_items = [item for item in spec.program if item.room_type == "bedroom"]
    assert len(bedroom_items) == 1
    assert bedroom_items[0].count == 1
    assert all(item.room_type != "safe_room" for item in spec.program)


def test_mock_gateway_honors_typed_required_room_constraints():
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(
        brief="בית עם 3 חדרי שינה וממ\"ד",
        site=SiteSpec(width_m=14, depth_m=12),
        hard_constraints=[
            RequiredRoomConstraint(room_type="bedroom", count=3, severity=ConstraintSeverity.hard),
            RequiredRoomConstraint(room_type="safe_room", count=1, severity=ConstraintSeverity.hard),
        ],
    )

    spec = gateway.generate(request)

    bedroom_items = [item for item in spec.program if item.room_type == "bedroom"]
    assert bedroom_items[0].count == 3
    assert any(item.room_type == "safe_room" for item in spec.program)
    assert any(
        rel.room_type_a == "safe_room" and rel.room_type_b == "bedroom" and rel.severity == ConstraintSeverity.hard
        for rel in spec.relationships
    )


def test_mock_gateway_honors_area_and_width_overrides():
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(
        brief="test",
        site=SiteSpec(width_m=14, depth_m=12),
        hard_constraints=[
            RequiredRoomConstraint(room_type="bedroom", count=1, severity=ConstraintSeverity.hard),
            MinAreaConstraint(room_type="bedroom", min_area_m2=10.0, severity=ConstraintSeverity.hard),
            MaxAreaConstraint(room_type="bedroom", max_area_m2=16.0, severity=ConstraintSeverity.hard),
            MinWidthConstraint(room_type="bedroom", min_width_m=3.2, severity=ConstraintSeverity.hard),
        ],
    )

    spec = gateway.generate(request)

    bedroom = next(item for item in spec.program if item.room_type == "bedroom")
    assert bedroom.min_area_m2 == 10.0
    assert bedroom.max_area_m2 == 16.0
    assert bedroom.min_width_m == 3.2


def test_mock_gateway_output_is_a_valid_architectural_spec():
    # The gateway's own output must satisfy ArchitecturalSpec's cross-reference validation — this is
    # implicit (construction would raise otherwise), asserted here explicitly for clarity.
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(
        brief="test",
        site=SiteSpec(width_m=12, depth_m=10),
        hard_constraints=[RequiredRoomConstraint(room_type="bedroom", count=4, severity=ConstraintSeverity.hard)],
    )

    spec = gateway.generate(request)

    assert isinstance(spec, ArchitecturalSpec)
    assert spec.circulation.requires_hallway is True  # bedroom_count > 2


def test_mock_gateway_explicit_zero_bedroom_count_excludes_bedroom_entirely():
    # count=0 must NOT collapse into the "no constraint given, use the default of 1" case — see
    # RequiredRoomConstraint's docstring — and the resulting spec must still be valid (no bedroom
    # references left dangling in zones/relationships/circulation).
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(
        brief="test",
        site=SiteSpec(width_m=12, depth_m=10),
        hard_constraints=[RequiredRoomConstraint(room_type="bedroom", count=0, severity=ConstraintSeverity.hard)],
    )

    spec = gateway.generate(request)

    assert all(item.room_type != "bedroom" for item in spec.program)
    assert all("bedroom" not in zone.room_types for zone in spec.zones)
    assert all(
        "bedroom" not in (rel.room_type_a, rel.room_type_b) for rel in spec.relationships
    )
    assert isinstance(spec, ArchitecturalSpec)  # constructs cleanly — no dangling bedroom references


# --- UNKNOWN != ZERO: RequiredRoomConstraint's state/count contract ------------------------------


def test_required_room_constraint_known_state_requires_a_count():
    with pytest.raises(ValidationError, match="count must be provided"):
        RequiredRoomConstraint(room_type="bedroom", state=RequirementState.known, severity=ConstraintSeverity.hard)


def test_required_room_constraint_unknown_state_rejects_a_count():
    with pytest.raises(ValidationError, match="count must not be provided"):
        RequiredRoomConstraint(
            room_type="bedroom", state=RequirementState.unknown, count=2, severity=ConstraintSeverity.hard
        )


def test_required_room_constraint_unknown_state_with_no_count_is_valid():
    constraint = RequiredRoomConstraint(
        room_type="bedroom", state=RequirementState.unknown, severity=ConstraintSeverity.hard
    )
    assert constraint.count is None


@pytest.mark.parametrize(
    ("constraint", "expected_bedroom_count", "expected_incomplete"),
    [
        (RequiredRoomConstraint(room_type="bedroom", state=RequirementState.known, count=0, severity=ConstraintSeverity.hard), 0, False),
        (RequiredRoomConstraint(room_type="bedroom", state=RequirementState.known, count=3, severity=ConstraintSeverity.hard), 3, False),
        (RequiredRoomConstraint(room_type="bedroom", state=RequirementState.unknown, severity=ConstraintSeverity.hard), 0, True),
    ],
    ids=["explicit-zero", "explicit-three", "unknown"],
)
def test_mock_gateway_distinguishes_explicit_zero_explicit_three_and_unknown(
    constraint: RequiredRoomConstraint, expected_bedroom_count: int, expected_incomplete: bool
):
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(
        brief="test", site=SiteSpec(width_m=12, depth_m=10), hard_constraints=[constraint]
    )

    spec = gateway.generate(request)

    bedroom_items = [item for item in spec.program if item.room_type == "bedroom"]
    actual_count = bedroom_items[0].count if bedroom_items else 0
    assert actual_count == expected_bedroom_count
    assert ("bedroom" in spec.incomplete_requirements) == expected_incomplete


def test_mock_gateway_unknown_bedroom_state_never_fabricates_the_generic_default():
    # The generic "no constraint at all" default (1 bedroom, per
    # test_mock_gateway_defaults_to_one_bedroom_and_no_safe_room) must NOT leak into the "explicitly
    # unknown" case — that would be exactly the silent fabrication this contract exists to prevent.
    gateway = MockArchitectModelGateway()
    request = ArchitectModelRequest(
        brief="test",
        site=SiteSpec(width_m=12, depth_m=10),
        hard_constraints=[
            RequiredRoomConstraint(room_type="bedroom", state=RequirementState.unknown, severity=ConstraintSeverity.hard)
        ],
    )

    spec = gateway.generate(request)

    assert all(item.room_type != "bedroom" for item in spec.program)
    assert spec.incomplete_requirements == ["bedroom"]
