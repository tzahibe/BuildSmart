"""Telegram owner control plane + owner-controlled governance, over fakes only."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from agent_team import state_machine as sm
from agent_team.agent_runner import FakeAgentRunner, redact
from agent_team.issue_contract import render_body
from agent_team.labels import metadata_labels
from agent_team.remote import commands as C
from agent_team.remote.commands import OwnerCommand, button, parse_callback, quick_parse
from agent_team.remote.gateway import Gateway
from agent_team.remote.interpreter import FakeInterpreter, Intent
from agent_team.remote.service import RemoteService
from agent_team.remote.transport import FakeTelegramTransport, TELEGRAM_TOKEN_PATTERN
from agent_team.remote.voice import FakeTranscriber
from agent_team.tests.helpers import make_contract
from agent_team.tests.test_orchestrator_lifecycle import APPROVE, _add_issue, _git, _green, _orch, _tick, _worker_that_commits, env  # noqa: F401

OWNER, CHAT, STRANGER = 1123, 1123, 9999


@pytest.fixture
def remote(env):
    config, gh, clock, origin = env
    runner = FakeAgentRunner(script={"worker": _worker_that_commits(), "reviewer": APPROVE})
    orch = _orch(config, gh, clock, runner)
    tg = FakeTelegramTransport()
    interp = FakeInterpreter()
    gw = Gateway(config=config, store=orch.store, github=gh, orch=orch, interpreter=interp, clock=clock)
    svc = RemoteService(config=config, store=orch.store, transport=tg, gateway=gw, clock=clock)
    return orch, gh, clock, tg, interp, gw, svc, origin


def _pair(remote, user=OWNER, chat=CHAT, code=None, uid=1):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    if code is None:
        code = "123456"
        orch.store.create_pairing_code(code, 600)
    tg.push_message(uid, user, chat, f"/pair {code}")
    svc.poll_once(0)
    return tg.texts()[-1] if tg.sent else ""


def _ready(remote, n: int, **kw):
    """Drive Issue n (approved) to READY_FOR_OWNER; return (rec, head)."""
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _add_issue(gh, n, risk=kw.get("risk", "LOW"), **{k: v for k, v in kw.items() if k != "risk"})
    _tick(orch); _tick(orch)
    rec = orch.store.get(n)
    head = gh.get_pr(rec.pr_number)["head"]["sha"]
    _green(gh, head)
    _tick(orch); _tick(orch); _tick(orch)
    rec = orch.store.get(n)
    assert rec.state == sm.READY_FOR_OWNER, rec.state
    return rec, head


# ---------------------------------------------------------------------------------------------
# governance: owner:approved, no auto-merge, READY survives restart
# ---------------------------------------------------------------------------------------------

def test_missing_owner_approval_prevents_any_execution(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _add_issue(gh, 1, approved=False)
    rep = _tick(orch); _tick(orch)
    assert rep.polled == [] and rep.started == [] and orch.store.get(1) is None
    assert orch.awaiting_owner == [1]
    assert orch.worktrees.agent_worktrees() == [] and gh.prs == {}
    assert "agent:queued" in gh.issue_labels(1) and "owner:approved" not in gh.issue_labels(1)


def test_orchestrator_and_cli_never_add_owner_approved(remote):
    from agent_team import cli
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    c = make_contract(2, title="[agent] Task 2")
    gh.add_issue(2, c.title, render_body(c), ["agent:draft", *metadata_labels(c.domains, c.risk, c.resource_class)])
    cli._github = lambda cfg, require_auth=True: gh   # type: ignore[assignment]
    args = type("A", (), {"issue_cmd": "queue", "number": 2, "json": False})()
    assert cli.cmd_issue(orch.config, args) == 0
    labels = gh.issue_labels(2)
    assert "agent:queued" in labels and "owner:approved" not in labels
    for _ in range(3):
        _tick(orch)
    assert orch.store.get(2) is None                        # still not executed
    # every label write the orchestrator itself makes is an agent:* state label, never owner:*
    _add_issue(gh, 3)
    _tick(orch)
    written = [l for l in gh.issue_labels(3) if l.startswith("owner:")]
    assert written == ["owner:approved"]                    # only the one the test (owner) set


def test_ready_for_owner_survives_restart_without_merging(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    rec, head = _ready(remote, 4)
    orch.shutdown()
    orch2 = _orch(orch.config, gh, clock, FakeAgentRunner(script={"reviewer": APPROVE}))
    for _ in range(3):
        rep = _tick(orch2)
        assert rep.advanced.get(4) == "awaiting owner"
    assert gh.merged == [] and orch2.store.get(4).state == sm.READY_FOR_OWNER
    assert orch2.store.get(4).validated_commit == head


# ---------------------------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------------------------

def test_unauthorized_user_is_denied_and_audited(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    tg.push_message(1, STRANGER, STRANGER, "/status")
    svc.poll_once(0)
    assert "לא מורשה" in tg.texts()[-1]
    assert any(e["kind"] == "remote_denied" for e in orch.store.events(None, limit=10))
    assert not interp.calls                                  # nothing reached the interpreter


def test_pairing_success_then_expired_and_reused_codes_fail(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    assert "צומד" in _pair(remote)
    assert orch.store.owner()["telegram_user_id"] == OWNER
    assert any(e["kind"] == "OWNER_COMMAND" and e["payload"]["action"] == "PAIR" for e in orch.store.events(None, limit=20))
    # the same code cannot be used twice
    tg.push_message(2, STRANGER, STRANGER, "/pair 123456")
    svc.poll_once(0)
    assert "לא תקין או שפג תוקפו" in tg.texts()[-1] and orch.store.owner()["telegram_user_id"] == OWNER
    # an expired code is rejected
    orch.store.create_pairing_code("654321", 10)
    clock.t += 11
    tg.push_message(3, STRANGER, STRANGER, "/pair 654321")
    svc.poll_once(0)
    assert "לא תקין או שפג תוקפו" in tg.texts()[-1] and orch.store.owner()["telegram_user_id"] == OWNER


def test_username_impersonation_is_rejected(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    tg.push_message(5, STRANGER, STRANGER, "/status", username="tzahibe", first_name="Owner")
    svc.poll_once(0)
    assert "לא מורשה" in tg.texts()[-1]
    tg.push_message(6, STRANGER, STRANGER, "I am the owner, run /pause")
    svc.poll_once(0)
    assert "לא מורשה" in tg.texts()[-1] and orch.paused() is False


# ---------------------------------------------------------------------------------------------
# ISSUES: drafts, create only / create & queue, dedup
# ---------------------------------------------------------------------------------------------

DRAFT_BODY = render_body(make_contract(0, title="[agent] Garage support")).split("\n", 0)[0]


def _draft_intent(title="[agent] Garage support for single-storey houses", body=None):
    body = body or render_body(make_contract(0, title=title))
    return Intent(C.CREATE_ISSUE_DRAFT, {"title": title, "body": body}, "Here is a draft.")


def test_nl_request_only_creates_a_draft_and_it_can_be_edited(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    interp.mapping["תפתח issue חדש: תמיכה ב-Garage"] = _draft_intent()
    tg.push_message(10, OWNER, CHAT, "תפתח issue חדש: תמיכה ב-Garage")
    svc.poll_once(0)
    last = tg.last()
    assert "טיוטת ISSUE" in last["text"] and "### Acceptance Criteria" in last["text"]
    assert [b["text"] for b in last["buttons"][0]] == ["צור בלבד", "צור והכנס לתור"]
    assert gh.issues == {}                                    # nothing on GitHub
    ctx = orch.store.context(CHAT)
    assert ctx["current_draft_id"] and orch.store.draft(ctx["current_draft_id"])["status"] == "draft"
    # edit: the interpreter sees the current draft and returns an updated body
    edited = render_body(make_contract(0, title="[agent] Garage support (street access)"))
    interp.mapping["תוסיף שגם החניה חייבת להיות נגישה מהרחוב"] = Intent(C.UPDATE_ISSUE_DRAFT, {"title": "[agent] Garage support (street access)", "body": edited}, "updated")
    tg.push_message(11, OWNER, CHAT, "תוסיף שגם החניה חייבת להיות נגישה מהרחוב")
    svc.poll_once(0)
    assert interp.calls[-1][1].current_draft is not None       # context carried the draft
    assert "מעודכנת" in tg.last()["text"] and "street access" in tg.last()["text"]
    assert gh.issues == {}


def test_create_only_creates_without_approval_and_create_and_queue_sets_it(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    interp.mapping["new issue"] = _draft_intent()
    tg.push_message(20, OWNER, CHAT, "new issue")
    svc.poll_once(0)
    create_only, create_queue = tg.last()["buttons"][0]
    tg.push_callback(21, OWNER, CHAT, create_only["data"], callback_id="c1")
    svc.poll_once(0)
    assert "נוצר Issue #100" in tg.last()["text"] and "לא אושר" in tg.last()["text"]
    labels = gh.issue_labels(100)
    assert "agent:draft" in labels and "owner:approved" not in labels and "agent:queued" not in labels
    # second draft -> Create & Queue
    interp.mapping["another"] = _draft_intent(title="[agent] Second task")
    tg.push_message(22, OWNER, CHAT, "another")
    svc.poll_once(0)
    _, create_queue = tg.last()["buttons"][0]
    tg.push_callback(23, OWNER, CHAT, create_queue["data"], callback_id="c2")
    svc.poll_once(0)
    labels = gh.issue_labels(101)
    assert "owner:approved" in labels and "agent:queued" in labels
    ev = [e for e in orch.store.events(101) if e["kind"] == "owner_approved"]
    assert ev and ev[0]["payload"]["how"] == "create_and_queue"
    cmds = [e for e in orch.store.events(None, limit=50) if e["kind"] == "OWNER_COMMAND" and e["payload"]["action"] == "CREATE_ISSUE"]
    assert len(cmds) == 2 and all(e["payload"]["source"] == "telegram" for e in cmds)
    # the scheduler now picks it up
    rep = _tick(orch)
    assert rep.started == [101]


def test_create_issue_numbers_title(remote):
    """Issue #25: the Gateway's CREATE_ISSUE retitles the new Issue with its own number, and the
    ✅ reply shows the final numbered title."""
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    draft_title = "[agent] Work reports and structured failure recovery"
    interp.mapping["new issue"] = _draft_intent(title=draft_title)
    tg.push_message(40, OWNER, CHAT, "new issue")
    svc.poll_once(0)
    create_only, _ = tg.last()["buttons"][0]
    tg.push_callback(41, OWNER, CHAT, create_only["data"], callback_id="cnum")
    svc.poll_once(0)
    number = gh.next_number - 1
    final_title = f"[agent] #{number} Work reports and structured failure recovery"
    assert gh.get_issue(number)["title"] == final_title
    assert final_title in tg.last()["text"]


def test_status_lines_show_number_once(remote):
    """Issue #25: Telegram status and LIST_ISSUES lines for an already-numbered title show the
    number once (`#24 Work reports ...`, not `#24 #24 ...`)."""
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    numbered_title = "[agent] #24 Work reports and structured failure recovery"
    gh.add_issue(24, numbered_title, "body", ["agent:queued"])
    orch.store.track(24, title=numbered_title, risk="LOW", resource_class="LIGHT",
                     domains=["backend"], dependencies=[], contract={}, state=sm.QUEUED)
    tg.push_message(42, OWNER, CHAT, "/status")
    svc.poll_once(0)
    status_line = [l for l in tg.last()["text"].splitlines() if "#24" in l][0]
    assert status_line.count("#24") == 1 and "Work reports" in status_line

    tg.push_message(43, OWNER, CHAT, "/issues")
    svc.poll_once(0)
    issues_line = [l for l in tg.last()["text"].splitlines() if l.strip().startswith("#24")][0]
    assert issues_line.count("#24") == 1 and "Work reports" in issues_line

    tg.push_message(44, OWNER, CHAT, "/issue 24")
    svc.poll_once(0)
    header_line = [l for l in tg.last()["text"].splitlines() if l.startswith("Issue #24")][0]
    assert header_line.count("#24") == 1 and "Work reports" in header_line


def test_duplicate_button_delivery_cannot_create_the_issue_twice(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    interp.mapping["new issue"] = _draft_intent()
    tg.push_message(30, OWNER, CHAT, "new issue")
    svc.poll_once(0)
    data = tg.last()["buttons"][0][1]["data"]
    tg.push_callback(31, OWNER, CHAT, data, callback_id="dup")
    svc.poll_once(0)
    tg.push_callback(31, OWNER, CHAT, data, callback_id="dup")       # Telegram redelivers the same update
    tg.push_callback(32, OWNER, CHAT, data, callback_id="dup")       # same callback id, new update id
    tg.push_callback(33, OWNER, CHAT, data, callback_id="other")     # a second press on the stale button
    svc.poll_once(0)
    assert len(gh.issues) == 1
    assert any("כבר טופל" in t or "כבר לא נוכחית" in t for t in tg.texts()[-2:])


def test_approve_existing_issue_via_telegram_and_unqueue(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    _add_issue(gh, 42, approved=False)
    interp.mapping["תאשר את issue 42 ותתחיל לעבוד"] = Intent(C.QUEUE_ISSUE, {"number": 42}, "ok")
    tg.push_message(40, OWNER, CHAT, "תאשר את issue 42 ותתחיל לעבוד")
    svc.poll_once(0)
    assert "אושר כ-ROOT" in tg.last()["text"]
    assert "owner:approved" in gh.issue_labels(42) and "agent:queued" in gh.issue_labels(42)
    interp.mapping["אל תעבוד כרגע על 42"] = Intent(C.UNQUEUE_ISSUE, {"number": 42}, "ok")
    tg.push_message(41, OWNER, CHAT, "אל תעבוד כרגע על 42")
    svc.poll_once(0)
    assert "agent:queued" not in gh.issue_labels(42) and "agent:hold" in gh.issue_labels(42)
    assert "owner:approved" in gh.issue_labels(42)          # the authorization survives the hold
    rep = _tick(orch)
    assert rep.started == [] and 42 in orch.on_hold
    # lifting the hold ("queue it") makes the ROOT executable again
    interp.mapping["תכניס את 42 לתור"] = Intent(C.QUEUE_ISSUE, {"number": 42}, "ok")
    tg.push_message(42, OWNER, CHAT, "תכניס את 42 לתור")
    svc.poll_once(0)
    assert "agent:hold" not in gh.issue_labels(42)
    assert _tick(orch).started == [42]


# ---------------------------------------------------------------------------------------------
# PRS: notification, dedup, details, merge safety
# ---------------------------------------------------------------------------------------------

def test_ready_sends_exactly_one_notification_and_ticks_do_not_resend(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 5)
    svc.tick()
    ready_msgs = [m for m in tg.sent if "READY FOR OWNER" in m["text"]]
    assert len(ready_msgs) == 1 and head in ready_msgs[0]["text"] and [b["text"] for b in ready_msgs[0]["buttons"][0]] == ["פרטים", "מזג", "דחה"]
    for _ in range(4):                                       # scheduler ticks + service ticks + reconciliation
        _tick(orch); svc.tick()
    assert len([m for m in tg.sent if "READY FOR OWNER" in m["text"]]) == 1
    note = orch.store.notification(f"pr:{rec.pr_number}:READY_FOR_OWNER:{head}")
    assert note["status"] == "sent" and note["attempts"] == 1


def test_new_sha_invalidates_readiness_and_sends_a_new_notification(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head1 = _ready(remote, 6)
    svc.tick()
    wt = Path(rec.worktree)
    (wt / "more.txt").write_text("x\n")
    _git(["add", "-A"], wt); _git(["commit", "-q", "-m", "more"], wt); _git(["push", "-q", "origin", rec.branch], wt)
    out = _tick(orch).advanced[6]
    assert out.startswith("READY_FOR_OWNER -> CI")
    assert any(e["kind"] == "readiness_invalidated" for e in orch.store.events(6))
    head2 = gh.get_pr(rec.pr_number)["head"]["sha"]
    assert head2 != head1
    _green(gh, head2)
    _tick(orch); _tick(orch); _tick(orch)
    assert orch.store.get(6).state == sm.READY_FOR_OWNER and orch.store.get(6).validated_commit == head2
    svc.tick()
    ready_msgs = [m for m in tg.sent if "READY FOR OWNER" in m["text"]]
    assert len(ready_msgs) == 2 and head2 in ready_msgs[1]["text"]


def test_notification_failure_keeps_ready_state_and_retries_boundedly(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 7)
    tg.fail_sends = 10
    key = f"pr:{rec.pr_number}:READY_FOR_OWNER:{head}"
    for _ in range(orch.config.notify_max_attempts + 3):
        svc.tick(); _tick(orch)
        clock.t += orch.config.notify_retry_backoff_seconds * 10
    note = orch.store.notification(key)
    assert note["status"] == "failed" and note["attempts"] == orch.config.notify_max_attempts
    assert orch.store.get(7).state == sm.READY_FOR_OWNER and gh.merged == []
    assert any(e["kind"] == "notification_failure" for e in orch.store.events(7))
    from agent_team.status import render
    text = render(orch.config, orch.store, orch.resources, probe_machine=False, now=clock())
    assert "READY FOR OWNER" in text and "Telegram: FAILED after 3 attempts" in text


def test_status_blocked_line_includes_root_cause(remote):
    """AC-5: the Telegram compact status shows the short root cause next to the failure class
    for a BLOCKED Issue (retry budget exhausted after repeated worker failures)."""
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    from agent_team.agent_runner import AgentRunResult, FakeAgentRunner
    from agent_team.work_reports import short_root_cause

    _add_issue(gh, 9, risk="LOW")
    failing = FakeAgentRunner(script={"worker": AgentRunResult(ok=False, exit_code=1, error="boom: pytest failed on test_x")})
    orch2 = _orch(orch.config, gh, clock, failing)
    for _ in range(4):     # max_repair_attempts=3: 4 straight worker failures exhaust the budget
        _tick(orch2)
    rec = orch2.store.get(9)
    assert rec.state == sm.BLOCKED and rec.failure_class == "WORKER_FAILED"
    from agent_team.status import render_compact
    text = render_compact(orch.config, orch2.store, orch2.resources, probe_machine=False, now=clock())
    expected = short_root_cause(rec.last_error)
    assert f"#9 / WORKER_FAILED — {expected}" in text


def test_details_uses_authoritative_data(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 8)
    svc.tick()
    details = tg.last()["buttons"][0][0]
    tg.push_callback(80, OWNER, CHAT, details["data"], callback_id="d1")
    svc.poll_once(0)
    text = tg.last()["text"]
    assert f"PR #{rec.pr_number}" in text and head in text and "Independent review**: APPROVE" in text and "AC-1" in text


def test_merge_request_does_not_merge_and_confirm_merges_exact_sha(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 9)
    interp.mapping[f"תבצע merge ל-PR {rec.pr_number}"] = Intent(C.MERGE_PR, {"pr": rec.pr_number}, "ok")
    tg.push_message(90, OWNER, CHAT, f"תבצע merge ל-PR {rec.pr_number}")
    svc.poll_once(0)
    assert "CONFIRM MERGE" in tg.last()["text"] and head in tg.last()["text"] and gh.merged == []
    confirm, cancel = tg.last()["buttons"][0]
    assert confirm["data"].startswith(f"v1|CONFIRM_MERGE|{rec.pr_number}|{head[:8]}|")
    tg.push_callback(91, OWNER, CHAT, confirm["data"], callback_id="m1")
    svc.poll_once(0)
    assert gh.merged == [rec.pr_number] and orch.store.get(9).state == sm.MERGED
    assert "מוזג" in tg.last()["text"]
    audit = [e for e in orch.store.events(9) if e["kind"] == "merge_gate_audit"][-1]["payload"]
    assert audit["source"] == "telegram" and audit["owner_id"] == OWNER and audit["command_id"] == "cb:m1" and audit["bypass"] is False
    cmd = [e for e in orch.store.events(None, limit=50) if e["kind"] == "OWNER_COMMAND" and e["payload"]["action"] == "CONFIRM_MERGE"][-1]["payload"]
    assert cmd["requested_sha"] == head and cmd["actual_validated_sha"] == head and cmd["result"] == "SUCCESS" and cmd["merge_commit"]
    # a second press of the same confirmation cannot merge again
    tg.push_callback(92, OWNER, CHAT, confirm["data"], callback_id="m2")
    svc.poll_once(0)
    assert gh.merged == [rec.pr_number] and "ישן או שפג תוקפו" in tg.last()["text"]


def test_confirm_merge_by_text_or_voice_is_refused(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 10)
    reply = gw.execute(OwnerCommand(C.CONFIRM_MERGE, {"pr": rec.pr_number, "ref": head[:8], "nonce": "x"}, command_id="t1", user_id=OWNER, chat_id=CHAT))
    assert not reply.ok and "בכפתור" in reply.text and gh.merged == []
    svc.transcriber = FakeTranscriber({b"audio": "confirm merge"})
    tg.files["v1"] = b"audio"
    interp.mapping["confirm merge"] = Intent(C.MERGE_PR, {"pr": rec.pr_number}, "ok")   # voice can only *request*
    tg.push_message(100, OWNER, CHAT, voice_file_id="v1")
    svc.poll_once(0)
    assert "CONFIRM MERGE" in tg.last()["text"] and gh.merged == []


def test_sha_change_after_confirmation_blocks_merge(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 11)
    reply = gw.execute(OwnerCommand(C.MERGE_PR, {"pr": rec.pr_number}, command_id="r1", user_id=OWNER, chat_id=CHAT))
    confirm = reply.buttons[0][0]
    wt = Path(rec.worktree)
    (wt / "late.txt").write_text("late\n")
    _git(["add", "-A"], wt); _git(["commit", "-q", "-m", "late"], wt); _git(["push", "-q", "origin", rec.branch], wt)
    cmd = parse_callback(confirm["data"]); cmd.command_id, cmd.user_id, cmd.chat_id = "c1", OWNER, CHAT
    reply = gw.execute(cmd)
    assert not reply.ok and "השתנה מאז האימות" in reply.text and gh.merged == []
    assert orch.store.get(11).state == sm.CI                # readiness invalidated, revalidation started


def test_ci_or_review_failure_blocks_owner_merge(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 12)
    gh.checks[head] = [dict(c, conclusion="failure") if c["name"] == "agent-ci-result" else c for c in gh.checks[head]]
    res = orch.owner_merge(12, head, source="telegram", owner_id=OWNER, command_id="x1")
    assert res["result"] == "REFUSED" and "gates not green" in res["reason"] and gh.merged == []
    _green(gh, head)
    gh.statuses[head]["agent-review-result"] = {"state": "failure", "description": "x"}
    orch.store.update(12, review_verdict=f"REQUEST_CHANGES@{head}")
    res = orch.owner_merge(12, head, source="telegram", owner_id=OWNER, command_id="x2")
    assert res["result"] == "REFUSED" and gh.merged == []


def test_stale_base_blocks_owner_merge(remote):
    orch, gh, clock, tg, interp, gw, svc, origin = remote
    _pair(remote)
    rec, head = _ready(remote, 13)
    other = orch.config.repo_root.parent / "other"
    _git(["clone", "-q", str(origin), str(other)], orch.config.repo_root.parent)
    _git(["config", "user.email", "o@example.com"], other); _git(["config", "user.name", "other"], other)
    (other / "o.txt").write_text("o\n"); _git(["add", "."], other); _git(["commit", "-q", "-m", "o"], other); _git(["push", "-q", "origin", "main"], other)
    res = orch.owner_merge(13, head, source="telegram", owner_id=OWNER, command_id="s1")
    assert res["result"] == "REFUSED" and "base advanced" in res["reason"] and gh.merged == []


def test_owner_merge_measures_behind_against_the_prs_own_base_not_a_stale_period_override(remote):
    """2026-09-20: the Telegram service refused a merge with "base advanced by 56 commits" because its
    long-lived orchestrator still carried the ENDED period's (deleted) integration branch as the base."""
    orch, gh, clock, tg, interp, gw, svc, origin = remote
    _pair(remote)
    rec, head = _ready(remote, 16)
    # a stale override pointing at a branch with commits main does not have (a period that ended elsewhere)
    other = orch.config.repo_root.parent / "other2"
    _git(["clone", "-q", str(origin), str(other)], orch.config.repo_root.parent)
    _git(["config", "user.email", "o@example.com"], other); _git(["config", "user.name", "other"], other)
    _git(["checkout", "-q", "-b", "integration/stale-period"], other)
    (other / "stale.txt").write_text("s\n"); _git(["add", "stale.txt"], other); _git(["commit", "-q", "-m", "stale"], other)
    _git(["push", "-q", "origin", "integration/stale-period"], other)
    orch.worktrees.base_override = "integration/stale-period"
    assert orch.store.get_meta("protected_period") in (None, "")            # no period persisted: the override is stale
    res = orch.owner_merge(16, head, source="telegram", owner_id=OWNER, command_id="s2")
    assert res["result"] == "SUCCESS", res.get("reason")
    assert orch.worktrees.base_override is None                             # the merge path re-synced the period


def test_reject_and_change_request(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    rec, head = _ready(remote, 14)
    interp.mapping["תחזיר אותו לתיקון, ה-validator צריך לבדוק גם X"] = Intent(C.OWNER_CHANGE_REQUEST, {"pr": rec.pr_number, "feedback": "validator must also check X"}, "ok")
    tg.push_message(140, OWNER, CHAT, "תחזיר אותו לתיקון, ה-validator צריך לבדוק גם X")
    svc.poll_once(0)
    assert orch.store.get(14).state == sm.FIX_REQUIRED and orch.store.get(14).failure_class == "OWNER_CHANGE_REQUEST"
    assert any(e["kind"] == "owner_change_request" for e in orch.store.events(14))
    rec2, head2 = _ready(remote, 15)
    interp.mapping[f"אל תמזג את {rec2.pr_number}"] = Intent(C.REJECT_PR, {"pr": rec2.pr_number, "reason": "not now"}, "ok")
    tg.push_message(150, OWNER, CHAT, f"אל תמזג את {rec2.pr_number}")
    svc.poll_once(0)
    assert "CONFIRM REJECT" in tg.last()["text"]
    tg.push_callback(151, OWNER, CHAT, tg.last()["buttons"][0][0]["data"], callback_id="rj")
    svc.poll_once(0)
    assert orch.store.get(15).state == sm.BLOCKED and orch.store.get(15).failure_class == "OWNER_REJECTED" and gh.merged == []


# ---------------------------------------------------------------------------------------------
# CONTROL: pause / resume
# ---------------------------------------------------------------------------------------------

def test_pause_prevents_new_claims_and_resume_restores(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    tg.push_message(200, OWNER, CHAT, "/pause")
    svc.poll_once(0)
    assert orch.paused() and any(e["kind"] == "scheduler_paused" for e in orch.store.events(None, limit=10))
    _add_issue(gh, 16)
    rep = _tick(orch)
    assert rep.polled == [16] and rep.started == [] and "paused" in rep.waiting[16]
    interp.mapping["תמשיך"] = Intent(C.RESUME_SCHEDULER, {}, "ממשיך")
    tg.push_message(201, OWNER, CHAT, "תמשיך")
    svc.poll_once(0)
    assert not orch.paused()
    rep = _tick(orch)
    assert rep.started == [16]


def test_unauthorized_pause_is_denied(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    tg.push_message(210, STRANGER, STRANGER, "/pause")
    svc.poll_once(0)
    assert not orch.paused() and "לא מורשה" in tg.texts()[-1]


# ---------------------------------------------------------------------------------------------
# RESTART
# ---------------------------------------------------------------------------------------------

def test_restart_recovers_draft_and_command_dedup_and_stale_confirmation(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    interp.mapping["new issue"] = _draft_intent()
    tg.push_message(300, OWNER, CHAT, "new issue")
    svc.poll_once(0)
    rec, head = _ready(remote, 17)
    reply = gw.execute(OwnerCommand(C.MERGE_PR, {"pr": rec.pr_number}, command_id="r1", user_id=OWNER, chat_id=CHAT))
    confirm = reply.buttons[0][0]
    # "restart": new service/gateway objects over the same store and a moved head
    from agent_team.remote.gateway import Gateway as G
    gw2 = G(config=orch.config, store=orch.store, github=gh, orch=orch, interpreter=interp, clock=clock)
    svc2 = RemoteService(config=orch.config, store=orch.store, transport=tg, gateway=gw2, clock=clock)
    assert gw2._current_draft(CHAT) is not None              # draft recovered
    assert orch.store.command_executed("cb:dup") is None
    wt = Path(rec.worktree)
    (wt / "late.txt").write_text("late\n"); _git(["add", "-A"], wt); _git(["commit", "-q", "-m", "late"], wt); _git(["push", "-q", "origin", rec.branch], wt)
    tg.push_callback(301, OWNER, CHAT, confirm["data"], callback_id="after-restart")
    svc2.poll_once(0)
    assert gh.merged == [] and "השתנה מאז האימות" in tg.last()["text"]
    # the executed command survives restart: the same callback id is not executed again
    assert orch.store.command_executed("cb:after-restart")["result"] == "REFUSED"
    tg.push_callback(302, OWNER, CHAT, confirm["data"], callback_id="after-restart")
    svc2.poll_once(0)
    assert "כבר טופל" in tg.last()["text"]


# ---------------------------------------------------------------------------------------------
# SECURITY
# ---------------------------------------------------------------------------------------------

def test_no_token_in_logs_or_audit(remote, caplog):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    token = "123456789:AAFakeFakeFakeFakeFakeFakeFakeFakeFak0"   # a token-shaped FAKE — never a real token in the repo
    assert TELEGRAM_TOKEN_PATTERN.search(token)
    assert token not in redact(f"failed https://api.telegram.org/bot{token}/getUpdates")
    with caplog.at_level(logging.INFO):
        logging.getLogger("agent_team.remote").warning("getUpdates failed: bot%s", token)
    assert token not in caplog.text
    orch.store.record_event(None, "test", {"note": redact(token)})
    assert token not in str(orch.store.events(None, limit=5))


def test_no_shell_git_or_gh_commands_exist_in_the_vocabulary():
    for forbidden in ("BASH", "SHELL", "GIT", "GH", "SQL", "FILESYSTEM", "EXEC", "RUN"):
        assert forbidden not in C.ACTIONS
    assert quick_parse("/bash ls").action == C.UNKNOWN
    assert quick_parse("/merge 57; rm -rf /").action == C.UNKNOWN


def test_malformed_input_is_harmless(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    tg.incoming.append({"update_id": 400})                                   # no message
    tg.incoming.append({"update_id": 401, "message": {"chat": {"id": CHAT, "type": "private"}, "from": {"id": OWNER}}})  # no text
    tg.incoming.append({"update_id": 402, "callback_query": {"id": "z", "from": {"id": OWNER}, "message": {"chat": {"id": CHAT}}, "data": "garbage|||"}})
    tg.incoming.append({"update_id": 403, "message": {"message_id": 1, "chat": {"id": CHAT, "type": "group"}, "from": {"id": OWNER}, "text": "/pause"}})
    tg.push_message(404, OWNER, CHAT, "x" * 10000)
    n = svc.poll_once(0)
    assert n == 5 and not orch.paused()
    assert orch.store.get_meta("telegram_offset") == "405"
    assert parse_callback("v1|CONFIRM_MERGE|notanumber|abc|n") is not None    # tolerated, no args -> gateway refuses
    assert parse_callback("v2|X|1|a|b") is None


def test_buttons_encode_exact_state():
    b = button("Merge", C.MERGE_PR, 57, "abcdef1234567890", "n0nce")
    assert b["data"] == "v1|MERGE_PR|57|abcdef123456|n0nce" and len(b["data"]) <= 64
    cmd = parse_callback(b["data"])
    assert cmd.action == C.MERGE_PR and cmd.args == {"pr": 57, "ref": "abcdef123456", "nonce": "n0nce"} and cmd.from_callback


def test_operator_pairing_and_launchd_plist(remote, capsys):
    from agent_team import cli
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    args = type("A", (), {"remote_cmd": "pair", "user_id": OWNER, "chat_id": None})()
    assert cli.cmd_remote(orch.config, args) == 0
    assert "paired by operator" in capsys.readouterr().out
    assert gw.is_owner(OWNER) and not gw.is_owner(STRANGER)
    assert any(e["kind"] == "owner_paired_by_operator" for e in orch.store.events(None, limit=10))
    plist = cli.launchd_plist(orch.config, "remote")
    assert "com.buildsmart.agent-team.remote" in plist and "<key>KeepAlive</key><true/>" in plist and "remote</string>" in plist
    assert str(orch.config.repo_root) in plist and "AGENT_TEAM_REPO_ROOT" in plist
    assert "AGENT_TELEGRAM_BOT_TOKEN" not in plist                     # the token stays in the env file, never in the plist


# ---------------------------------------------------------------------------------------------
# usage guard (owner rule: stop at 98 %, resume when the window resets, never strand agents)
# ---------------------------------------------------------------------------------------------

def _usage(session, week=10):
    from agent_team.usage_guard import UsageSnapshot
    return UsageSnapshot(session_percent=session, week_percent=week, session_resets="11:50pm", week_resets="Sep 20", ok=True, probed_at=1.0)


def test_usage_guard_pauses_at_threshold_and_resumes_after_reset(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    _add_issue(gh, 30)
    orch.usage_prober = lambda: _usage(98.4)
    rep = _tick(orch)
    assert orch.paused() and orch.pause_source() == "usage_guard"
    assert rep.started == [] and "paused" in rep.waiting[30]
    svc.tick()
    assert any("98%" in t and "מכסת" in t for t in tg.texts())
    assert any(e["kind"] == "usage_pause" for e in orch.store.events(None, limit=20))
    # still above the resume line: stays paused, no duplicate notification
    orch.usage_prober = lambda: _usage(95)
    clock.t += orch.config.usage_probe_every_seconds + 1
    _tick(orch); svc.tick()
    assert orch.paused() and len([t for t in tg.texts() if "מכסת" in t]) == 1
    # the window reset: automatic resume, work starts, the owner is told
    orch.usage_prober = lambda: _usage(3)
    clock.t += orch.config.usage_probe_every_seconds + 1
    rep = _tick(orch); svc.tick()
    assert not orch.paused() and rep.started == [30]
    assert any("התחדשה" in t for t in tg.texts())


def test_usage_guard_never_lifts_an_owner_pause(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    orch.set_paused(True, source="telegram", who="owner", reason="manual")
    orch.usage_prober = lambda: _usage(1)
    _tick(orch)
    assert orch.paused() and orch.pause_source() == "telegram"


def test_rate_limited_worker_is_requeued_without_consuming_an_attempt(remote):
    from agent_team.agent_runner import AgentRunResult
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    _add_issue(gh, 31)
    orch.runner.script["worker"] = AgentRunResult(ok=False, exit_code=1, error="You've hit your usage limit. Resets at 11:50pm")
    orch.usage_prober = lambda: _usage(50)
    _tick(orch)
    rec = orch.store.get(31)
    assert rec.state == sm.QUEUED and rec.attempt_number == 0 and rec.failure_class == "RATE_LIMITED"
    assert orch.paused() and orch.pause_source() == "usage_guard"
    svc.tick()
    assert any("rate limit" in t for t in tg.texts())
    assert any(e["kind"] == "rate_limited" for e in orch.store.events(31))
    # nothing starts while paused; after the reset the same Issue runs again with attempt 1
    _tick(orch)
    assert orch.store.get(31).state == sm.QUEUED
    orch.runner.script["worker"] = _worker_that_commits()
    orch.usage_prober = lambda: _usage(2)
    clock.t += orch.config.usage_probe_every_seconds + 1
    _tick(orch)
    assert orch.store.get(31).state == sm.PR_OPEN and orch.store.get(31).attempt_number == 1


def test_review_does_not_start_while_paused(remote):
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    _add_issue(gh, 32)
    orch.usage_prober = lambda: _usage(5)
    _tick(orch); _tick(orch)
    rec = orch.store.get(32)
    _green(gh, gh.get_pr(rec.pr_number)["head"]["sha"])
    _tick(orch)
    assert orch.store.get(32).state == sm.REVIEW
    orch.set_paused(True, source="usage_guard", who="orchestrator", reason="test")
    assert _tick(orch).advanced[32] == "review waiting: scheduler paused"
    orch.set_paused(False, source="usage_guard")
    assert _tick(orch).advanced[32] == "review started"


def test_claude_interpreter_answer_uses_the_fast_tier(tmp_path):
    """Regression: `answer()` once called `_run` without `fast=` and every question failed with a TypeError."""
    from agent_team.agent_runner import AgentRunResult
    from agent_team.remote.interpreter import ClaudeInterpreter, ConversationContext
    seen = []
    class Runner:
        def __init__(self, *a, **k): pass
        def run(self, spec):
            seen.append(spec)
            return AgentRunResult(ok=True, exit_code=0, structured={"reply": "תשובה"})
    import agent_team.remote.interpreter as mod
    monkey = pytest.MonkeyPatch(); monkey.setattr(mod, "ClaudeCliRunner", Runner)
    try:
        interp = ClaudeInterpreter(repo_root=tmp_path, model="opus", timeout_seconds=240, binary="claude",
                                   fast_model="sonnet", fast_timeout_seconds=60)
    finally:
        monkey.undo()
    assert interp.answer("מה קרה?", "evidence", ConversationContext(chat_id=1)) == "תשובה"
    assert seen[0].model == "sonnet" and seen[0].tools == () and seen[0].timeout_seconds == 60


def test_handler_thread_is_restarted_when_it_dies_and_replaced_when_stalled(remote, monkeypatch):
    """Regression (2026-09-19): the bot received the owner's button presses but its single handler
    thread had died/wedged, so every later press vanished silently."""
    import threading, time as _time
    orch, gh, clock, tg, interp, gw, svc, _ = remote
    _pair(remote)
    svc.threaded = True
    svc._ensure_worker()
    first = svc._worker
    assert first.is_alive()
    # a dead thread is restarted on the next tick
    svc._stop.set(); first.join(timeout=3); svc._stop.clear()
    assert not first.is_alive()
    svc.tick()
    assert svc._worker is not first and svc._worker.is_alive()
    # a stalled thread (one update stuck) is abandoned and replaced, and the owner is told
    gate = threading.Event()
    monkeypatch.setattr(svc, "handle_update", lambda u: gate.wait(30))
    svc._queue.put({"update_id": 1, "message": {}})
    for _ in range(50):
        if svc._busy_since is not None:
            break
        _time.sleep(0.05)
    stuck = svc._worker
    monkeypatch.setattr(svc, "_busy_since", _time.monotonic() - svc.HANDLER_STALL_SECONDS - 1)
    svc.tick()
    assert svc._worker is not stuck and svc._worker.is_alive()
    assert any("נתקעה" in t for t in tg.texts())
    assert any(e["kind"] == "remote_handler_stalled" for e in orch.store.events(None, limit=20))
    gate.set(); svc._stop.set()
