"""Risk-based merge policy. A PR merges only when every requirement of its risk level holds.

    LOW     ci_green + reviewer_green                              -> may auto-merge
    MEDIUM  ci_green + regression_green + reviewer_green + lead_approval
    HIGH    ci_green + regression_green + reviewer_green + lead_architecture_review

`regression_green` is satisfied by a green gate 4, or — when the contract did not require the
corpus and no backend product code changed — by the gate's explicit, recorded skip. Approvals
are recorded in the state store by the Team Lead (`agentctl approve`), never inferred from text.
The worker saying "done" is not an input to this function.
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
    if gate4:
        ok = all(ev.checks[n].get("conclusion") == "success" for n in gate4)
        return ok, "gate-4 " + ("green" if ok else "red")
    manifest = ev.reports.get("manifest") or {}
    if manifest.get("regression_required"):
        # the contract wanted the corpus; it was skipped only if no backend product code changed
        return ev.status == SUCCESS, "gate-4 skipped: no backend product code changed (aggregate check green)"
    return ev.status == SUCCESS, "gate-4 not required by the contract"


def decide(record: IssueRecord, ev: CiEvidence | None, config: Config, *, review_sha: str | None = None) -> MergeDecision:
    policy = config.risk_policy[record.risk]
    satisfied: list[str] = []
    missing: list[str] = []
    notes: list[str] = []
    approvals = {a["kind"] for a in record.approvals}
    for req in policy.requires:
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
        elif req in ("lead_approval", "lead_architecture_review"):
            ok = req in approvals
        else:
            ok = False
            notes.append(f"unknown requirement {req!r}")
        (satisfied if ok else missing).append(req)
    return MergeDecision(ok=not missing, auto_merge=policy.auto_merge and not missing,
                         satisfied=tuple(satisfied), missing=tuple(missing), notes=tuple(notes))
