"""Parsing robustness for raw LLM text (supports AC-4's proposal generation, not itself an AC)."""
from __future__ import annotations

from app.ai_harness.topology_poc.llm_parsing import parse_proposals_array


def test_parses_clean_json_array():
    outcome = parse_proposals_array('[{"a": 1}, {"b": 2}]')
    assert outcome.array_found
    assert outcome.raw_dicts == ({"a": 1}, {"b": 2})
    assert outcome.elements_malformed == 0


def test_ignores_prose_before_and_after_array():
    text = 'Sure, here is the array:\n[{"a": 1}]\nHope that helps!'
    outcome = parse_proposals_array(text)
    assert outcome.raw_dicts == ({"a": 1},)


def test_bracket_inside_string_does_not_break_balancing():
    text = '[{"design_tradeoff": "rooms [A, B] trade off privacy"}]'
    outcome = parse_proposals_array(text)
    assert outcome.raw_dicts == ({"design_tradeoff": "rooms [A, B] trade off privacy"},)


def test_no_array_found_returns_empty_not_an_error():
    outcome = parse_proposals_array("no json here at all")
    assert outcome.array_found is False
    assert outcome.raw_dicts == ()


def test_non_dict_elements_are_counted_as_malformed_not_dropped_silently():
    outcome = parse_proposals_array('[{"a": 1}, "not a dict", 42]')
    assert outcome.raw_dicts == ({"a": 1},)
    assert outcome.elements_malformed == 2
    assert outcome.elements_seen == 3


def test_truncated_array_returns_empty_honestly():
    outcome = parse_proposals_array('[{"a": 1}, {"b": 2')
    assert outcome.array_found is False  # no balanced closing bracket found at all
    assert outcome.raw_dicts == ()
