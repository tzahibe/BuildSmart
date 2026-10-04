"""Issue #142K — offline parts of the corrected-proposer regeneration driver: response parsing in either
shape, the deterministic critic-feedback text (findings only, no geometry), and the bounded retry rule
(at most one critic-informed regeneration). No network, no LLM."""
from __future__ import annotations

from app.ai_harness.topology_poc.regen_142k import feedback_text, proposals_of


def test_proposals_are_read_from_an_array_or_a_wrapping_object():
    arr = [{"rooms": []}, {"rooms": [1]}]
    assert proposals_of(arr) == arr
    assert proposals_of({"proposals": arr}) == arr
    assert proposals_of({"anything": arr}) == arr                 # a single list value
    assert proposals_of({"a": arr, "b": arr}) == []                # ambiguous: honestly nothing
    assert proposals_of({}) == [] and proposals_of("x") == []


def test_feedback_is_findings_only_and_deterministic():
    assessment = {"rows": [
        {"index": 0, "hard": ("WET_ROOM_MULTIPLE_ENTRANTS",), "findings": [
            {"code": "WET_ROOM_MULTIPLE_ENTRANTS", "severity": "HARD", "subjects": ["BATHROOM_2"], "detail": "BATHROOM_2 has 2 doors (BEDROOM_1, HALL); a wet room has exactly one"},
            {"code": "ACCESS_WITHOUT_CONTACT", "severity": "WARN", "subjects": [], "detail": "ignored in feedback"}]},
        {"index": 1, "hard": ("UNREACHABLE_ROOM",), "findings": [
            {"code": "UNREACHABLE_ROOM", "severity": "HARD", "subjects": ["BEDROOM_2"], "detail": "not reachable from ENTRANCE through legal doors: BEDROOM_2"}]},
    ], "schema_rejected": [(2, "room 'X' has invalid role")]}
    a, b = feedback_text(assessment), feedback_text(assessment)
    assert a == b
    assert "proposal #1: WET_ROOM_MULTIPLE_ENTRANTS" in a and "proposal #2: UNREACHABLE_ROOM" in a and "proposal #3: SCHEMA_REJECTED" in a
    assert "ignored in feedback" not in a                           # WARNs are not fed back
    assert "COMPLETELY NEW batch" in a
    for forbidden in ("x=", "width", "metre", " m ", "coordinate"):  # no geometry edits, only findings and the rules
        assert forbidden not in a.lower()
