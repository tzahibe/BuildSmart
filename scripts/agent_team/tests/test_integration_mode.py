"""Weekend / Jewish-holiday autonomous integration mode (governance §26–§41), over fakes and a
temp git origin. The calendar is exercised on real 2026 dates; the lifecycle on a fake clock
that is moved into and out of a protected period.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agent_team import state_machine as sm
from agent_team.agent_runner import FakeAgentRunner
from agent_team.integration_mode import period_title, rollup_contract_body, rollup_notification, rollup_pr_body
from agent_team.issue_contract import parse_contract
from agent_team.labels import ROLLUP_LABEL
from agent_team.protected_periods import Calendar, Period
from agent_team.tests.helpers import KNOWN_LOCKS
from agent_team.tests.test_governance_parallel import _child, _finish, _root, _to_ready  # noqa: F401
from agent_team.tests.test_orchestrator_lifecycle import (  # noqa: F401
    APPROVE, _add_issue, _git, _green, _orch, _owner_merge, _tick, _worker_that_commits, env,
)

TZ = ZoneInfo("Asia/Jerusalem")

#: the fake reviewer marks every AC a contract may carry (the rollup has AC-1..AC-3, AC-3 semantic)
APPROVE_ALL = {**APPROVE, "ac_assessment": [{"ac": f"AC-{i}", "verdict": "MET", "note": ""} for i in range(1, 12)]}


def _runner():
    return FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE_ALL})


def _at(day: str, hour: int = 10) -> float:
    return dt.datetime.fromisoformat(day).replace(hour=hour, tzinfo=TZ).timestamp()


# ---------------------------------------------------------------------------------------------
# calendar (§26, §40): deterministic, Hebrew-calendar based, Asia/Jerusalem
# ---------------------------------------------------------------------------------------------

def test_calendar_knows_weekends_and_the_listed_holidays_from_erev_to_end():
    c = Calendar()
    assert c.classify(dt.date(2026, 9, 17)) == (None, None)                       # Thursday
    assert c.classify(dt.date(2026, 9, 18)) == ("SHABBAT", "weekend")             # Friday
    assert c.classify(dt.date(2026, 9, 19)) == ("SHABBAT", "weekend")             # Saturday
    assert c.classify(dt.date(2026, 9, 20)) == ("EREV", "Yom Kippur")             # Erev Yom Kippur
    assert c.classify(dt.date(2026, 9, 21)) == ("HOLIDAY", "Yom Kippur")
    assert c.classify(dt.date(2026, 9, 22)) == (None, None)
    assert c.classify(dt.date(2026, 9, 25)) == ("EREV", "Succos")                 # Friday = Erev Sukkot
    assert c.classify(dt.date(2026, 9, 29)) == ("HOLIDAY", "Succos")              # Chol HaMoed counts
    assert c.classify(dt.date(2026, 10, 3)) == ("HOLIDAY", "Shmini Atzeres")
    assert c.classify(dt.date(2026, 10, 4)) == (None, None)
    assert c.classify(dt.date(2026, 5, 21)) == ("EREV", "Shavuos")
    assert c.classify(dt.date(2026, 5, 22)) == ("HOLIDAY", "Shavuos")
    assert c.classify(dt.date(2026, 9, 12)) == ("SHABBAT", "weekend")             # Rosh Hashanah is NOT configured
    assert c.classify(dt.date(2026, 4, 2)) == (None, None)                        # Erev Pesach is NOT configured


def test_adjacent_protected_days_form_one_period_named_after_the_holiday():
    c = Calendar()
    p = c.period_containing(dt.date(2026, 9, 19))
    assert (p.start, p.end, p.kind, p.name) == (dt.date(2026, 9, 18), dt.date(2026, 9, 21), "HOLIDAY", "Yom Kippur")
    assert p.branch == "integration/holiday-yom-kippur-2026"
    s = c.period_containing(dt.date(2026, 9, 30))
    assert (s.start, s.end, s.branch) == (dt.date(2026, 9, 25), dt.date(2026, 10, 3), "integration/holiday-sukkot-2026")
    w = c.period_containing(dt.date(2026, 9, 12))
    assert (w.start, w.end, w.kind, w.branch) == (dt.date(2026, 9, 11), dt.date(2026, 9, 12), "SHABBAT", "integration/weekend-2026-09-11")
    assert c.period_containing(dt.date(2026, 9, 23)) is None
    assert c.next_period(dt.date(2026, 9, 22)).start == dt.date(2026, 9, 25)
    assert period_title(w) == "Weekend Integration — 11–12 Sep 2026"
    assert period_title(p).startswith("Yom Kippur Integration")


def test_calendar_config_is_validated_and_timezone_aware():
    c = Calendar.from_config({"weekdays": ["fri", "sat"], "holidays": ["yom_kippur"], "erev": False})
    assert c.classify(dt.date(2026, 9, 20)) == (None, None)                       # no erev
    assert c.classify(dt.date(2026, 9, 21)) == ("HOLIDAY", "Yom Kippur")
    with pytest.raises(ValueError):
        Calendar.from_config({"holidays": ["purim"]})
    # 23:30 UTC Thursday is already Friday 02:30 in Jerusalem
    ts = dt.datetime(2026, 9, 17, 23, 30, tzinfo=dt.timezone.utc).timestamp()
    assert Calendar().today(lambda: ts) == dt.date(2026, 9, 18)


# ---------------------------------------------------------------------------------------------
# lifecycle: integration branch, autonomous integration, rollup, owner merge (§27–§34, §41)
# ---------------------------------------------------------------------------------------------

def _enter_period(orch, clock, day="2026-09-19"):
    clock.t = _at(day)
    rep = _tick(orch)
    assert orch.period is not None, rep.summary()
    return orch.period


def test_period_starts_with_one_integration_branch_and_survives_restart(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    assert p.branch == "integration/holiday-yom-kippur-2026" and orch.worktrees.base_override == p.branch
    assert orch.worktrees.branch_exists(p.branch, remote=True)
    ev = [e for e in orch.store.events(None, limit=50) if e["kind"] == "PROTECTED_PERIOD_STARTED"]
    assert len(ev) == 1 and ev[0]["payload"]["type"] == "HOLIDAY" and ev[0]["payload"]["integration_branch"] == p.branch
    # a fresh orchestrator (restart) resumes the same period and branch
    orch2 = _orch(config, gh, clock, _runner())
    assert orch2.period == p and orch2.worktrees.base_override == p.branch
    assert len([e for e in orch2.store.events(None, limit=50) if e["kind"] == "PROTECTED_PERIOD_STARTED"]) == 1
    _tick(orch2)
    assert len([e for e in orch2.store.events(None, limit=50) if e["kind"] == "PROTECTED_PERIOD_STARTED"]) == 1


def test_green_prs_are_integrated_by_the_lead_never_merged_to_main(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    _add_issue(gh, 70)
    _tick(orch)
    rec = orch.store.get(70)
    pr = gh.get_pr(rec.pr_number)
    assert pr["base"]["ref"] == p.branch                     # new PRs target the integration branch
    _to_ready_or_integrated(orch, gh, 70)
    rec = orch.store.get(70)
    assert rec.state == sm.INTEGRATED and gh.merged == [rec.pr_number]
    assert gh.get_pr(rec.pr_number)["base"]["ref"] == p.branch
    # main is untouched, the integration branch carries the work, locks are free, dependency satisfied
    root = config.repo_root
    _git(["fetch", "-q", "origin"], root)
    assert "work-70.txt" not in _git(["ls-tree", "--name-only", "origin/main"], root).stdout
    assert "work-70.txt" in _git(["ls-tree", "--name-only", f"origin/{p.branch}"], root).stdout
    assert not any(l.issue_id == 70 for l in orch.store.locks_held())
    assert orch.integrations()[0]["issue"] == 70 and "agent:integrated" in gh.issue_labels(70)
    assert any(e["kind"] == "integration_smoke" and e["payload"]["ok"] for e in orch.store.events(70))
    # the owner's merge command does not apply to an integrated child (nothing is READY for main)
    assert _owner_merge(orch, 70, sha=rec.validated_commit)["result"] == "REFUSED"


def _to_ready_or_integrated(orch, gh, issue_id):
    for _ in range(6):
        rec = orch.store.get(issue_id)
        if rec.state in (sm.READY_FOR_OWNER, sm.INTEGRATED):
            return rec
        _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
        _tick(orch)
    raise AssertionError(orch.store.get(issue_id).state)


def test_dependents_start_from_the_integration_branch_and_work_continues(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    _root(gh, 120, locks="docs (shared)")
    _child(gh, 121)
    _child(gh, 122, deps="#121")
    _tick(orch)
    _to_ready_or_integrated(orch, gh, 121)
    assert orch.store.get(121).state == sm.INTEGRATED
    rep = _tick(orch)                                        # the dependent starts at once: INTEGRATED satisfies it
    assert rep.started == [122]
    rec = orch.store.get(122)
    assert "work-121.txt" in _git(["ls-tree", "--name-only", "HEAD"], rec.worktree).stdout   # built on the integrated work
    _to_ready_or_integrated(orch, gh, 122)
    assert [i["issue"] for i in orch.integrations()] == [121, 122]


def test_period_end_opens_one_rollup_pr_validated_as_a_whole_then_owner_merges(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    _add_issue(gh, 70)
    _add_issue(gh, 71)
    _tick(orch)
    for n in (70, 71):
        _to_ready_or_integrated(orch, gh, n)
    orch.record_decision("kept the guest-WC pocket rule as-is (owner not reachable)", issue_id=71)
    # the period ends: one rollup Issue + PR, main still untouched
    clock.t = _at("2026-09-22")
    rep = _tick(orch)
    assert orch.period is None and orch.worktrees.base_override is None
    ru = orch.rollup()
    assert ru and ru["children"] == [70, 71]
    rrec = orch.store.get(ru["issue"])
    assert rrec.kind == "rollup" and rrec.state in (sm.PR_OPEN, sm.CI) and rrec.pr_number == ru["pr"]
    rpr = gh.get_pr(ru["pr"])
    assert rpr["base"]["ref"] == "main" and rpr["head"]["ref"] == p.branch
    assert "## מה בוצע ב" in rpr["body"] and "#70" in rpr["body"] and "#71" in rpr["body"] and "guest-WC" in rpr["body"]
    assert ROLLUP_LABEL in gh.issue_labels(ru["issue"])
    ended = [e for e in orch.store.events(None, limit=100) if e["kind"] == "PROTECTED_PERIOD_ENDED"]
    assert ended and ended[-1]["payload"]["rollup_pr"] == ru["pr"]
    assert gh.merged == [orch.store.get(70).pr_number, orch.store.get(71).pr_number]   # only integration merges so far
    # the rollup goes through CI + independent review of the combined diff, then ONE notification
    rrec = _to_ready(orch, gh, ru["issue"])
    assert rrec.state == sm.READY_FOR_OWNER and rrec.review_verdict.startswith("APPROVE")
    notes = [n for n in orch.store.due_notifications(limit=50) if n["kind"] == "ready_for_owner"]
    assert len(notes) == 1 and "עבודת" in notes[0]["text"] and f"PR #{ru['pr']}" in notes[0]["text"] and "לא בוצע Merge ל-main" in notes[0]["text"]
    assert "guest-WC" in notes[0]["text"]
    assert "MERGE RECOMMENDED" in gh.get_pr(ru["pr"])["body"]
    # nobody merged main meanwhile
    root = config.repo_root
    _git(["fetch", "-q", "origin"], root)
    assert "work-70.txt" not in _git(["ls-tree", "--name-only", "origin/main"], root).stdout
    # the owner merges the rollup: main gets everything, children close, branch and mode state are gone
    res = _owner_merge(orch, ru["issue"])
    assert res["result"] == "SUCCESS"
    for _ in range(3):
        _tick(orch)
        if orch.store.get(ru["issue"]).state == sm.DONE:
            break
    assert orch.store.get(ru["issue"]).state == sm.DONE
    assert orch.store.get(70).state == sm.DONE and orch.store.get(71).state == sm.DONE
    assert gh.get_issue(70)["state"] == "closed" and gh.get_issue(71)["state"] == "closed"
    _git(["fetch", "-q", "-p", "origin"], root)
    assert "work-70.txt" in _git(["ls-tree", "--name-only", "origin/main"], root).stdout
    assert not orch.worktrees.branch_exists(p.branch, remote=True)
    assert orch.rollup() is None and orch.integrations() == []


def test_period_end_without_integrated_work_is_quiet(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    clock.t = _at("2026-09-22")
    rep = _tick(orch)
    assert orch.period is None and orch.rollup() is None
    assert not orch.worktrees.branch_exists(p.branch, remote=True)
    assert any("nothing integrated" in r for r in rep.reconciled)


def test_integration_smoke_failure_reverts_the_merge_and_sends_the_issue_back(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    # the worker's change breaks the smoke command (`test -f README.md`)
    def breaks_smoke(spec):
        readme = Path(spec.cwd) / "README.md"
        if readme.exists():                                   # the first run breaks the smoke; a repair run would fix it
            readme.unlink()
            _git(["add", "-A"], spec.cwd)
            _git(["commit", "-q", "-m", "oops: removes README"], spec.cwd)
        return _worker_that_commits()(spec)
    orch.runner.script["worker"] = breaks_smoke
    _add_issue(gh, 72)
    _tick(orch)
    for _ in range(8):                                        # integrate -> smoke red -> revert -> repair run
        if any(e["kind"] == "integration_smoke" and not e["payload"]["ok"] for e in orch.store.events(72)):
            break
        rec = orch.store.get(72)
        if rec.pr_number:
            _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
        _tick(orch)
    events = orch.store.events(72)
    assert any(e["kind"] == "integrated" for e in events)
    assert any(e["kind"] == "integration_smoke" and not e["payload"]["ok"] for e in events)
    assert any(e["kind"] == "transition" and e["payload"]["to"] == sm.FIX_REQUIRED for e in events)
    assert orch.store.get(72).failure_class == "INTEGRATION_FAILURE"
    assert orch.integrations() == []
    root = config.repo_root
    _git(["fetch", "-q", "origin"], root)
    assert "README.md" in _git(["ls-tree", "--name-only", f"origin/{p.branch}"], root).stdout   # reverted
    assert any(e["kind"] == "lead_decision" and "reverted" in e["payload"]["text"] for e in orch.store.events(72))


def test_owner_can_exclude_an_issue_from_the_rollup(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    p = _enter_period(orch, clock)
    _add_issue(gh, 70)
    _add_issue(gh, 71)
    _tick(orch)
    for n in (70, 71):
        _to_ready_or_integrated(orch, gh, n)
    clock.t = _at("2026-09-22")
    _tick(orch)
    ru = orch.rollup()
    _to_ready(orch, gh, ru["issue"])
    res = orch.rollup_exclude(70, source="telegram", who=1, reason="לא רוצה את זה בחבילה")
    assert res["result"] == "SUCCESS"
    assert orch.store.get(70).state == sm.BLOCKED and orch.store.get(70).failure_class == "OWNER_EXCLUDED"
    assert orch.rollup()["children"] == [71] and [i["issue"] for i in orch.integrations()] == [71]
    root = config.repo_root
    _git(["fetch", "-q", "origin"], root)
    tree = _git(["ls-tree", "--name-only", f"origin/{p.branch}"], root).stdout
    assert "work-70.txt" not in tree and "work-71.txt" in tree
    rep = _tick(orch)                                        # the rollup's head moved: readiness invalidated, re-validating
    assert orch.store.get(ru["issue"]).state == sm.CI
    assert any(e["kind"] == "lead_decision" and "excluded" in e["payload"]["text"] for e in orch.store.events(70))


def test_owner_change_request_on_the_rollup_waits_for_the_lead_not_a_worker(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    _enter_period(orch, clock)
    _add_issue(gh, 70)
    _tick(orch)
    _to_ready_or_integrated(orch, gh, 70)
    clock.t = _at("2026-09-22")
    _tick(orch)
    ru = orch.rollup()
    _to_ready(orch, gh, ru["issue"])
    res = orch.owner_change_request(ru["issue"], source="telegram", owner_id=1, command_id="c1", feedback="שנה את החלטת המוצר לגבי X")
    assert res["result"] == "SUCCESS" and res.get("rollup")
    rec = orch.store.get(ru["issue"])
    assert rec.state == sm.BLOCKED and rec.failure_class == "OWNER_CHANGE_REQUEST"
    assert _tick(orch).started == []                          # no repair worker is spawned for a rollup


def test_rollup_contract_and_body_render_and_validate():
    p = Period(dt.date(2026, 9, 18), dt.date(2026, 9, 21), "HOLIDAY", "Yom Kippur", "integration/holiday-yom-kippur-2026")
    children = [{"issue": 70, "pr": 100, "sha": "a" * 40, "title": "Entrance policy", "root": 70, "review": "APPROVE"},
                {"issue": 71, "pr": 101, "sha": "b" * 40, "title": "Windows", "root": 60, "review": "APPROVE"}]
    body = rollup_contract_body(p, children, domains=["backend", "geometry"], risk="MEDIUM", primary_changes="40", decisions=[{"text": "kept X"}])
    c = parse_contract(99, "[agent] Yom Kippur Integration — 18–21 Sep 2026", body, known_locks=KNOWN_LOCKS)
    assert c.authorization.source == "rollup" and c.needs_regression(("backend", "geometry")) and c.budget_rule("primary_signature_changes").limit == 40
    pr_body = rollup_pr_body(p, children, decisions=[{"text": "kept X"}], behavior_changes=[], regression="PASS (0 lost)", tests_ok=True,
                             review="APPROVE", limitations=[], recommendation="MERGE RECOMMENDED")
    assert "## מה בוצע ביום כיפור" in pr_body and "1. kept X" in pr_body and "| #71 | PR #101 |" in pr_body
    note = rollup_notification(p, 120, children, decisions=[{"text": "kept X"}], ci="PASS", regression="PASS", review="APPROVE", head="c" * 40, pr_url="u")
    assert "🟢 עבודת יום כיפור מוכנה לבדיקה" in note and "2 משימות ו-2 PRs" in note and "• kept X" in note and "לא בוצע Merge ל-main" in note


def test_no_period_means_the_normal_owner_gate(env):
    config, gh, clock, origin = env
    orch = _orch(config, gh, clock, _runner())
    clock.t = _at("2026-09-23")                              # Wednesday
    _add_issue(gh, 70)
    _tick(orch)
    assert orch.period is None and gh.get_pr(orch.store.get(70).pr_number)["base"]["ref"] == "main"
    rec = _to_ready_or_integrated(orch, gh, 70)
    assert rec.state == sm.READY_FOR_OWNER and gh.merged == []
