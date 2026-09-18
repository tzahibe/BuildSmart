"""The owner command gateway: the only thing that turns a typed command into an action.

Order of checks for every command: pairing/authorization (numeric Telegram user id only) ->
replay protection (command_id) -> authoritative state re-read (GitHub + orchestrator DB) ->
action -> audit (OWNER_COMMAND event with source, action, entity, result). Merges and rejects
need a second, button-only confirmation bound to the exact validated SHA with a short-lived
nonce; a stale button is refused.
"""
from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass

from agent_team import state_machine as sm
from agent_team.config import Config
from agent_team.issue_contract import ContractError, numbered_title, parse_contract, render_body, strip_title_number
from agent_team.labels import metadata_labels
from agent_team.orchestrator import Orchestrator, render_ready_report
from agent_team.remote import commands as C
from agent_team.remote.commands import OwnerCommand, Reply, button
from agent_team.remote.interpreter import ConversationContext, Interpreter
from agent_team.state_store import StateStore

log = logging.getLogger("agent_team.remote.gateway")


@dataclass
class Gateway:
    config: Config
    store: StateStore
    github: object
    orch: Orchestrator
    interpreter: Interpreter
    clock: object = time.time

    # -- authorization --------------------------------------------------------------------
    def is_owner(self, user_id: int | None) -> bool:
        owner = self.store.owner()
        return bool(owner) and user_id is not None and int(owner["telegram_user_id"]) == int(user_id)

    def owner_chat_id(self) -> int | None:
        owner = self.store.owner()
        return int(owner["chat_id"]) if owner else None

    # -- entry point ----------------------------------------------------------------------
    def execute(self, cmd: OwnerCommand) -> Reply:
        if cmd.action == C.PAIR:
            return self._pair(cmd)
        if not self.is_owner(cmd.user_id):
            self.store.record_event(None, "remote_denied", {"action": cmd.action, "user_id": cmd.user_id, "chat_id": cmd.chat_id})
            return Reply.deny("⛔ לא מורשה. הבוט הזה עונה רק לבעלים המצומד (agentctl remote pair).")
        if cmd.action in C.BUTTON_ONLY and not cmd.from_callback:
            return Reply(f"את {cmd.action} אפשר לאשר רק בכפתור — לעולם לא בטקסט או בקול.", ok=False)
        if cmd.action in C.MUTATING:
            prior = self.store.command_executed(cmd.command_id) if cmd.command_id else None
            if prior:
                return Reply(f"כבר טופל ({prior['action']} → {prior['result']}). שום דבר לא בוצע פעמיים.")
        handler = getattr(self, "_do_" + cmd.action.lower(), None)
        if handler is None:
            return Reply(f"פעולה לא נתמכת: {cmd.action}.", ok=False)
        try:
            reply = handler(cmd)
        except Exception as exc:  # noqa: BLE001 — a bug in a handler must never crash the service
            log.exception("command %s failed", cmd.action)
            self._audit(cmd, "ERROR", {"error": str(exc)[:300]})
            return Reply(f"הפקודה נכשלה: {str(exc)[:200]}", ok=False)
        return reply

    def _audit(self, cmd: OwnerCommand, result: str, payload: dict | None = None) -> None:
        if not cmd.command_id:
            cmd.command_id = f"auto:{cmd.action}:{int(self.clock() * 1000)}:{secrets.token_hex(3)}"
        self.store.record_command(cmd.command_id, cmd.action, cmd.entity, cmd.source, cmd.user_id, result, payload)

    # -- pairing --------------------------------------------------------------------------
    def _pair(self, cmd: OwnerCommand) -> Reply:
        code = str(cmd.args.get("code", ""))
        if cmd.user_id is None or cmd.chat_id is None:
            return Reply.deny("צימוד אפשרי רק בצ'אט פרטי.")
        if not self.store.consume_pairing_code(code):
            self.store.record_event(None, "pairing_rejected", {"user_id": cmd.user_id})
            return Reply.deny("קוד הצימוד לא תקין או שפג תוקפו. בקש מהמפעיל להריץ שוב `agentctl remote pair`.")
        self.store.set_owner(int(cmd.user_id), int(cmd.chat_id))
        self._audit(cmd, "SUCCESS", {"paired_user_id": cmd.user_id})
        return Reply(f"✅ צומד. משתמש טלגרם {cmd.user_id} הוא עכשיו הבעלים של האורקסטרטור. שלח /help לרשימת הפקודות.")

    # -- read-only ------------------------------------------------------------------------
    def _do_get_status(self, cmd: OwnerCommand) -> Reply:
        from agent_team.status import render_compact
        return Reply(render_compact(self.config, self.store, self.orch.resources, probe_machine=True, now=self.clock()))

    _do_get_agents = _do_get_status

    def _do_help(self, cmd: OwnerCommand) -> Reply:
        return Reply(C.HELP_TEXT)

    def _do_unknown(self, cmd: OwnerCommand) -> Reply:
        return Reply(cmd.args.get("reply") or "לא הבנתי. נסה /help.")

    def _do_list_issues(self, cmd: OwnerCommand) -> Reply:
        want = (cmd.args.get("state") or "open").lower()
        labels = ("agent:queued",) if want == "queued" else ()
        issues = self.github.list_issues(labels=labels, state="open")
        lines = []
        for i in issues[:30]:
            names = [l["name"] for l in i.get("labels", [])]
            rec = self.store.get(i["number"])
            tags = [n for n in names if n.startswith(("agent:", "owner:", "risk:"))]
            lines.append(f"#{i['number']} {strip_title_number(i['title'])[:60]}\n   {' '.join(tags)}" + (f" | orchestrator: {rec.state}" if rec else ""))
        return Reply("Issues פתוחים:\n" + ("\n".join(lines) if lines else "(אין)"))

    def _do_get_issue(self, cmd: OwnerCommand) -> Reply:
        n = int(cmd.args["number"])
        issue = self.github.get_issue(n)
        names = [l["name"] for l in issue.get("labels", [])]
        rec = self.store.get(n)
        try:
            c = parse_contract(n, issue.get("title", ""), issue.get("body") or "", known_locks=self.config.known_locks,
                               behavior_domains=self.config.behavior_domains)
            contract = (f"חוזה תקין: {c.risk}/{c.resource_class} · תחומים {', '.join(c.domains)} · {len(c.acceptance_criteria)} קריטריונים · "
                        f"תלויות {list(c.dependencies) or 'אין'}\nמטרה: {c.goal[:300]}")
        except ContractError as exc:
            contract = "חוזה לא תקין: " + "; ".join(exc.problems)[:300]
        state = f"אורקסטרטור: {rec.state}" + (f", PR #{rec.pr_number}" if rec and rec.pr_number else "") if rec else "אורקסטרטור: לא במעקב"
        approved = self.config.owner_approval_label in names
        text = (f"Issue #{n}: {issue.get('title')}\nGitHub: {issue.get('state')} · תוויות {', '.join(names) or '-'}\n{state}\n"
                f"אישור בעלים: {'כן' if approved else 'לא'}\n{contract}\n{issue.get('html_url', '')}")
        buttons = []
        if issue.get("state") == "open" and not approved:
            buttons = [[button("אשר והכנס לתור", C.QUEUE_ISSUE, n), button("אשר בלבד", C.APPROVE_ISSUE, n)]]
        return Reply(text, buttons)

    def _do_list_ready_prs(self, cmd: OwnerCommand) -> Reply:
        recs = self.store.list((sm.READY_FOR_OWNER,))
        if not recs:
            return Reply("אין PR שממתין לך כרגע.")
        lines, buttons = ["PRs שממתינים לאישורך (READY FOR OWNER):"], []
        for r in recs:
            sha = (r.validated_commit or "")[:12]
            lines.append(f"PR #{r.pr_number} — Issue #{r.issue_id} {strip_title_number(r.title)[:60]}\n   סיכון {r.risk} · SHA {sha} · ביקורת {(r.review_verdict or '-').split('@')[0]}")
            buttons.append([button(f"פרטים #{r.pr_number}", C.GET_PR_DETAILS, r.pr_number, sha[:8]),
                            button(f"מזג #{r.pr_number}", C.MERGE_PR, r.pr_number, sha[:8]),
                            button(f"דחה #{r.pr_number}", C.REJECT_PR, r.pr_number, sha[:8])])
        return Reply("\n".join(lines), buttons)

    def _rec_for_pr(self, pr: int):
        for r in self.store.list():
            if r.pr_number == pr:
                return r
        return None

    def _do_get_pr_details(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args["pr"])
        rec = self._rec_for_pr(pr)
        if rec is None:
            return Reply(f"PR #{pr} אינו במעקב האורקסטרטור.", ok=False)
        self.store.set_context(cmd.chat_id, current_pr=pr)
        head = rec.validated_commit or self.github.get_pr(pr)["head"]["sha"]
        report = self.orch.ready_report(rec, head)
        text = render_ready_report(report) if rec.state == sm.READY_FOR_OWNER else \
            (f"PR #{pr} (Issue #{rec.issue_id}) במצב {rec.state}" + (f" — {rec.failure_class}: {rec.last_error}" if rec.failure_class else "") +
             f"\n{rec.pr_url or ''}")
        buttons = []
        if rec.state == sm.READY_FOR_OWNER:
            buttons = [[button("מזג", C.MERGE_PR, pr, head[:8]), button("דחה", C.REJECT_PR, pr, head[:8])]]
        return Reply(text, buttons)

    def _pr_evidence(self, rec) -> str:
        """Authoritative evidence pack for PR questions: contract, diff, CI, review, audit."""
        from pathlib import Path
        from agent_team import ci_evidence
        parts = [f"ISSUE #{rec.issue_id}: {rec.title}", f"STATE: {rec.state}  PR #{rec.pr_number}  validated SHA {rec.validated_commit}"]
        d = rec.contract_dict()
        parts.append("CONTRACT:\n" + (d.get("body") or "")[:6000])
        try:
            ev = ci_evidence.collect(self.github, self.config, rec.validated_commit or self.github.get_pr(rec.pr_number)["head"]["sha"], fetch_logs=False)
            parts.append("CI EVIDENCE:\n" + ev.summary_markdown())
        except Exception as exc:  # noqa: BLE001
            parts.append(f"CI EVIDENCE: unavailable ({exc})")
        try:
            files = self.github.pr_files(rec.pr_number)
            parts.append("FILES CHANGED:\n" + "\n".join(files[:100]))
        except Exception:  # noqa: BLE001
            pass
        try:
            if rec.worktree and Path(rec.worktree).exists():
                parts.append("DIFF (base...head):\n" + self.orch.worktrees.diff(Path(rec.worktree), self.orch.worktrees.base_ref(), max_bytes=40000))
        except Exception:  # noqa: BLE001
            pass
        events = self.store.events(rec.issue_id, limit=200)
        keep = ("ci_failed", "review_verdict", "review_failed", "worker_report", "merged", "readiness_invalidated", "owner_change_request", "smoke")
        parts.append("AUDIT TRAIL:\n" + "\n".join(f"{e['kind']}: {str(e['payload'])[:400]}" for e in events if e["kind"] in keep))
        return "\n\n".join(parts)

    def _do_pr_question(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args.get("pr") or self.store.context(cmd.chat_id).get("current_pr") or 0)
        rec = self._rec_for_pr(pr) if pr else None
        if rec is None:
            return Reply("על איזה PR? ציין מספר (למשל PR 57).", ok=False)
        self.store.set_context(cmd.chat_id, current_pr=pr)
        ctx = self._context(cmd.chat_id)
        return Reply(self.interpreter.answer(cmd.args.get("question") or cmd.raw_text, self._pr_evidence(rec), ctx))

    def _do_ask(self, cmd: OwnerCommand) -> Reply:
        from agent_team.status import render_compact
        evidence = "STATUS:\n" + render_compact(self.config, self.store, self.orch.resources, probe_machine=False, now=self.clock())
        evidence += "\n\nRECENT EVENTS:\n" + "\n".join(f"#{e['issue_id']} {e['kind']}: {str(e['payload'])[:200]}" for e in self.store.events(None, limit=40))
        return Reply(self.interpreter.answer(cmd.args.get("question") or cmd.raw_text, evidence, self._context(cmd.chat_id)))

    # -- issue drafts ---------------------------------------------------------------------
    def _validate_draft(self, title: str, body: str) -> list[str]:
        try:
            parse_contract(0, title, body, known_locks=self.config.known_locks, behavior_domains=self.config.behavior_domains)
            return []
        except ContractError as exc:
            return list(exc.problems)

    def _render_draft(self, d: dict, prefix: str = "טיוטת ISSUE") -> Reply:
        problems = d.get("problems") or []
        text = f"{prefix} ({d['draft_id']})\n\n# {d['title']}\n\n{d['body']}"
        if problems:
            text += "\n\n⚠️ הטיוטה עדיין לא תקינה:\n" + "\n".join(f"- {p}" for p in problems[:8]) + "\n\nכתוב לי מה לשנות."
            buttons = [[button("ערוך", C.SHOW_DRAFT, d["draft_id"]), button("בטל", C.CANCEL_DRAFT, d["draft_id"])]]
        else:
            buttons = [[button("צור בלבד", C.CREATE_ISSUE, d["draft_id"], "draft"), button("צור והכנס לתור", C.CREATE_ISSUE, d["draft_id"], "queue")],
                       [button("ערוך", C.SHOW_DRAFT, d["draft_id"]), button("בטל", C.CANCEL_DRAFT, d["draft_id"])]]
        return Reply(text, buttons)

    def _do_create_issue_draft(self, cmd: OwnerCommand) -> Reply:
        title = (cmd.args.get("title") or "").strip()
        body = (cmd.args.get("body") or "").strip()
        if not title.lower().startswith("[agent]"):
            title = "[agent] " + title
        if not body:
            return Reply("צריך עוד פרטים כדי לנסח את ה-Issue — מה צריך להשתנות, ואיך נאמת את זה?", ok=False)
        draft_id = f"d{int(self.clock())}{secrets.token_hex(2)}"
        problems = self._validate_draft(title, body)
        self.store.save_draft(draft_id, cmd.chat_id, title, body, problems)
        self.store.set_context(cmd.chat_id, current_draft_id=draft_id)
        self.store.record_event(None, "issue_draft_created", {"draft_id": draft_id, "chat_id": cmd.chat_id, "valid": not problems})
        return self._render_draft(self.store.draft(draft_id))

    def _current_draft(self, chat_id: int) -> dict | None:
        did = self.store.context(chat_id).get("current_draft_id")
        d = self.store.draft(did) if did else None
        return d if d and d["status"] == "draft" else None

    def _do_update_issue_draft(self, cmd: OwnerCommand) -> Reply:
        d = self._current_draft(cmd.chat_id)
        if d is None:
            return Reply("אין טיוטה לעריכה. תאר את ה-Issue החדש ואנסח אותו.", ok=False)
        title = (cmd.args.get("title") or d["title"]).strip()
        body = (cmd.args.get("body") or "").strip() or d["body"]
        if not title.lower().startswith("[agent]"):
            title = "[agent] " + title
        problems = self._validate_draft(title, body)
        self.store.save_draft(d["draft_id"], cmd.chat_id, title, body, problems)
        self.store.record_event(None, "issue_draft_updated", {"draft_id": d["draft_id"], "valid": not problems})
        return self._render_draft(self.store.draft(d["draft_id"]), prefix="טיוטת ISSUE (מעודכנת)")

    def _do_show_draft(self, cmd: OwnerCommand) -> Reply:
        d = self._current_draft(cmd.chat_id)
        if d is None:
            return Reply("אין טיוטה נוכחית.")
        r = self._render_draft(d)
        r.text += "\n\nשלח את השינויים כהודעה ואעדכן את הטיוטה."
        return r

    def _do_cancel_draft(self, cmd: OwnerCommand) -> Reply:
        d = self._current_draft(cmd.chat_id)
        if d is None:
            return Reply("אין טיוטה נוכחית.")
        self.store.finish_draft(d["draft_id"], "cancelled")
        self.store.set_context(cmd.chat_id, current_draft_id=None)
        self.store.record_event(None, "issue_draft_cancelled", {"draft_id": d["draft_id"]})
        return Reply("הטיוטה בוטלה.")

    def _do_create_issue(self, cmd: OwnerCommand) -> Reply:
        d = self._current_draft(cmd.chat_id)
        if cmd.args.get("draft_id") and (d is None or d["draft_id"] != cmd.args["draft_id"]):
            return Reply("הטיוטה הזאת כבר לא נוכחית (כפתור ישן).", ok=False)
        if d is None:
            return Reply("אין טיוטה ליצירה. תאר קודם את ה-Issue.", ok=False)
        problems = self._validate_draft(d["title"], d["body"])
        if problems:
            return Reply("הטיוטה לא תקינה:\n" + "\n".join(f"- {p}" for p in problems[:8]), ok=False)
        c = parse_contract(0, d["title"], d["body"], known_locks=self.config.known_locks, behavior_domains=self.config.behavior_domains)
        queue = bool(cmd.args.get("queue"))
        labels = metadata_labels(c.domains, c.risk, c.resource_class)
        # owner:approved is added ONLY here, on the paired owner's explicit "Create & Queue".
        labels = (["agent:queued", self.config.owner_approval_label] if queue else ["agent:draft"]) + labels
        issue = self.github.create_issue(c.title, render_body(c), labels)
        number = issue["number"]
        final_title = numbered_title(number, issue["title"])
        issue = self.github.update_issue(number, title=final_title)
        self.store.finish_draft(d["draft_id"], "created", number)
        self.store.set_context(cmd.chat_id, current_draft_id=None)
        self._audit(cmd, "SUCCESS", {"issue": number, "queued": queue, "labels": labels, "draft_id": d["draft_id"]})
        if queue:
            self.store.record_event(number, "owner_approved", {"source": cmd.source, "owner_id": cmd.user_id, "how": "create_and_queue"})
        return Reply(f"✅ נוצר Issue #{number}: {final_title}\n{issue.get('html_url', '')}\n" +
                     ("אושר והוכנס לתור — הסקדיולר ייקח אותו." if queue else "נוצר בלבד (agent:draft) — לא אושר ולא בתור."))

    # -- existing issues ------------------------------------------------------------------
    def _do_approve_issue(self, cmd: OwnerCommand) -> Reply:
        n = int(cmd.args["number"])
        queue = bool(cmd.args.get("queue"))
        issue = self.github.get_issue(n)
        if issue.get("state") != "open":
            return Reply(f"Issue #{n} אינו פתוח.", ok=False)
        try:
            parse_contract(n, issue.get("title", ""), issue.get("body") or "", known_locks=self.config.known_locks,
                           behavior_domains=self.config.behavior_domains)
        except ContractError as exc:
            self._audit(cmd, "REFUSED", {"issue": n, "reason": "contract invalid"})
            return Reply(f"אי אפשר לאשר את Issue #{n}: החוזה לא תקין:\n" + "\n".join(f"- {p}" for p in exc.problems[:8]), ok=False)
        names = {l["name"] for l in issue.get("labels", [])}
        # Governance: the owner's approval makes this a ROOT Issue and authorizes its execution in full —
        # claiming, queueing, decomposition, workers, PRs, CI, review. Only the merge stays with the owner.
        add = [l for l in [self.config.owner_approval_label, "agent:queued"] if l not in names]
        if add:
            self.github.add_labels(n, add)
        if "agent:hold" in names:
            self.github.remove_label(n, "agent:hold")
        self.github.set_state_label(n, sm.QUEUED)
        rec = self.store.get(n)
        if rec and rec.state == sm.BLOCKED and rec.failure_class in ("OWNER_HOLD", "OWNER_UNQUEUED"):
            self.store.transition(n, sm.QUEUED, allowed_from=(sm.BLOCKED,), note="re-authorized by the owner", failure_class=None, last_error=None)
        self.store.record_event(n, "owner_approved", {"source": cmd.source, "owner_id": cmd.user_id, "queued": True, "root": True})
        self._audit(cmd, "SUCCESS", {"issue": n, "queued": True, "added": add})
        return Reply(f"✅ Issue #{n} אושר כ-ROOT — ה-team lead מבצע אותו במלואו (פירוק, workers, PR, CI, review); רק ה-merge אצלך.")

    def _do_queue_issue(self, cmd: OwnerCommand) -> Reply:
        cmd.args["queue"] = True
        return self._do_approve_issue(cmd)

    def _do_unqueue_issue(self, cmd: OwnerCommand) -> Reply:
        n = int(cmd.args["number"])
        rec = self.store.get(n)
        if rec and rec.state not in (sm.QUEUED, sm.DONE, sm.BLOCKED):
            self._audit(cmd, "REFUSED", {"issue": n, "reason": f"already {rec.state}"})
            return Reply(f"Issue #{n} כבר במצב {rec.state}; השתמש ב-/pause כדי לעצור עבודה חדשה, או דחה את ה-PR שלו בהמשך.", ok=False)
        # `agent:hold` keeps an authorized Issue (and its children) out of execution until the owner lifts it.
        self.github.remove_label(n, "agent:queued")
        self.github.add_labels(n, ["agent:hold"])
        if rec and rec.state == sm.QUEUED:
            self.store.transition(n, sm.BLOCKED, note="on hold by the owner", failure_class="OWNER_HOLD")
        self._audit(cmd, "SUCCESS", {"issue": n})
        return Reply(f"Issue #{n} הושם בהמתנה (agent:hold) — האישור נשמר, לא יבוצע עד שתגיד 'תכניס לתור'.")

    # -- merge / reject with confirmation -------------------------------------------------
    def _ready_rec(self, pr: int):
        rec = self._rec_for_pr(pr)
        if rec is None:
            return None, Reply(f"PR #{pr} אינו במעקב.", ok=False)
        if rec.state != sm.READY_FOR_OWNER:
            return None, Reply(f"PR #{pr} במצב {rec.state}, לא READY_FOR_OWNER — אין מה לאשר.", ok=False)
        return rec, None

    def _pending(self, chat_id: int, kind: str) -> dict | None:
        pm = self.store.context(chat_id).get("pending_merge")
        if not pm or pm.get("kind") != kind:
            return None
        if pm.get("expires_at", 0) < self.clock():
            self.store.set_context(chat_id, pending_merge=None)
            return None
        return pm

    def _do_merge_pr(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args["pr"])
        rec, err = self._ready_rec(pr)
        if err:
            return err
        head = self.github.get_pr(pr)["head"]["sha"]
        if head != rec.validated_commit:
            return Reply(f"PR #{pr} השתנה מאז האימות (head {head[:12]} ≠ מאומת {str(rec.validated_commit)[:12]}). "
                         "נדרש אימות מחדש — האורקסטרטור יריץ שוב את השערים.", ok=False)
        nonce = C.new_nonce()
        self.store.set_context(cmd.chat_id, pending_merge={"kind": "merge", "pr": pr, "issue": rec.issue_id, "sha": rec.validated_commit,
                                                           "nonce": nonce, "expires_at": self.clock() + self.config.merge_confirmation_ttl_seconds})
        text = (f"CONFIRM MERGE — אישור מיזוג\n\nPR #{pr}\nIssue #{rec.issue_id} {rec.title[:70]}\nסיכון: {rec.risk}\nSHA מאומת: {rec.validated_commit}\n"
                f"CI: PASS\nרגרסיה: PASS\nביקורת: {(rec.review_verdict or '-').split('@')[0]}\n\n"
                f"לחיצה על CONFIRM MERGE היא האישור שלך. תוקף: {self.config.merge_confirmation_ttl_seconds // 60} דקות.")
        return Reply(text, [[button("CONFIRM MERGE", C.CONFIRM_MERGE, pr, rec.validated_commit[:8], nonce),
                             button("ביטול", C.CANCEL_MERGE, pr, rec.validated_commit[:8], nonce)]])

    def _do_confirm_merge(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args["pr"])
        pm = self._pending(cmd.chat_id, "merge")
        if pm is None or pm["pr"] != pr or pm.get("nonce") != cmd.args.get("nonce"):
            self._audit(cmd, "REFUSED", {"pr": pr, "reason": "no matching pending confirmation (stale or expired button)"})
            return Reply("האישור הזה ישן או שפג תוקפו. בקש שוב merge כדי לקבל אישור חדש.", ok=False)
        if not pm["sha"].startswith(cmd.args.get("ref", "")):
            self._audit(cmd, "REFUSED", {"pr": pr, "reason": "button SHA mismatch"})
            return Reply("הכפתור הזה שייך ל-SHA אחר. נדרש אימות מחדש.", ok=False)
        self.store.set_context(cmd.chat_id, pending_merge=None)   # one confirmation, one attempt
        res = self.orch.owner_merge(pm["issue"], pm["sha"], source="telegram", owner_id=cmd.user_id, command_id=cmd.command_id)
        self._audit(cmd, res["result"], {"pr": pr, "issue": pm["issue"], "requested_sha": pm["sha"],
                                        "actual_validated_sha": res.get("actual_validated_sha"), "merge_commit": res.get("merge_commit"),
                                        "reason": res.get("reason")})
        if res["result"] == "SUCCESS":
            return Reply(f"✅ PR #{pr} מוזג (squash {str(res.get('merge_commit'))[:12]}) ב-SHA המאומת {pm['sha'][:12]}. בדיקת ה-smoke שאחרי המיזוג רצה; "
                         "ה-Issue ייסגר כשהיא ירוקה.")
        return Reply(f"❌ לא מוזג: {res.get('reason')}", ok=False)

    def _do_cancel_merge(self, cmd: OwnerCommand) -> Reply:
        self.store.set_context(cmd.chat_id, pending_merge=None)
        return Reply("בוטל. שום דבר לא מוזג.")

    def _do_reject_pr(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args["pr"])
        rec, err = self._ready_rec(pr)
        if err:
            return err
        nonce = C.new_nonce()
        reason = (cmd.args.get("reason") or "").strip() or "נדחה על ידי הבעלים"
        self.store.set_context(cmd.chat_id, pending_merge={"kind": "reject", "pr": pr, "issue": rec.issue_id, "sha": rec.validated_commit,
                                                           "nonce": nonce, "reason": reason,
                                                           "expires_at": self.clock() + self.config.merge_confirmation_ttl_seconds})
        return Reply(f"CONFIRM REJECT — אישור דחייה\n\nPR #{pr} (Issue #{rec.issue_id})\nסיבה: {reason}\n\nה-Issue יהפוך ל-BLOCKED (OWNER_REJECTED); ה-PR נשאר פתוח לסגירה שלך.",
                     [[button("CONFIRM REJECT", C.CONFIRM_REJECT, pr, rec.validated_commit[:8], nonce), button("ביטול", C.CANCEL_MERGE, pr, rec.validated_commit[:8], nonce)]])

    def _do_confirm_reject(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args["pr"])
        pm = self._pending(cmd.chat_id, "reject")
        if pm is None or pm["pr"] != pr or pm.get("nonce") != cmd.args.get("nonce"):
            self._audit(cmd, "REFUSED", {"pr": pr, "reason": "stale/expired confirmation"})
            return Reply("האישור הזה ישן או שפג תוקפו.", ok=False)
        self.store.set_context(cmd.chat_id, pending_merge=None)
        res = self.orch.owner_reject(pm["issue"], source="telegram", owner_id=cmd.user_id, command_id=cmd.command_id, reason=pm.get("reason", ""))
        self._audit(cmd, res["result"], {"pr": pr, "issue": pm["issue"], "reason": pm.get("reason")})
        return Reply(f"PR #{pr} נדחה; Issue #{pm['issue']} חסום (BLOCKED)." if res["result"] == "SUCCESS" else f"לא נדחה: {res.get('reason')}", ok=res["result"] == "SUCCESS")

    def _do_owner_change_request(self, cmd: OwnerCommand) -> Reply:
        pr = int(cmd.args.get("pr") or self.store.context(cmd.chat_id).get("current_pr") or 0)
        rec = self._rec_for_pr(pr) if pr else None
        if rec is None:
            return Reply("איזה PR לשנות? ציין מספר.", ok=False)
        feedback = (cmd.args.get("feedback") or cmd.raw_text or "").strip()
        if not feedback:
            return Reply("מה צריך להשתנות? תאר ואעביר ל-worker.", ok=False)
        res = self.orch.owner_change_request(rec.issue_id, source="telegram", owner_id=cmd.user_id, command_id=cmd.command_id, feedback=feedback)
        self._audit(cmd, res["result"], {"pr": pr, "issue": rec.issue_id, "feedback": feedback[:300], "reason": res.get("reason")})
        if res["result"] != "SUCCESS":
            return Reply(f"אי אפשר לבקש שינויים: {res.get('reason')}", ok=False)
        return Reply(f"✏️ בקשת השינוי נרשמה ל-PR #{pr}; ניסיון תיקון יטפל בה. תקבל התראת READY חדשה ל-SHA החדש.")

    # -- control --------------------------------------------------------------------------
    def _do_pause_scheduler(self, cmd: OwnerCommand) -> Reply:
        self.orch.set_paused(True, source=cmd.source, who=str(cmd.user_id), reason=cmd.raw_text[:200])
        self._audit(cmd, "SUCCESS")
        return Reply("⏸ הושהה: אין claims חדשים, אין workers חדשים, אין לולאות תיקון חדשות. workers שרצים מסיימים את השלב הנוכחי. אמור 'תמשיך' או /resume להמשך.")

    def _do_resume_scheduler(self, cmd: OwnerCommand) -> Reply:
        self.orch.set_paused(False, source=cmd.source, who=str(cmd.user_id), reason=cmd.raw_text[:200])
        self._audit(cmd, "SUCCESS")
        return Reply("▶️ ממשיך: הסקדיולר לוקח שוב עבודה חדשה.")

    # -- context for the interpreter ------------------------------------------------------
    def _context(self, chat_id: int) -> ConversationContext:
        from agent_team.status import render_compact
        ctx = self.store.context(chat_id)
        draft = self._current_draft(chat_id)
        ready = [{"issue": r.issue_id, "pr": r.pr_number, "title": r.title, "sha": r.validated_commit or ""} for r in self.store.list((sm.READY_FOR_OWNER,))]
        issues = []
        try:
            for i in self.github.list_issues(state="open")[:15]:
                issues.append({"number": i["number"], "title": i.get("title", ""), "labels": [l["name"] for l in i.get("labels", [])], "state": i.get("state")})
        except Exception:  # noqa: BLE001
            pass
        return ConversationContext(chat_id=chat_id, current_draft=draft, current_pr=ctx.get("current_pr"), ready_prs=ready,
                                   status_text=render_compact(self.config, self.store, self.orch.resources, probe_machine=False, now=self.clock()),
                                   recent_issues=issues, paused=self.orch.paused())

    def interpret_and_execute(self, text: str, *, user_id: int, chat_id: int, command_id: str, from_voice: bool = False,
                              on_slow: object = None) -> Reply:
        """Text/voice path: quick slash parse, else the interpreter; then the typed command.
        `on_slow(action)` is called before a slow (drafting) phase so the service can acknowledge."""
        cmd = C.quick_parse(text)
        if cmd is None or cmd.action == C.UNKNOWN and not text.startswith("/"):
            if not self.is_owner(user_id):
                return Reply.deny("⛔ לא מורשה. הבוט הזה עונה רק לבעלים המצומד (agentctl remote pair).")
            ctx = self._context(chat_id)
            classify = getattr(self.interpreter, "classify", None)
            deepen = getattr(self.interpreter, "deepen", None)
            if callable(classify) and callable(deepen):
                intent = classify(text, ctx)
                from agent_team.remote.interpreter import DEEP_ACTIONS
                if intent.action in DEEP_ACTIONS and not (intent.args.get("body") or "").strip():
                    if callable(on_slow):
                        on_slow(intent.action)
                    intent = deepen(text, ctx, intent)
            else:
                intent = self.interpreter.interpret(text, ctx)
            cmd = OwnerCommand(action=intent.action, args=dict(intent.args), raw_text=text)
            if intent.action == C.UNKNOWN or intent.action == C.HELP:
                cmd.args["reply"] = intent.reply
            reply_prefix = intent.reply.strip()
        else:
            reply_prefix = ""
        cmd.command_id, cmd.user_id, cmd.chat_id, cmd.from_voice = command_id, user_id, chat_id, from_voice
        if cmd.action in C.BUTTON_ONLY:
            return Reply(f"{cmd.action} דורש אישור בכפתור.", ok=False)
        reply = self.execute(cmd)
        if reply_prefix and cmd.action not in (C.UNKNOWN, C.HELP, C.ASK, C.PR_QUESTION) and reply_prefix not in reply.text:
            reply.text = f"{reply_prefix}\n\n{reply.text}"
        return reply
