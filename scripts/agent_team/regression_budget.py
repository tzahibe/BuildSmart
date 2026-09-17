"""Evaluate a corpus regression report against an Issue's declared regression budget.

Pure function over two JSON documents: the report produced by
`backend/spikes/failure_log_sweep/corpus_snapshot.py --compare` and the budget parsed from the
Issue contract (`issue_contract.BudgetRule`). CI fails on any violation; nothing here is an
opinion.

Budget keys and what they count:

    LOST                        contexts PLANNED before, not PLANNED after      (must be 0)
    GAINED                      contexts not PLANNED before, PLANNED after
    crashes                     contexts that crash after and did not before
    status_changes              REFUSED <-> CRASH flips (neither lost nor gained)
    refusal_code_changes        REFUSED before and after with a different code
    primary_signature_changes   PLANNED before and after with a different room signature

Values: a number (max), `allowed`, `none` (== 0), or `tagged:<field><op><value>` — every changed
context must satisfy the predicate on its own context fields (e.g. `tagged:safe_room==true`,
`tagged:bedrooms>=5`), so a feature may change exactly the contexts it is about and nothing else.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field

from agent_team.issue_contract import BUDGET_KEYS, BudgetRule

#: budget key -> field in the corpus_snapshot report
REPORT_FIELDS = {"LOST": "lost", "GAINED": "gained", "crashes": "crashes", "status_changes": "status_changes",
                 "refusal_code_changes": "refusal_code_changes", "primary_signature_changes": "primary_signature_changes"}

_OPS = {"==": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


@dataclass(frozen=True)
class BudgetViolation:
    key: str
    rule: str
    observed: int
    detail: str


@dataclass
class BudgetEvaluation:
    ok: bool
    violations: list[BudgetViolation] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        head = "REGRESSION BUDGET: " + ("OK" if self.ok else "VIOLATED")
        rows = [f"  {k}: {v}" for k, v in self.counts.items()]
        for v in self.violations:
            rows.append(f"  ✗ {v.key}: observed {v.observed}, budget {v.rule} — {v.detail}")
        return "\n".join([head, *rows])


def _coerce(value, raw: str):
    if isinstance(value, bool):
        return value, raw.lower() in ("true", "1", "yes")
    if isinstance(value, (int, float)):
        try:
            return float(value), float(raw)
        except ValueError:
            return str(value), raw
    return str(value), raw


def context_matches(context: dict, rule: BudgetRule) -> bool:
    if rule.tag_field not in context:
        return False
    lhs, rhs = _coerce(context[rule.tag_field], rule.tag_value)
    op = _OPS.get(rule.tag_op)
    if op is None:
        return False
    try:
        return bool(op(lhs, rhs))
    except TypeError:
        return False


def evaluate(report: dict, rules: tuple[BudgetRule, ...] | list[BudgetRule]) -> BudgetEvaluation:
    by_key = {r.key: r for r in rules}
    ev = BudgetEvaluation(ok=True)
    for key in BUDGET_KEYS:
        rows = list(report.get(REPORT_FIELDS[key], []))
        observed = len(rows)
        ev.counts[key] = observed
        rule = by_key.get(key)
        if rule is None:
            # A missing rule is the strict default for everything except GAINED.
            rule = BudgetRule(key, "allowed") if key == "GAINED" else BudgetRule(key, "max", 0)
        if rule.kind == "allowed":
            continue
        if rule.kind in ("none", "max"):
            limit = 0 if rule.kind == "none" else rule.limit
            if observed > limit:
                sample = "; ".join(_describe(r) for r in rows[:5])
                ev.ok = False
                ev.violations.append(BudgetViolation(key, rule.spec(), observed, f"first: {sample}"))
            continue
        if rule.kind == "tagged":
            outside = [r for r in rows if not context_matches(r.get("context", {}), rule)]
            if outside:
                sample = "; ".join(_describe(r) for r in outside[:5])
                ev.ok = False
                ev.violations.append(BudgetViolation(key, rule.spec(), len(outside),
                                                     f"{len(outside)} change(s) outside the tagged contexts: {sample}"))
    if report.get("after", {}).get("total", 0) == 0:
        ev.ok = False
        ev.violations.append(BudgetViolation("corpus", "non-empty", 0, "the after-snapshot is empty — the harness did not run"))
    return ev


def _describe(row: dict) -> str:
    c = row.get("context", {})
    base = (f"{c.get('footprint_width_m')}x{c.get('footprint_depth_m')} bd={c.get('bedrooms')} wet={c.get('wet_rooms')} "
            f"safe={c.get('safe_room')} open={c.get('open_plan')}")
    if "after_code" in row and "before_code" in row:
        return f"{base} {row['before_code']} -> {row['after_code']}"
    if "after_code" in row:
        return f"{base} -> {row.get('after')} {row.get('after_code')}"
    if "error" in row:
        return f"{base} {row['error']}"
    return base
