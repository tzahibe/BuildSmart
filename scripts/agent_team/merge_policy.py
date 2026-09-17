"""Risk-based merge policy. A PR merges only when every requirement of its risk level holds.

    LOW     ci_green + reviewer_green                              -> may auto-merge
    MEDIUM  ci_green + regression_green + reviewer_green + lead_approval
    HIGH    ci_green + regression_green + reviewer_green + lead_architecture_review

`regression_green` is satisfied by a green gate 4, or — when the contract did not require the
corpus and no backend product code changed — by the gate's explicit, recorded skip. Approvals
are recorded in the state store by the Team Lead (`agentctl approve`), never inferred from text.
The worker saying "done" is not an input to this function.

Two further requirements are implied by the contract / the GitHub state rather than the risk table:

- `lost_allowance` — a contract whose regression budget intentionally allows LOST contexts needs
  an explicit `agentctl approve N --kind lost_allowance` on top of the risk requirements.
- `github_gates_green` — every context branch protection requires (the CI check run and the
  `agent-review-result` status) must be green on GitHub for the exact head SHA. The orchestrator
  merges only through that door; the admin exemption is break-glass and never used by automation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent_team.ci_evidence import SUCCESS, CiEvidence
from agent_team.config import Config
from agent_team.state_store import IssueRecord


@dataclass(frozen=True)
class MergeDecision:
    ok: bool
    auto_merge: bool
    satisfied: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def describe(self) -> str:
        parts = [f"satisfied: {', '.join(self.satisfied) or '-'}", f"missing: {', '.join(self.missing) or '-'}"]
        if self.notes:
            parts.append("notes: " + "; ".join(self.notes))
        return " | ".join(parts)


def regression_status(ev: CiEvidence, config: Config) -> tuple[bool, str]:
    gate4 = [n for n in ev.checks if n.startswith("gate-4")]
    conclusions = {ev.checks[n].get("conclusion") for n in gate4}
    if gate4 and conclusions - {"skipped"}:
        ok = conclusions == {"success"}
        return ok, "gate-4 " + ("green" if ok else "red")
    if gate4:
        # Skipped by ci/plan.py (no backend product code / not required). The aggregate check
        # fails when a *required* gate-4 was skipped, so green aggregate == legitimate skip.
        return ev.status == SUCCESS, "gate-4 skipped for this diff (aggregate check " + ("green" if ev.status == SUCCESS else "red") + ")"
    manifest = ev.reports.get("manifest") or {}
    if manifest.get("regression_required"):
        # the contract wanted the corpus; it was skipped only if no backend product code changed
        return ev.status == SUCCESS, "gate-4 skipped: no backend product code changed (aggregate check green)"
    return ev.status == SUCCESS, "gate-4 not required by the contract"


def decide(record: IssueRecord, ev: CiEvidence | None, config: Config, *, review_sha: str | None = None,
           lost_allowance: bool = False, require_github_gates: bool = False) -> MergeDecision:
    policy = config.risk_policy[record.risk]
    satisfied: list[str] = []
    missing: list[str] = []
    notes: list[str] = []
    approvals = {a["kind"] for a in record.approvals}
    requirements = list(policy.requires)
    if lost_allowance:
        requirements.append("lost_allowance")
    if require_github_gates:
        requirements.append("github_gates_green")
    for req in requirements:
        if req == "ci_green":
            ok = ev is not None and ev.status == SUCCESS
        elif req == "regression_green":
            if ev is None:
                ok = False
            else:
                ok, note = regression_status(ev, config)
                notes.append(note)
        elif req == "reviewer_green":
            verdict, _, verdict_sha = (record.review_verdict or "").partition("@")
            sha = review_sha or verdict_sha or None
            ok = verdict == "APPROVE" and (sha is None or ev is None or sha == ev.head_sha)
            if verdict == "APPROVE" and not ok:
                notes.append("review verdict is for an older head SHA")
        elif req in ("lead_approval", "lead_architecture_review", "lost_allowance"):
            ok = req in approvals
        elif req == "github_gates_green":
            if ev is None:
                ok = False
            else:
                ok, states = ev.required_contexts_green(config.protection_required_contexts)
                if not ok:
                    notes.append("GitHub contexts: " + ", ".join(f"{k}={v}" for k, v in states.items()))
        else:
            ok = False
            notes.append(f"unknown requirement {req!r}")
        (satisfied if ok else missing).append(req)
    return MergeDecision(ok=not missing, auto_merge=policy.auto_merge and not missing,
                         satisfied=tuple(satisfied), missing=tuple(missing), notes=tuple(notes))
