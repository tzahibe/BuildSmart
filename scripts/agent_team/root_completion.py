"""When may a decomposed ROOT be closed automatically? (GitHub #188 directive 5)

THE DEFECT THIS REPLACES. `close_completed_roots` decided on one condition — every child's state is
`DONE` — and then told GitHub "Every child Issue of this ROOT is done and merged by the owner". That
claim was never verified. A child reaches `DONE` two ways and the state machine permits both:

    MERGED -> DONE, INTEGRATED -> DONE    delivered: a merge actually happened
    BLOCKED -> DONE                       RETIRED: a lead decision, including a measured
                                          negative result

On 2026-10-11 ROOT #127 auto-closed because child #134 — closed as an explicit negative result,
its PR #139 shut without merging — had reached `DONE`. Nothing was delivered.

THE RULE NOW. `DONE` is not evidence of anything. A child counts as delivered only when all four
hold, and every one of them is a fact read from GitHub or from a SHA-pinned record:

  1. it has a PR;
  2. that PR is MERGED — a PR closed without merging is a retirement;
  3. it merged into the ROOT's OWN required target — a PR merged into some other branch says
     nothing about this ROOT;
  4. an APPROVE review verdict is recorded for it — the explicit acceptance evidence.

AND the ROOT's target matters at a second level. When a ROOT works through an intermediate
integration branch, children merging into that branch does NOT mean the work reached `main`: main
is reached only through that ROOT's single rollup PR. While the integration branch is open the ROOT
is NOT complete, however many children are merged.

FAIL CLOSED. If the required target cannot be determined, or a PR cannot be read, or the acceptance
evidence is missing, this refuses. Refusing leaves the ROOT open for the owner — the same stance
`reconciliation` already takes ("never silently continue").
"""
from __future__ import annotations

from dataclasses import dataclass

#: A review verdict counts as acceptance evidence only in this form. `review_verdict` is stored as
#: `<VERDICT>@<sha>`, so the approval is pinned to the commit it was given for.
_APPROVED = "APPROVE@"


@dataclass(frozen=True)
class ChildOutcome:
    """One child's VERIFIED outcome. `detail` is written to the GitHub comment verbatim, so it may
    only ever state what was actually checked."""

    issue_id: int
    delivered: bool
    detail: str
    pr_number: int | None = None


@dataclass(frozen=True)
class RootCompletion:
    may_close: bool
    reason: str
    required_target: str | None
    children: tuple[ChildOutcome, ...] = ()

    def comment(self) -> str:
        """The closure comment. Describes only verified outcomes — never "merged by the owner"
        unless every line below was proven by a merged PR into the required target."""
        lines = [f"- #{c.issue_id} — {c.detail}" for c in self.children]
        return (f"**[agent-team]** Every child Issue of this ROOT was delivered into "
                f"`{self.required_target}` and independently approved:\n" + "\n".join(lines)
                + "\n\nClosing the ROOT.")


def child_outcome(child, pr: dict | None, required_target: str) -> ChildOutcome:
    """One child judged against the ROOT's required target. Pure; `pr` is GitHub's own record."""
    n = child.issue_id
    if not child.pr_number:
        return ChildOutcome(n, False, "no PR — retired, not delivered")
    if pr is None:
        return ChildOutcome(n, False, f"PR #{child.pr_number} could not be read — "
                                      f"delivery cannot be established", child.pr_number)
    if not pr.get("merged"):
        state = pr.get("state", "unknown")
        return ChildOutcome(n, False, f"PR #{child.pr_number} is {state} and was never merged — "
                                      f"retired, not delivered", child.pr_number)
    base = ((pr.get("base") or {}).get("ref")) or ""
    if base != required_target:
        return ChildOutcome(n, False, f"PR #{child.pr_number} merged into `{base}`, which is not "
                                      f"this ROOT's required target `{required_target}`",
                            child.pr_number)
    verdict = (child.review_verdict or "")
    if not verdict.startswith(_APPROVED):
        shown = verdict.split("@")[0] if verdict else "none recorded"
        return ChildOutcome(n, False, f"PR #{child.pr_number} merged into `{base}` but the "
                                      f"acceptance evidence is missing (review verdict: {shown})",
                            child.pr_number)
    sha = verdict[len(_APPROVED):][:12]
    return ChildOutcome(n, True, f"PR #{child.pr_number} merged into `{base}`, approved at "
                                 f"`{sha}`", child.pr_number)


def evaluate_root(root: int, children, *, required_target: str | None,
                  integration_open: bool, pr_lookup) -> RootCompletion:
    """May ROOT `root` be closed automatically?

    `required_target` is the branch its children must merge into — its integration branch when it
    has one, else the repository's base branch. `None` means it could not be determined, which is
    itself a refusal. `integration_open` is True while the ROOT's intermediate integration branch
    has not yet landed on the base branch.
    """
    if not children:
        return RootCompletion(False, "the ROOT has no tracked children", required_target)
    if required_target is None:
        return RootCompletion(False, "the ROOT's required integration target could not be "
                                     "determined — refusing to close on an unknown target", None)

    outcomes = []
    for child in children:
        pr = None
        if child.pr_number:
            try:
                pr = pr_lookup(child.pr_number)
            except Exception as exc:  # noqa: BLE001 — unreadable is "cannot establish", not "fine"
                outcomes.append(ChildOutcome(child.issue_id, False,
                                             f"PR #{child.pr_number} could not be read ({exc}) — "
                                             f"delivery cannot be established", child.pr_number))
                continue
        outcomes.append(child_outcome(child, pr, required_target))
    outcomes = tuple(outcomes)

    undelivered = [c for c in outcomes if not c.delivered]
    if undelivered:
        return RootCompletion(
            False,
            f"{len(undelivered)} of {len(outcomes)} children are not delivered: "
            + "; ".join(f"#{c.issue_id} ({c.detail})" for c in undelivered),
            required_target, outcomes)

    # Every child is in. But a child merged into an INTERMEDIATE integration branch has not
    # reached the base branch: that happens only through this ROOT's own rollup PR.
    if integration_open:
        return RootCompletion(
            False,
            f"every child is merged into `{required_target}`, but that is an intermediate "
            f"integration branch which has not landed — the base branch is reached only through "
            f"this ROOT's rollup PR, so the ROOT is not complete",
            required_target, outcomes)

    return RootCompletion(True, f"every child delivered into `{required_target}` with an "
                                f"approving review", required_target, outcomes)
