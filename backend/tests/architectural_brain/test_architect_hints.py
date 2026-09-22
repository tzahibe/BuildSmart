"""Verifies Issue #95 AC-4: a fake-gateway test shows a hint contradicting a requirement is
dropped and reported.

Reads (never modifies) the EXISTING, already-shipped Architect Model hint machinery
(``app.architect.gateway.ArchitectModelGateway``, ``app.vertical_slice.concept_spec
.ArchitectModelHints``/``hints_from_architect_spec``/``apply_architect_hints``/``DroppedHint`` --
Concept Engine child 1, Issue #75) rather than inventing a second one for this POC: the
investigation's conclusion (``docs/reports/poc-architectural-brain/architect-model.md``) is
precisely that this machinery is what the Architect Model can already serve as a non-authoritative
hint, and this test is the proof that "non-authoritative" actually holds.
"""
from __future__ import annotations

from app.architect.gateway import ArchitectModelGateway
from app.architect.models import (
    ArchitecturalSpec,
    ArchitectModelRequest,
    Circulation,
    ProgramItem,
    SiteSpec,
    Zone,
)
from app.vertical_slice.concept_spec import (
    CirculationClass,
    ConceptSpec,
    ZoningSplit,
    apply_architect_hints,
    hints_from_architect_spec,
)


class _FakeGateway(ArchitectModelGateway):
    """A fake Architect Model gateway -- deterministic, no external call -- that always claims a
    hallway is required, i.e. a SPINE circulation hint."""

    def generate(self, request: ArchitectModelRequest) -> ArchitecturalSpec:
        return ArchitecturalSpec(
            program=[ProgramItem(room_type="living_room", count=1)],
            zones=[Zone(name="public", room_types=["living_room"])],
            relationships=[],
            circulation=Circulation(entry_room_type="living_room", requires_hallway=True),
        )


def test_fake_gateway_hint_contradicting_authoritative_circulation_class_is_dropped_and_reported():
    gateway = _FakeGateway()
    request = ArchitectModelRequest(brief="a compact house", site=SiteSpec(width_m=10.0, depth_m=12.0))
    spec = gateway.generate(request)

    hints = hints_from_architect_spec(spec)
    assert hints.circulation_style_hint == "SPINE"

    # The candidate this hint is applied to was decided (by a builder, not the model) to be
    # FRONT_BAND -- a direct contradiction of the model's SPINE hint.
    authoritative_concept = ConceptSpec(
        circulation_class=CirculationClass.FRONT_BAND,
        zoning=ZoningSplit.FRONT_REAR,
        wet_core_groups=(),
        programme_reference=(),
        outline_reference=(),
    )

    merged, dropped = apply_architect_hints(authoritative_concept, hints)

    # The hint is attached for the record...
    assert merged.architect_hints == hints
    # ...but the authoritative fact is UNCHANGED...
    assert merged.circulation_class == CirculationClass.FRONT_BAND
    # ...and the contradiction is reported, not silently dropped.
    assert len(dropped) == 1
    assert dropped[0].field == "circulation_class"
    assert dropped[0].hinted_value == "SPINE"
    assert dropped[0].authoritative_value == "FRONT_BAND"


def test_fake_gateway_hint_agreeing_with_the_authoritative_class_is_not_reported_as_dropped():
    gateway = _FakeGateway()
    request = ArchitectModelRequest(brief="a spine-hall house", site=SiteSpec(width_m=10.0, depth_m=18.0))
    spec = gateway.generate(request)
    hints = hints_from_architect_spec(spec)

    authoritative_concept = ConceptSpec(
        circulation_class=CirculationClass.SPINE,
        zoning=ZoningSplit.SIDE_BY_SIDE,
        wet_core_groups=(),
        programme_reference=(),
        outline_reference=(),
    )

    merged, dropped = apply_architect_hints(authoritative_concept, hints)
    assert merged.circulation_class == CirculationClass.SPINE
    assert dropped == ()
