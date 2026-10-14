"""GATE 1 — contract validation for agent PRs.

Verifies, deterministically:
- the PR targets the base branch from `agent/<issue>-<slug>` (never from main, never elsewhere);
- the PR body links exactly that Issue (`Closes #<issue>`);
- the Issue exists, is open, was opened by a trusted author association, carries an executable
  `agent:*` label (not draft) and parses as a valid contract (acceptance criteria, verification
  plan, risk/resource, budget);
- the Issue's domain/risk/resource labels match its contract;
- the PR body has every required section and an evidence row for every acceptance criterion.

Writes `manifest.json` (the machine-readable verification manifest used by gates 3 and 4) next to
the report, so later gates never re-interpret the Issue.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from agent_team.ci.common import GateReport, event_payload, repo_root, set_output, write_report
from agent_team.config import load_config
from agent_team.github_client import GitHubClient, TokenTransport
from agent_team.issue_contract import ContractError, IssueContract, parse_contract, verification_manifest
from agent_team.labels import STATE_LABEL_PREFIX, metadata_labels
from agent_team.worktree_manager import issue_from_branch

PR_SECTIONS = ("## Issue", "## What changed", "## Why", "## Implementation", "## Acceptance Criteria Evidence",
               "## Tests", "## Regression", "## Known limitations", "## Risk", "## Files / domains affected", "## Worker Agent")
_CLOSES = re.compile(r"(?i)\b(?:closes|fixes|resolves)\s+#(\d+)")
_EVIDENCE_ROW = re.compile(r"^\|\s*(AC-\d+)\s*\|", re.M)


def evaluate(pr: dict, issue: dict | None, config, *, contract_out: dict | None = None) -> GateReport:
    rep = GateReport("gate-1-contract")
    head = pr.get("head", {}).get("ref", "")
    base = pr.get("base", {}).get("ref", "")
    body = pr.get("body") or ""

    # main, or a weekend/holiday integration branch (worker PRs target it during a protected period)
    base_ok = base == config.base_branch or base.startswith("integration/")
    rep.add("PR targets base branch", base_ok, f"base={base!r}")
    rep.add("head branch is not the base branch", head != base and head != config.base_branch, f"head={head!r}")
    linked = [int(n) for n in _CLOSES.findall(body)]
    issue_labels = {l["name"] for l in (issue or {}).get("labels", [])}
    if head.startswith("integration/") or "agent:rollup" in issue_labels:
        # the rollup PR of a weekend/holiday period: its Issue is the rollup Issue the body closes
        issue_no = linked[0] if linked else None
        rep.add("rollup PR targets main", base == config.base_branch, f"base={base!r}")
        rep.add("rollup PR closes its rollup Issue", issue_no is not None, f"Closes: {linked or 'none'}")
    else:
        issue_no = issue_from_branch(config, head)
        rep.add("branch naming agent/<issue>-<slug>", issue_no is not None and bool(re.fullmatch(rf"{re.escape(config.branch_prefix)}\d+-[a-z0-9\-]+", head)), f"head={head!r}")
        rep.add("PR body links its Issue", issue_no is not None and issue_no in linked, f"Closes: {linked or 'none'}; branch issue: {issue_no}")

    if issue is None:
        rep.add("Issue exists", False, f"#{issue_no} not found")
        return rep
    rep.add("Issue exists and is open", issue.get("state") == "open", f"state={issue.get('state')}")
    assoc = issue.get("author_association", "NONE")
    rep.add("Issue author is trusted", assoc in config.executable_author_associations, f"author_association={assoc}")
    labels = [l["name"] for l in issue.get("labels", [])]
    state_labels = [l for l in labels if l.startswith(STATE_LABEL_PREFIX)]
    rep.add("Issue carries an executable agent:* label", bool(state_labels) and "agent:draft" not in state_labels, f"labels={state_labels}")

    try:
        contract = parse_contract(issue["number"], issue.get("title", ""), issue.get("body") or "", known_locks=config.known_locks,
                                  behavior_domains=config.behavior_domains)
    except ContractError as exc:
        rep.add("Issue contract validates", False, "; ".join(exc.problems)[:800])
        return rep
    rep.add("Issue contract validates", True, f"{len(contract.acceptance_criteria)} AC, {len(contract.verification)} targets"
            + (f", LOST allowance declared ({contract.budget_rule('LOST').spec()})" if contract.lost_allowance else ""))
    if contract.lost_allowance:
        rep.add("LOST allowance requires MEDIUM/HIGH risk", contract.risk in ("MEDIUM", "HIGH"), f"risk={contract.risk}")
    expected_meta = set(metadata_labels(contract.domains, contract.risk, contract.resource_class))
    have_meta = {l for l in labels if l.split(":")[0] in ("domain", "risk", "resource")}
    rep.add("Issue metadata labels match contract", expected_meta == have_meta,
            f"expected {sorted(expected_meta)}, have {sorted(have_meta)}")

    if head.startswith("integration/"):
        # A rollup PR carries the owner summary (§32), not a worker report: its evidence IS the combined-state
        # validation the gates run on this head, plus the per-child evidence recorded on each child PR.
        rep.add("rollup PR body carries the owner summary", "## מה בוצע" in body and "## Technical details" in body, "owner summary + technical table")
    else:
        missing = [s for s in PR_SECTIONS if s not in body]
        rep.add("PR body has all required sections", not missing, f"missing: {missing}" if missing else "all present")
        rows = set(_EVIDENCE_ROW.findall(body))
        lacking = [ac for ac in contract.ac_ids if ac not in rows]
        rep.add("PR evidence table covers every AC", not lacking, f"missing rows for {lacking}" if lacking else f"rows for {sorted(rows)}")
        risk_section = body.split("## Risk", 1)[1].split("##", 1)[0] if "## Risk" in body else ""
        rep.add("PR risk matches Issue risk", contract.risk in risk_section.upper(), f"issue risk {contract.risk}")

    manifest = verification_manifest(contract, regression_domains=config.regression_domains)
    rep.extra["manifest"] = manifest
    rep.extra["issue"] = contract.number
    if contract_out is not None:
        contract_out["contract"] = contract
    return rep


def main() -> int:
    root = repo_root()
    config = load_config(repo_root=root)
    event = event_payload()
    pr = event.get("pull_request") or {}
    if not pr:
        print("no pull_request in the event payload", file=sys.stderr)
        return 2
    client = GitHubClient(config.repo, TokenTransport())
    head = pr.get("head", {}).get("ref", "")
    issue_no = issue_from_branch(config, head)
    if issue_no is None and head.startswith("integration/"):
        closes = _CLOSES.findall(pr.get("body") or "")
        issue_no = int(closes[0]) if closes else None
    issue = None
    if issue_no is not None:
        try:
            issue = client.get_issue(issue_no)
        except Exception as exc:  # noqa: BLE001
            print(f"could not fetch issue #{issue_no}: {exc}", file=sys.stderr)
    rep = evaluate(pr, issue, config)
    label_only = [c["name"] for c in rep.checks if not c["ok"]] == ["Issue carries an executable agent:* label"]
    if label_only and issue_no is not None:
        # the orchestrator swaps the state label right after the push that triggered this run; a
        # read inside that window sees no state label — wait once and read again before failing
        import time as _time
        _time.sleep(20)
        try:
            issue = client.get_issue(issue_no)
            rep = evaluate(pr, issue, config)
        except Exception as exc:  # noqa: BLE001
            print(f"could not re-fetch issue #{issue_no}: {exc}", file=sys.stderr)
    out_dir = root / ".agent" / "ci"
    write_report(rep, out_dir / "contract_report.json")
    if "manifest" in rep.extra:
        (out_dir / "manifest.json").write_text(json.dumps(rep.extra["manifest"], indent=2), encoding="utf-8")
        set_output("issue", str(rep.extra["issue"]))
        set_output("risk", rep.extra["manifest"]["risk"])
        set_output("regression_required", "true" if rep.extra["manifest"]["regression_required"] else "false")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
