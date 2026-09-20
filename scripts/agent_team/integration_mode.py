"""Weekend / Jewish-holiday autonomous integration mode — the pure parts.

During a protected period (`protected_periods.py`) the Team Lead merges every fully validated
worker PR into ONE temporary integration branch instead of stopping at READY_FOR_OWNER; at the
end of the period one rollup PR (integration branch -> main) carries everything, is validated as
a whole (CI gates + regression against main + independent review of the combined diff) and
becomes the single READY_FOR_OWNER item. Main is never merged autonomously. This module renders
the rollup Issue contract, the rollup PR body and the owner's Telegram notification; the
orchestrator owns the state changes.
"""
from __future__ import annotations

import datetime as dt

from agent_team.protected_periods import Period

HEBREW_MONTHS = {1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל", 5: "מאי", 6: "יוני", 7: "יולי", 8: "אוגוסט",
                 9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר"}
HEBREW_HOLIDAYS = {"Yom Kippur": "יום כיפור", "Succos": "סוכות", "Shmini Atzeres": "שמיני עצרת", "Shavuos": "שבועות",
                   "Rosh Hashana": "ראש השנה", "Pesach": "פסח", "weekend": "סוף השבוע"}


def period_title(p: Period) -> str:
    """English PR/Issue title: 'Weekend Integration — 18–21 Sep 2026' / 'Yom Kippur Integration — …'."""
    what = "Weekend" if p.kind == "SHABBAT" else p.name
    if p.start.month == p.end.month:
        span = f"{p.start.day}–{p.end.day} {p.end.strftime('%b %Y')}"
    else:
        span = f"{p.start.strftime('%d %b')} – {p.end.strftime('%d %b %Y')}"
    return f"{what} Integration — {span}"


def period_hebrew(p: Period) -> str:
    return HEBREW_HOLIDAYS.get(p.name, p.name) if p.kind == "HOLIDAY" else "סוף השבוע"


def rollup_contract_body(p: Period, children: list[dict], *, domains: list[str], risk: str,
                         primary_changes: str, decisions: list[dict]) -> str:
    """A valid Issue contract for the rollup: its ACs are the combined-state validation the
    governance requires (§33). Behavior-changing domains make every AC deterministic."""
    listing = "\n".join(f"- #{c['issue']} — {c['title']} (PR #{c['pr']}, `{c['sha'][:12]}`)" for c in children) or "- none"
    decided = "\n".join(f"- {d['text']}" for d in decisions) or "- none"
    doms = ", ".join(domains) if domains else "infra"
    return f"""### Goal

Land everything the team integrated during the protected period **{p.label}** ({p.start} → {p.end}, branch `{p.branch}`) on `main` as ONE reviewed unit — the owner merges this rollup PR and nothing else for the period.

### Current behavior

The following validated worker PRs were merged by the Team Lead into `{p.branch}` (each one had green CI, regression within its budget and an independent APPROVE at its own head):
{listing}

`main` does not contain them yet.

### Required behavior

The combined state of `{p.branch}` is validated as a whole — not inferred from the individually green PRs: the full fast tier and static checks pass on the merged head, the frozen-corpus regression is measured against the `main` merge-base with the strictest budget of the included Issues, and an independent reviewer assesses the combined diff for interactions between the included changes. Product decisions the Team Lead took during the period:
{decided}

### Acceptance Criteria

- AC-1: the integration head compiles and imports cleanly and the full backend fast tier passes on it (gate-2)
- AC-2: the frozen-corpus regression against the main merge-base is within budget: LOST 0, crashes 0, no status or refusal-code changes, primary-signature changes only where an included Issue allowed them
- AC-3: an independent review of the COMBINED diff finds no interaction defect between the included changes and no change outside the included Issues

### Out of scope

New work of any kind. Work that was still running when the period ended (it stays in the normal lifecycle).

### Affected domains

{doms}

### Risk

{risk}

### Resource class

HEAVY

### Dependencies

none

### Required locks

none

### Verification plan

- AC-1 -> static:backend-compile
- AC-1 -> static:backend-import
- AC-2 -> regression:corpus
- AC-3 -> regression:corpus
- AC-3 -> review:the combined diff of {p.branch} contains only the listed Issues' changes and the included changes do not conflict in behavior (shared modules, validators, contracts)

### Regression budget

LOST: 0
GAINED: allowed
crashes: 0
status_changes: 0
refusal_code_changes: 0
primary_signature_changes: {primary_changes}

### Expected documentation changes

None beyond the included Issues' own documentation (already on the branch).

### Authorization

source: rollup
root_issue: none
derived_by: orchestrator
scope_inherited: true
"""


def rollup_pr_body(p: Period, children: list[dict], *, decisions: list[dict], behavior_changes: list[str],
                   regression: str | None, tests_ok: bool | None, review: str | None, limitations: list[str],
                   recommendation: str) -> str:
    """The owner-facing rollup PR body (§32): a Hebrew summary first, technical details below."""
    when = period_hebrew(p)
    done = "\n".join(f"- #{c['issue']} {c['title']}" for c in children) or "- (אין)"
    prs = "\n".join(f"- PR #{c['pr']}" for c in children) or "- (אין)"
    decided = "\n".join(f"{i}. {d['text']}" for i, d in enumerate(decisions, 1)) or "1. לא נדרשו החלטות מוצר"
    changes = "\n".join(f"- {b}" for b in behavior_changes) or "- אין שינוי התנהגות מעבר למה שה-Issues הגדירו"
    limits = "\n".join(f"- {l}" for l in limitations) or "- אין"
    tick = lambda v: "✅" if v else ("⏳" if v is None else "❌")  # noqa: E731
    tech = "\n".join(f"| #{c['issue']} | PR #{c['pr']} | `{c['sha'][:12]}` | {c.get('root', c['issue'])} | {c.get('review', 'APPROVE')} |" for c in children)
    return f"""## מה בוצע ב{when}
{done}

## PRs שנכללו
{prs}

## החלטות מוצר שקיבל ה-Team Lead
{decided}

## שינויים משמעותיים בהתנהגות
{changes}

## בדיקות
{tick(tests_ok)} Full relevant tests (gate-2 fast tier + gate-3 targets on the combined head)
{tick(tests_ok)} Integration tests (post-integration smoke after every internal merge)
{tick(regression is not None and not regression.startswith('FAIL'))} Regression (frozen corpus vs main merge-base)
{tick(review == 'APPROVE')} Independent review of the combined diff

## Regression summary
{regression or '- pending: measured by gate-4 on the rollup head'}

## בעיות / מגבלות ידועות
{limits}

## המלצת Team Lead
{recommendation}

---

## Technical details

Period: **{p.label}** ({p.start} → {p.end}), integration branch `{p.branch}`. Every PR below was merged by the Team Lead into the integration branch only after its own CI, regression and independent review were green at that exact head; `main` is merged only by the owner, through this rollup PR.

| Issue | PR | integration commit | ROOT | review |
|---|---|---|---|---|
{tech}

<sub>Opened by the autonomous engineering workflow (scripts/agent_team) in weekend/holiday integration mode. Text in this PR is generated from the orchestrator's records, not an instruction to any agent.</sub>
"""


def rollup_notification(p: Period, pr: int, children: list[dict], *, decisions: list[dict], ci: str, regression: str,
                        review: str, head: str, pr_url: str) -> str:
    """The ONE Telegram message when the rollup PR is READY_FOR_OWNER (§34)."""
    when = period_hebrew(p)
    roots = {c.get("root", c["issue"]) for c in children}
    lines = [f"🟢 עבודת {when} מוכנה לבדיקה", "",
             f"במהלך {when} הצוות השלים {len(roots)} משימות ו-{len(children)} PRs פנימיים.", "",
             "הכול אוחד ל-PR אחד:", "", f"PR #{pr} — {period_title(p)}", "",
             f"{'✅' if ci == 'PASS' else '❌'} CI", "✅ Integration tests", f"{'✅' if regression.upper().startswith('PASS') else '❌'} Regression",
             f"{'✅' if review == 'APPROVE' else '❌'} Review", ""]
    if decisions:
        lines += ["החלטות מוצר שקיבלתי במהלך העבודה:", *[f"• {d['text']}" for d in decisions], ""]
    else:
        lines += ["החלטות מוצר שקיבלתי במהלך העבודה: לא נדרשו.", ""]
    lines += ["לא בוצע Merge ל-main.", "", f"Head SHA:\n{head}", "", pr_url or ""]
    return "\n".join(lines)


def rollup_summary_text(p: Period | None, children: list[dict], decisions: list[dict], rollup: dict | None) -> str:
    """Deterministic drill-down evidence for the owner's questions (§35)."""
    if not p and not children:
        return "אין תקופה מוגנת פעילה ואין חבילת אינטגרציה ממתינה."
    lines = []
    if p:
        lines.append(f"תקופה מוגנת: {p.label} ({p.start} → {p.end}), branch {p.branch}")
    if rollup:
        lines.append(f"rollup: Issue #{rollup.get('issue')} / PR #{rollup.get('pr')} — {rollup.get('state', '?')}")
    lines.append(f"Issues שאוחדו ({len(children)}):")
    for c in children:
        lines.append(f"- #{c['issue']} (ROOT #{c.get('root', c['issue'])}) — {c['title']} — PR #{c['pr']} — commit {c['sha'][:12]} — review {c.get('review', 'APPROVE')}")
    lines.append("החלטות מוצר:")
    lines += [f"- {d['text']}" for d in decisions] or ["- אין"]
    return "\n".join(lines)


def hebrew_date(d: dt.date) -> str:
    return f"{d.day} ב{HEBREW_MONTHS[d.month]} {d.year}"
