"""The ArchitectModelGateway abstraction: the rest of the backend depends only on this interface,
never on a specific model provider or on how/whether the model was trained or fine-tuned. Swapping
`MockArchitectModelGateway` for a real (e.g. LLM-backed) implementation later requires no change
anywhere else — same boundary-abstraction pattern as `app/requirements/parser.py`'s `RequirementParser`
and `app/chat/assistant.py`'s `ChatAssistant`.
"""

from abc import ABC, abstractmethod

from app.architect.models import (
    AdjacencyConstraint,
    ArchitecturalSpec,
    ArchitectModelRequest,
    Circulation,
    ConstraintSeverity,
    DirectAccessConstraint,
    MaxAreaConstraint,
    MinAreaConstraint,
    MinWidthConstraint,
    ProgramItem,
    RequiredRoomConstraint,
    RequirementState,
    SeparationConstraint,
    Zone,
)


class ArchitectModelGateway(ABC):
    @abstractmethod
    def generate(self, request: ArchitectModelRequest) -> ArchitecturalSpec: ...


# Placeholder sizing, not a standard — same spirit as Feature 03's fixed room-size constants
# (specs/003-parametric-design-model/plan.md's Design decisions).
_TARGET_AREA_M2 = {"kitchen": 12.0, "bathroom": 5.0, "safe_room": 9.0, "living_room": 20.0, "bedroom": 12.0}
_MIN_WIDTH_M = {"kitchen": 2.4, "bathroom": 1.6, "safe_room": 2.2, "living_room": 3.0, "bedroom": 2.6}


class _RequiredRoomLookup:
    """Result of looking up a `RequiredRoomConstraint` for one room type — three genuinely different
    outcomes, kept distinct on purpose (see `RequirementState`'s docstring for why collapsing any two
    of these would be a fabrication):

    - `present=False`: no constraint was given at all — the gateway may apply its own generic default.
    - `present=True, is_unknown=True`: the caller explicitly doesn't know the count. `count` is None.
    - `present=True, is_unknown=False`: a real, known count (`count`, which may legitimately be 0).
    """

    def __init__(self, present: bool, is_unknown: bool = False, count: int | None = None) -> None:
        self.present = present
        self.is_unknown = is_unknown
        self.count = count


def _lookup_required_room(request: ArchitectModelRequest, room_type: str) -> _RequiredRoomLookup:
    for constraint in request.hard_constraints:
        if isinstance(constraint, RequiredRoomConstraint) and constraint.room_type == room_type:
            if constraint.state == RequirementState.unknown:
                return _RequiredRoomLookup(present=True, is_unknown=True)
            return _RequiredRoomLookup(present=True, is_unknown=False, count=constraint.count)
    return _RequiredRoomLookup(present=False)


def _area_and_width_overrides(
    request: ArchitectModelRequest, room_type: str
) -> tuple[float | None, float | None, float | None]:
    """Pulls any typed MinArea/MaxArea/MinWidth hard constraints for `room_type` out of the request,
    so the mock actually consumes them rather than only ever using its own fixed defaults."""
    min_area = max_area = min_width = None
    for constraint in request.hard_constraints:
        if isinstance(constraint, MinAreaConstraint) and constraint.room_type == room_type:
            min_area = constraint.min_area_m2
        elif isinstance(constraint, MaxAreaConstraint) and constraint.room_type == room_type:
            max_area = constraint.max_area_m2
        elif isinstance(constraint, MinWidthConstraint) and constraint.room_type == room_type:
            min_width = constraint.min_width_m
    return min_area, max_area, min_width


def _program_item(request: ArchitectModelRequest, room_type: str, count: int) -> ProgramItem:
    min_area, max_area, min_width_override = _area_and_width_overrides(request, room_type)
    return ProgramItem(
        room_type=room_type,
        count=count,
        target_area_m2=_TARGET_AREA_M2[room_type],
        min_area_m2=min_area,
        max_area_m2=max_area,
        min_width_m=min_width_override or _MIN_WIDTH_M[room_type],
    )


class MockArchitectModelGateway(ArchitectModelGateway):
    """Deterministic placeholder — derives a plausible `ArchitecturalSpec` directly from the request's
    typed hard constraints (bedroom count via `RequiredRoomConstraint`, a safe room via the same,
    optional per-room area/width overrides via `MinAreaConstraint`/`MaxAreaConstraint`/
    `MinWidthConstraint`) without calling any external model. Stands in for a real model-backed
    gateway so the Geometry Solver has a realistic contract to consume during development; the
    `ArchitectModelGateway` abstraction above, not this class, is the actual deliverable.
    """

    def generate(self, request: ArchitectModelRequest) -> ArchitecturalSpec:
        incomplete_requirements: list[str] = []

        # Three-way distinction (see `_RequiredRoomLookup`): absent -> this mock's own generic default
        # (1 bedroom); known -> exactly that count, including a real 0; unknown -> excluded from the
        # program entirely and reported, NEVER guessed as 0 or as the default.
        bedroom_lookup = _lookup_required_room(request, "bedroom")
        if bedroom_lookup.is_unknown:
            bedroom_count = 0
            incomplete_requirements.append("bedroom")
        elif bedroom_lookup.present:
            bedroom_count = bedroom_lookup.count or 0
        else:
            bedroom_count = 1  # no constraint at all given -> generic default for standalone use
        has_bedroom = bedroom_count > 0

        safe_room_lookup = _lookup_required_room(request, "safe_room")
        if safe_room_lookup.is_unknown:
            wants_safe_room = False
            incomplete_requirements.append("safe_room")
        elif safe_room_lookup.present:
            wants_safe_room = (safe_room_lookup.count or 0) > 0
        else:
            wants_safe_room = False  # no constraint at all -> default is "not requested", not a guess

        program = [
            _program_item(request, "kitchen", 1),
            _program_item(request, "bathroom", 1),
            _program_item(request, "living_room", 1),
        ]
        if has_bedroom:
            program.append(_program_item(request, "bedroom", bedroom_count))
        if wants_safe_room:
            program.append(_program_item(request, "safe_room", 1))

        zones = [
            Zone(name="public", room_types=["living_room", "kitchen"]),
            Zone(
                name="private",
                room_types=(["bedroom"] if has_bedroom else [])
                + ["bathroom"]
                + (["safe_room"] if wants_safe_room else []),
            ),
        ]

        relationships = [
            AdjacencyConstraint(
                room_type_a="kitchen",
                room_type_b="living_room",
                severity=ConstraintSeverity.hard,
                description="Kitchen must open onto the main living/dining area",
            ),
            DirectAccessConstraint(
                room_type_a="bathroom",
                room_type_b="living_room",
                severity=ConstraintSeverity.soft,
                description="Prefer the bathroom directly reachable near common areas",
            ),
        ]
        if has_bedroom:
            relationships.append(
                AdjacencyConstraint(
                    room_type_a="bedroom",
                    room_type_b="bathroom",
                    severity=ConstraintSeverity.soft,
                    description="Prefer a bedroom near the bathroom",
                )
            )
            relationships.append(
                SeparationConstraint(
                    room_type_a="bedroom",
                    room_type_b="kitchen",
                    severity=ConstraintSeverity.soft,
                    description="Prefer keeping bedrooms away from kitchen noise/smells",
                )
            )
        if wants_safe_room and has_bedroom:
            relationships.append(
                DirectAccessConstraint(
                    room_type_a="safe_room",
                    room_type_b="bedroom",
                    severity=ConstraintSeverity.hard,
                    description=(
                        "Safe room reachable directly from a bedroom — a placeholder design "
                        "heuristic for this mock, not sourced from actual building code"
                    ),
                )
            )

        circulation = Circulation(entry_room_type="living_room", requires_hallway=bedroom_count > 2)

        return ArchitecturalSpec(
            program=program,
            zones=zones,
            relationships=relationships,
            circulation=circulation,
            incomplete_requirements=incomplete_requirements,
        )


def get_architect_model_gateway() -> ArchitectModelGateway:
    """Provider selection per `ARCHITECT_MODEL_PROVIDER` (default `"mock"`) — see
    `app/architect/config.py`. This is the DEFAULT a caller gets when it doesn't construct a gateway
    itself; tests and other callers that want a specific gateway should keep constructing one directly
    and passing it explicitly (e.g. `generate_design_via_solver(project, gateway=...)`), never going
    through this factory, so provider selection stays a single, explicit runtime decision rather than
    something tests need to fight against via environment variables.

    `RealArchitectModelGateway` is imported lazily inside the `"real"` branch — it needs
    `ArchitectModelGateway` from this module, so importing it at module scope here would be circular.
    """
    from app.architect.config import provider_name_from_env, real_config_from_env

    provider = provider_name_from_env()
    if provider == "mock":
        return MockArchitectModelGateway()
    if provider == "real":
        from app.architect.real_gateway import RealArchitectModelGateway

        return RealArchitectModelGateway(real_config_from_env())
    raise RuntimeError(f"Unknown ARCHITECT_MODEL_PROVIDER: {provider!r} (expected 'mock' or 'real')")
