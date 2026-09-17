from __future__ import annotations

import json

import pytest

from agent_team.issue_contract import (
    ContractError,
    IssueContract,
    manifest_json,
    parse_contract,
    render_body,
    slugify,
    verification_manifest,
)

KNOWN_LOCKS = ("planner-core", "geometry-core", "knowledge-index", "docs")


def test_valid_contract_parses(valid_body):
    c = parse_contract(42, "[agent] Document agentctl in the README", valid_body, known_locks=KNOWN_LOCKS)
    assert c.number == 42
    assert c.ac_ids == ("AC-1", "AC-2", "AC-3")
    assert c.domains == ("knowledge", "backend")
    assert c.risk == "LOW" and c.resource_class == "LIGHT"
    assert c.dependencies == ()
    assert c.locks[0].name == "docs" and c.locks[0].mode == "shared"
    assert [t.spec for t in c.targets_for("AC-1")] == ["grep:backend/README.md:Autonomous workflow"]
    assert c.targets_for("AC-1")[0].vtype == "ARTIFACT"
    assert c.targets_for("AC-3")[0].kind == "pytest"
    assert c.budget_rule("LOST").kind == "max" and c.budget_rule("LOST").limit == 0
    assert c.budget_rule("GAINED").kind == "allowed"
    assert c.budget_rule("primary_signature_changes").kind == "none"
    assert c.slug == "document-agentctl-in-the-readme"


def test_slugify_bounds():
    assert slugify("[agent] Add   Guest WC placement!!") == "add-guest-wc-placement"
    assert len(slugify("x" * 200)) <= 40
    assert slugify("!!!") == "task"


def test_render_round_trip(valid_body):
    c = parse_contract(7, "[agent] Round trip", valid_body, known_locks=KNOWN_LOCKS)
    again = parse_contract(7, "[agent] Round trip", render_body(c), known_locks=KNOWN_LOCKS)
    assert again == c


def test_manifest_is_machine_readable(valid_body):
    c = parse_contract(7, "[agent] Manifest", valid_body, known_locks=KNOWN_LOCKS)
    m = verification_manifest(c, regression_domains=("backend", "geometry"))
    assert m["issue"] == 7
    assert m["regression_required"] is True  # backend is a regression domain
    assert {t["ac"] for t in m["targets"]} == {"AC-1", "AC-2", "AC-3"}
    assert m["regression_budget"]["LOST"] == "0"
    assert json.loads(manifest_json(c)) == verification_manifest(c)


def test_regression_not_required_for_docs_only(valid_body):
    body = valid_body.replace("knowledge, backend", "knowledge")
    c = parse_contract(7, "t", body, known_locks=KNOWN_LOCKS)
    assert c.needs_regression(("backend", "geometry")) is False
    body2 = body.replace("- AC-3 -> pytest:backend/tests/test_projects.py", "- AC-3 -> regression:corpus")
    assert parse_contract(7, "t", body2, known_locks=KNOWN_LOCKS).needs_regression(("backend",)) is True


def _expect_problem(body: str, fragment: str, **kw):
    with pytest.raises(ContractError) as ei:
        parse_contract(1, "t", body, known_locks=KNOWN_LOCKS, **kw)
    assert any(fragment in p for p in ei.value.problems), ei.value.problems
    return ei.value.problems


def test_missing_section_rejected(valid_body):
    _expect_problem(valid_body.replace("### Risk", "### Danger"), "missing section '### Risk'")


def test_empty_required_section_rejected(valid_body):
    _expect_problem(valid_body.replace("The README does not mention scripts/agentctl at all.", "_No response_"),
                    "section 'Current behavior' is empty")


def test_ac_without_verification_rejected(valid_body):
    body = valid_body.replace("- AC-3 -> pytest:backend/tests/test_projects.py\n", "")
    _expect_problem(body, "AC-3 has no verification target")


def test_verification_for_unknown_ac_rejected(valid_body):
    body = valid_body.replace("- AC-3 -> pytest:backend/tests/test_projects.py",
                              "- AC-3 -> pytest:backend/tests/test_projects.py\n- AC-9 -> file:README.md")
    _expect_problem(body, "unknown criterion AC-9")


def test_bad_verification_kind_rejected(valid_body):
    body = valid_body.replace("grep:backend/README.md:agentctl status", "llm:looks fine")
    _expect_problem(body, "verification kind 'llm'")


def test_bad_risk_rejected(valid_body):
    _expect_problem(valid_body.replace("\nLOW\n", "\nMAYBE\n"), "Risk must be one of")


def test_unknown_domain_rejected(valid_body):
    _expect_problem(valid_body.replace("knowledge, backend", "knowledge, marketing"), "unknown domain 'marketing'")


def test_self_dependency_rejected(valid_body):
    _expect_problem(valid_body.replace("### Dependencies\n\nnone", "### Dependencies\n\n#1"), "cannot depend on itself")


def test_dependencies_parse(valid_body):
    c = parse_contract(1, "t", valid_body.replace("### Dependencies\n\nnone", "### Dependencies\n\n#200, #201 202"),
                       known_locks=KNOWN_LOCKS)
    assert c.dependencies == (200, 201, 202)


def test_unknown_lock_rejected(valid_body):
    _expect_problem(valid_body.replace("docs (shared)", "kitchen-sink (exclusive)"), "unknown lock 'kitchen-sink'")


def test_lock_default_mode_is_exclusive(valid_body):
    c = parse_contract(1, "t", valid_body.replace("docs (shared)", "planner-core"), known_locks=KNOWN_LOCKS)
    assert c.locks == (type(c.locks[0])("planner-core", "exclusive"),)


def test_lost_budget_default_and_allowance_rules(valid_body):
    # LOW risk: any non-zero LOST allowance is rejected; 'allowed' is never accepted at any risk
    _expect_problem(valid_body.replace("LOST: 0", "LOST: 2"), "non-zero LOST allowance requires Risk MEDIUM or HIGH")
    _expect_problem(valid_body.replace("LOST: 0", "LOST: tagged:bedrooms>=6"), "non-zero LOST allowance requires Risk MEDIUM or HIGH")
    _expect_problem(valid_body.replace("LOST: 0", "LOST: allowed"), "'allowed' is never accepted")
    _expect_problem(valid_body.replace("LOST: 0", "LOST: allowed").replace("\nLOW\n", "\nHIGH\n"), "'allowed' is never accepted")
    # default stays 0 when the line is missing
    c = parse_contract(1, "t", valid_body.replace("LOST: 0\n", ""), known_locks=KNOWN_LOCKS)
    assert c.budget_rule("LOST").kind == "max" and c.budget_rule("LOST").limit == 0 and not c.lost_allowance
    # MEDIUM/HIGH may name intentionally lost contexts explicitly
    body = valid_body.replace("LOST: 0", "LOST: tagged:bedrooms>=6").replace("\nLOW\n", "\nMEDIUM\n")
    c = parse_contract(1, "t", body, known_locks=KNOWN_LOCKS)
    assert c.lost_allowance and c.budget_rule("LOST").spec() == "tagged:bedrooms>=6"
    body = valid_body.replace("LOST: 0", "LOST: 1").replace("\nLOW\n", "\nHIGH\n")
    assert parse_contract(1, "t", body, known_locks=KNOWN_LOCKS).lost_allowance
    assert verification_manifest(c)["lost_allowance"] is True


def test_verification_types_inferred_and_explicit(valid_body):
    c = parse_contract(1, "t", valid_body, known_locks=KNOWN_LOCKS)
    assert {t.vtype for t in c.targets_for("AC-1")} == {"ARTIFACT"}
    assert c.targets_for("AC-3")[0].vtype == "TEST" and c.semantic_review_acs == ()
    body = valid_body.replace("- AC-3 -> pytest:backend/tests/test_projects.py",
                              "- AC-3 -> TEST:pytest:backend/tests/test_projects.py ; STATIC:static:backend-import ; "
                              "REGRESSION:regression:corpus ; review:the wording matches the Wiki page")
    c = parse_contract(1, "t", body, known_locks=KNOWN_LOCKS)
    assert [t.vtype for t in c.targets_for("AC-3")] == ["TEST", "STATIC", "REGRESSION", "SEMANTIC_REVIEW"]
    assert c.semantic_review_acs == ("AC-3",)
    assert verification_manifest(c)["semantic_review_acs"] == ["AC-3"]
    again = parse_contract(1, "t", render_body(c), known_locks=KNOWN_LOCKS)
    assert again.verification == c.verification
    _expect_problem(valid_body.replace("pytest:backend/tests/test_projects.py", "ARTIFACT:pytest:backend/tests/test_projects.py"),
                    "produces TEST evidence, not ARTIFACT")
    _expect_problem(valid_body.replace("pytest:backend/tests/test_projects.py", "static:something-else"), "static target must be one of")
    _expect_problem(valid_body.replace("pytest:backend/tests/test_projects.py", "review:ok"), "review target must say")


def test_semantic_review_alone_cannot_prove_behavior_change(valid_body):
    # backend is a behavior domain: a criterion proven only by review is rejected
    body = valid_body.replace("- AC-3 -> pytest:backend/tests/test_projects.py",
                              "- AC-3 -> review:the endpoint behaves as described")
    _expect_problem(body, "AC-3 is proven only by SEMANTIC_REVIEW")
    # a docs-only (knowledge) Issue may use it, as long as deterministic evidence exists elsewhere
    docs_only = body.replace("knowledge, backend", "knowledge")
    c = parse_contract(1, "t", docs_only, known_locks=KNOWN_LOCKS)
    assert c.semantic_review_acs == ("AC-3",) and not c.is_behavior_changing()
    # ... but never as the only kind of evidence in the whole contract
    only_review = docs_only.replace("- AC-1 -> grep:backend/README.md:Autonomous workflow", "- AC-1 -> review:section reads well") \
                           .replace("- AC-2 -> grep:backend/README.md:agentctl status", "- AC-2 -> review:mentions the status command")
    _expect_problem(only_review, "no deterministic verification target at all")


def test_tagged_budget_parses(valid_body):
    body = valid_body.replace("primary_signature_changes: none", "primary_signature_changes: tagged:safe_room=true")
    c = parse_contract(1, "t", body, known_locks=KNOWN_LOCKS)
    r = c.budget_rule("primary_signature_changes")
    assert (r.kind, r.tag_field, r.tag_op, r.tag_value) == ("tagged", "safe_room", "==", "true")
    assert r.spec() == "tagged:safe_room==true"


def test_unknown_budget_key_rejected(valid_body):
    _expect_problem(valid_body.replace("crashes: 0", "explosions: 0"), "unknown Regression budget key")


def test_all_problems_reported_together(valid_body):
    body = valid_body.replace("\nLOW\n", "\nMAYBE\n").replace("knowledge, backend", "marketing")
    problems = _expect_problem(body, "Risk must be one of")
    assert any("unknown domain" in p for p in problems)


def test_duplicate_ac_rejected(valid_body):
    _expect_problem(valid_body.replace("- AC-2:", "- AC-1:"), "duplicate acceptance criterion id AC-1")


def test_contract_is_frozen(valid_body):
    c = parse_contract(1, "t", valid_body, known_locks=KNOWN_LOCKS)
    assert isinstance(c, IssueContract)
    with pytest.raises(Exception):
        c.risk = "HIGH"  # type: ignore[misc]
