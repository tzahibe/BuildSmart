from __future__ import annotations

from agent_team.failure_classifier import (
    ENVIRONMENT_FAILURE, FLAKY_TEST, IMPLEMENTATION_FAILURE, INFRA_FAILURE, MERGE_CONFLICT, REGRESSION, REVIEW_REJECTED,
    SPEC_MISMATCH, TEST_FAILURE, FailureInput, classify,
)

GREEN = {"gate-1-contract / contract": "success", "gate-2-static": "success", "gate-3-verification": "success"}


def test_missing_optional_dependency_is_environment_not_implementation():
    inp = FailureInput(gate_results={**GREEN, "gate-2-static": "failure"},
                       logs={"gate-2-static": "...\nModuleNotFoundError: No module named 'torch'\n..."})
    c = classify(inp)
    assert c.kind == ENVIRONMENT_FAILURE and "torch" in c.summary and not c.repairable


def test_first_party_import_error_is_implementation():
    inp = FailureInput(gate_results={**GREEN, "gate-2-static": "failure"},
                       logs={"gate-2-static": "ModuleNotFoundError: No module named 'app.demo.newthing'"})
    assert classify(inp).kind == IMPLEMENTATION_FAILURE


def test_regression_gate_failure():
    inp = FailureInput(gate_results={**GREEN, "gate-4-regression / regression": "failure"},
                       reports={"regression_gate_report": {"checks": [{"name": "budget LOST", "ok": False, "detail": "observed 2, budget 0"}]}})
    c = classify(inp)
    assert c.kind == REGRESSION and "budget LOST" in c.evidence and c.repairable


def test_gate3_failing_own_tests_vs_existing_tests():
    rep = {"checks": [{"name": "AC-1 -> pytest:backend/tests/test_new.py::test_x", "ok": False, "detail": "1 failed"}]}
    own = FailureInput(gate_results={**GREEN, "gate-3-verification": "failure"}, reports={"verification_report": rep},
                       changed_files=["backend/tests/test_new.py", "backend/app/x.py"])
    assert classify(own).kind == TEST_FAILURE
    other = FailureInput(gate_results={**GREEN, "gate-3-verification": "failure"}, reports={"verification_report": rep},
                         changed_files=["backend/app/x.py"])
    assert classify(other).kind == IMPLEMENTATION_FAILURE
    missing_file = FailureInput(gate_results={**GREEN, "gate-3-verification": "failure"},
                                reports={"verification_report": {"checks": [{"name": "AC-2 -> file:docs/x.md", "ok": False, "detail": "missing"}]}})
    assert classify(missing_file).kind == IMPLEMENTATION_FAILURE


def test_gate2_pytest_failures_by_ownership():
    log = "FAILED tests/test_projects.py::test_create - AssertionError\n1 failed, 10 passed"
    inp = FailureInput(gate_results={**GREEN, "gate-2-static": "failure"}, logs={"gate-2-static": log}, changed_files=["backend/app/projects/api.py"])
    assert classify(inp).kind == IMPLEMENTATION_FAILURE
    inp = FailureInput(gate_results={**GREEN, "gate-2-static": "failure"}, logs={"gate-2-static": log}, changed_files=["backend/tests/test_projects.py"])
    assert classify(inp).kind == TEST_FAILURE


def test_syntax_error_is_implementation():
    inp = FailureInput(gate_results={**GREEN, "gate-2-static": "failure"}, logs={"gate-2-static": "  File x.py\nSyntaxError: invalid syntax"})
    assert classify(inp).kind == IMPLEMENTATION_FAILURE


def test_infra_and_flaky_and_conflict_and_spec():
    assert classify(FailureInput(gate_results={"gate-2-static": "cancelled"})).kind == INFRA_FAILURE
    assert classify(FailureInput(gate_results={**GREEN, "gate-2-static": "failure"},
                                 logs={"gate-2-static": "Error: The runner has received a shutdown signal."})).kind == INFRA_FAILURE
    assert classify(FailureInput(timed_out_waiting=True)).kind == INFRA_FAILURE
    assert classify(FailureInput(gate_results={**GREEN, "gate-2-static": "failure"}, rerun_passed=True)).kind == FLAKY_TEST
    assert classify(FailureInput(gate_results={**GREEN, "gate-2-static": "failure"}, mergeable=False, mergeable_state="dirty")).kind == MERGE_CONFLICT
    spec = FailureInput(gate_results={"gate-1-contract / contract": "failure"},
                        reports={"contract_report": {"checks": [{"name": "PR evidence table covers every AC", "ok": False}]}})
    c = classify(spec)
    assert c.kind == SPEC_MISMATCH and "evidence table" in c.summary


def test_review_rejection_is_its_own_class():
    c = classify(FailureInput(gate_results=GREEN, review_verdict="REQUEST_CHANGES"))
    assert c.kind == REVIEW_REJECTED and c.repairable


def test_gate4_red_without_a_budget_verdict_is_implementation_work_not_a_regression():
    """#67 (2026-09-20): the sharded base snapshot ran `--shard` on a base checkout whose script has no
    such flag; #35: a missing script on the PR head. Neither is 'a regression outside the budget'."""
    inp = FailureInput(gate_results={**GREEN, "gate-4-regression / snapshot (base, 1)": "failure"},
                       logs={"gate-4-regression / snapshot (base, 1)": "...\ncorpus_snapshot.py: error: unrecognized arguments: --shard 1/4\n##[error]Process completed with exit code 2."},
                       reports={})
    c = classify(inp)
    assert c.kind == "IMPLEMENTATION_FAILURE" and "unrecognized arguments: --shard" in c.summary and c.repairable
    # a real budget verdict still classifies as REGRESSION
    inp2 = FailureInput(gate_results={**GREEN, "gate-4-regression / regression": "failure"},
                        reports={"regression_gate_report": {"checks": [{"name": "LOST", "ok": False, "detail": "3 > 0"}]}})
    assert classify(inp2).kind == "REGRESSION"
