from __future__ import annotations

import json
from pathlib import Path

from agent_team.ci import contract_check, plan, regression_gate, verify
from agent_team.github_client import FakeGitHub
from agent_team.issue_contract import parse_budget_value
from agent_team.labels import metadata_labels
from agent_team.regression_budget import context_matches, evaluate
from agent_team.tests.conftest import VALID_BODY

PR_BODY = """## Issue
Closes #42

## What changed
- docs

## Why
because

## Implementation
edited README

## Acceptance Criteria Evidence
| AC | Evidence | Result |
|---|---|---|
| AC-1 | grep:backend/README.md:Autonomous workflow | PASS |
| AC-2 | grep:backend/README.md:agentctl status | PASS |
| AC-3 | pytest:backend/tests/test_projects.py | PASS |

## Tests
ran

## Regression
not required: docs only

## Known limitations
none

## Risk
LOW

## Files / domains affected
backend/README.md

## Worker Agent
sonnet
"""


def _pr(head="agent/42-doc", base="main", body=PR_BODY):
    return {"number": 7, "head": {"ref": head, "sha": "h"}, "base": {"ref": base, "sha": "b"}, "body": body}


def _issue(labels=None, body=VALID_BODY, assoc="OWNER", state="open"):
    labels = labels if labels is not None else ["agent:pr-open", *metadata_labels(("knowledge", "backend"), "LOW", "LIGHT")]
    return {"number": 42, "title": "[agent] Doc", "body": body, "state": state, "author_association": assoc,
            "labels": [{"name": l} for l in labels]}


def test_gate1_passes_for_a_well_formed_agent_pr(repo_config):
    rep = contract_check.evaluate(_pr(), _issue(), repo_config)
    assert rep.ok, [c for c in rep.checks if not c["ok"]]
    assert rep.extra["manifest"]["issue"] == 42 and rep.extra["manifest"]["regression_required"] is True


def test_gate1_rejects_bad_branch_and_missing_link(repo_config):
    rep = contract_check.evaluate(_pr(head="feature/x", body=PR_BODY.replace("Closes #42", "no link")), _issue(), repo_config)
    failed = {c["name"] for c in rep.checks if not c["ok"]}
    assert "branch naming agent/<issue>-<slug>" in failed and "PR body links its Issue" in failed


def test_gate1_rejects_untrusted_author_and_draft_label(repo_config):
    rep = contract_check.evaluate(_pr(), _issue(assoc="NONE"), repo_config)
    assert any(c["name"] == "Issue author is trusted" and not c["ok"] for c in rep.checks)
    rep = contract_check.evaluate(_pr(), _issue(labels=["agent:draft", *metadata_labels(("knowledge", "backend"), "LOW", "LIGHT")]), repo_config)
    assert any(c["name"] == "Issue carries an executable agent:* label" and not c["ok"] for c in rep.checks)


def test_gate1_rejects_label_mismatch_and_missing_evidence_rows(repo_config):
    rep = contract_check.evaluate(_pr(), _issue(labels=["agent:pr-open", "domain:frontend", "risk:low", "resource:light"]), repo_config)
    assert any(c["name"] == "Issue metadata labels match contract" and not c["ok"] for c in rep.checks)
    body = PR_BODY.replace("| AC-3 | pytest:backend/tests/test_projects.py | PASS |\n", "")
    rep = contract_check.evaluate(_pr(body=body), _issue(), repo_config)
    assert any("missing rows for ['AC-3']" in c["detail"] for c in rep.checks)


def test_gate1_rejects_invalid_contract_and_direct_main(repo_config):
    rep = contract_check.evaluate(_pr(), _issue(body=VALID_BODY.replace("### Risk", "### Danger")), repo_config)
    assert any(c["name"] == "Issue contract validates" and not c["ok"] for c in rep.checks)
    rep = contract_check.evaluate(_pr(head="main"), _issue(), repo_config)
    assert any(c["name"] == "head branch is not the base branch" and not c["ok"] for c in rep.checks)
    rep = contract_check.evaluate(_pr(), None, repo_config)
    assert not rep.ok


def test_plan_decides_gates():
    m = {"regression_required": True, "risk": "MEDIUM"}
    d = plan.decide(["backend/app/demo/service.py"], m)
    assert d["backend_changed"] and d["regression_required"] and not d["frontend_changed"]
    d = plan.decide(["docs/wiki/x.md", "backend/tests/test_x.py"], m)
    assert d["backend_changed"] and not d["regression_required"] and "no backend product code" in d["regression_reason"]
    d = plan.decide(["backend/app/x.py"], {"regression_required": False, "risk": "LOW"})
    assert not d["regression_required"]
    d = plan.decide(["backend/app/x.py"], {"regression_required": False, "risk": "HIGH"})
    assert d["regression_required"]  # HIGH risk + product code always replays the corpus
    d = plan.decide(["frontend/src/App.tsx", "scripts/agent_team/x.py"], None)
    assert d["frontend_changed"] and d["orchestrator_changed"] and not d["regression_required"]


def test_backend_docs_alone_do_not_trigger_the_fast_tier():
    m = {"regression_required": True, "risk": "MEDIUM"}
    d = plan.decide(["backend/README.md", "docs/wiki/x.md"], m)
    assert not d["backend_changed"] and not d["regression_required"]
    d = plan.decide(["backend/README.md", "backend/app/x.py"], m)
    assert d["backend_changed"]  # code alongside docs still runs the fast tier
    for path in ("backend/app/x.py", "backend/tests/test_x.py", "backend/spikes/x.py",
                 "backend/pyproject.toml", "backend/uv.lock"):
        assert plan.decide([path], m)["backend_changed"], path


def test_verify_runs_file_and_grep_targets(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("# Autonomous workflow\nrun scripts/agentctl status\n")
    manifest = {"issue": 1, "acceptance_criteria": [{"id": "AC-1", "text": "t"}, {"id": "AC-2", "text": "t"}, {"id": "AC-3", "text": "t"}],
                "targets": [{"ac": "AC-1", "kind": "file", "target": "docs/a.md"},
                            {"ac": "AC-2", "kind": "grep", "target": "docs/a.md:agentctl status"},
                            {"ac": "AC-3", "kind": "grep", "target": "docs/a.md:does-not-exist"}]}
    rep = verify.evaluate(manifest, tmp_path)
    assert not rep.ok
    by = {c["name"]: c for c in rep.checks}
    assert by["AC-1 -> file:docs/a.md"]["ok"] and by["AC-2 -> grep:docs/a.md:agentctl status"]["ok"]
    assert not by["AC-3 -> grep:docs/a.md:does-not-exist"]["ok"]
    assert "AC-3 evidence passes" in by and not by["AC-3 evidence passes"]["ok"]


def test_verify_fails_ac_without_targets_and_defers_regression(tmp_path: Path):
    manifest = {"issue": 1, "acceptance_criteria": [{"id": "AC-1", "text": "t"}, {"id": "AC-2", "text": "t"}],
                "targets": [{"ac": "AC-1", "kind": "regression", "target": "corpus"}]}
    rep = verify.evaluate(manifest, tmp_path)
    by = {c["name"]: c for c in rep.checks}
    assert by["AC-1 -> regression:corpus"]["ok"] and "deferred" in by["AC-1 -> regression:corpus"]["detail"]
    assert not by["AC-2 has evidence"]["ok"] and not rep.ok


def test_run_target_resolves_orchestrator_and_backend_pytest_targets(monkeypatch, tmp_path: Path):
    """AC-7: `scripts/agent_team/tests/` pytest targets run with the orchestrator's own project
    from the repository root; `backend/` targets still run from `backend/` exactly as before."""
    calls = []

    class FakeProc:
        returncode = 0
        stdout = "1 passed"
        stderr = ""

    def fake_run(cmd, cwd, timeout=1800, env=None):
        calls.append((cmd, str(cwd)))
        return FakeProc()

    monkeypatch.setattr(verify, "run", fake_run)

    ok, detail = verify.run_target("pytest", "scripts/agent_team/tests/test_work_reports.py::test_x", tmp_path)
    assert ok
    cmd, cwd = calls[-1]
    assert cmd == "uv run --project scripts/agent_team pytest -q -p no:cacheprovider scripts/agent_team/tests/test_work_reports.py::test_x"
    assert cwd == str(tmp_path)          # the repository root, not backend/

    ok, detail = verify.run_target("pytest", "backend/tests/test_x.py::test_y", tmp_path)
    assert ok
    cmd, cwd = calls[-1]
    assert cmd == "uv run pytest -q -p no:cacheprovider tests/test_x.py::test_y"
    assert cwd == str(tmp_path / "backend")


def test_verify_uses_injected_runner(tmp_path: Path):
    calls = []

    def fake(kind, target, root):
        calls.append((kind, target))
        return kind == "pytest", "fake"

    manifest = {"issue": 1, "acceptance_criteria": [{"id": "AC-1", "text": "t"}],
                "targets": [{"ac": "AC-1", "kind": "pytest", "target": "backend/tests/test_x.py::test_y"}]}
    assert verify.evaluate(manifest, tmp_path, runner=fake).ok and calls == [("pytest", "backend/tests/test_x.py::test_y")]


def _report(**overrides):
    base = {"before": {"planned": 404, "refused": 28, "crashes": 0, "total": 432},
            "after": {"planned": 404, "refused": 28, "crashes": 0, "total": 432},
            "lost": [], "gained": [], "crashes": [], "status_changes": [], "refusal_code_changes": [],
            "primary_signature_changes": [], "byte_identical_primaries": 404}
    base.update(overrides)
    return base


def _rules(**spec):
    d = {"LOST": "0", "GAINED": "allowed", "crashes": "0", "status_changes": "0", "refusal_code_changes": "0",
         "primary_signature_changes": "none"}
    d.update(spec)
    return tuple(parse_budget_value(k, v) for k, v in d.items())


def _ctx(**kw):
    c = {"footprint_width_m": 12.0, "footprint_depth_m": 14.0, "bedrooms": 3, "wet_rooms": 2, "safe_room": True, "open_plan": False}
    c.update(kw)
    return c


def test_budget_clean_report_passes():
    ev = evaluate(_report(), _rules())
    assert ev.ok and ev.counts["LOST"] == 0


def test_budget_lost_and_signature_changes_fail():
    rep = _report(lost=[{"context": _ctx(), "after": "REFUSED", "after_code": "X"}],
                  primary_signature_changes=[{"context": _ctx()}])
    ev = evaluate(rep, _rules())
    assert not ev.ok and {v.key for v in ev.violations} == {"LOST", "primary_signature_changes"}
    assert "12.0x14.0" in ev.summary()


def test_budget_allowed_and_max():
    rep = _report(primary_signature_changes=[{"context": _ctx()}, {"context": _ctx()}], gained=[{"context": _ctx()}])
    assert evaluate(rep, _rules(primary_signature_changes="allowed")).ok
    assert evaluate(rep, _rules(primary_signature_changes="2")).ok
    assert not evaluate(rep, _rules(primary_signature_changes="1")).ok
    assert not evaluate(rep, _rules(GAINED="0")).ok


def test_budget_tagged_predicate():
    rule = parse_budget_value("primary_signature_changes", "tagged:safe_room=true")
    assert context_matches(_ctx(safe_room=True), rule) and not context_matches(_ctx(safe_room=False), rule)
    rule = parse_budget_value("primary_signature_changes", "tagged:bedrooms>=5")
    assert context_matches(_ctx(bedrooms=5), rule) and not context_matches(_ctx(bedrooms=4), rule)
    rep = _report(primary_signature_changes=[{"context": _ctx(safe_room=True)}, {"context": _ctx(safe_room=False)}])
    ev = evaluate(rep, _rules(primary_signature_changes="tagged:safe_room=true"))
    assert not ev.ok and "1 change(s) outside" in ev.violations[0].detail
    rep = _report(primary_signature_changes=[{"context": _ctx(safe_room=True)}])
    assert evaluate(rep, _rules(primary_signature_changes="tagged:safe_room=true")).ok


def test_budget_empty_after_snapshot_fails():
    rep = _report(after={"planned": 0, "refused": 0, "crashes": 0, "total": 0})
    ev = evaluate(rep, _rules())
    assert not ev.ok and ev.violations[0].key == "corpus"


def test_regression_gate_report():
    rep = regression_gate.evaluate(_report(crashes=[{"context": _ctx(), "error": "KeyError"}]),
                                   {"LOST": "0", "GAINED": "allowed", "crashes": "0"})
    assert not rep.ok
    assert any(c["name"] == "budget crashes" and not c["ok"] for c in rep.checks)
    assert regression_gate.evaluate(_report(), {"LOST": "0"}).ok


def test_fake_github_state_label_is_idempotent():
    gh = FakeGitHub()
    gh.add_issue(1, "t", "b", ["agent:queued", "domain:qa"])
    assert gh.set_state_label(1, "CLAIMED") == "agent:claimed"
    assert gh.set_state_label(1, "CLAIMED") == "agent:claimed"
    assert sorted(gh.issue_labels(1)) == ["agent:claimed", "domain:qa"]
    pr = gh.create_pr(head="agent/1-t", base="main", title="t", body="b")
    assert gh.find_pr_for_branch("agent/1-t")["number"] == pr["number"]
    gh.review_pr(pr["number"], "ok", event="APPROVE")
    assert gh.reviews[-1][1] == "COMMENT"  # never self-approve through the owner's token
