"""The typed owner command vocabulary.

Natural language (any language) is interpreted into one of these actions with typed arguments;
buttons carry them directly. The gateway executes only these — there is deliberately no BASH,
GIT, GH, SQL or filesystem command: Telegram is an owner interface, never a remote shell.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

# read-only
GET_STATUS = "GET_STATUS"
GET_AGENTS = "GET_AGENTS"
LIST_ISSUES = "LIST_ISSUES"
GET_ISSUE = "GET_ISSUE"
LIST_READY_PRS = "LIST_READY_PRS"
GET_PR_DETAILS = "GET_PR_DETAILS"
PR_QUESTION = "PR_QUESTION"
ASK = "ASK"
HELP = "HELP"
# issue backlog (owner authority)
CREATE_ISSUE_DRAFT = "CREATE_ISSUE_DRAFT"
UPDATE_ISSUE_DRAFT = "UPDATE_ISSUE_DRAFT"
SHOW_DRAFT = "SHOW_DRAFT"
CANCEL_DRAFT = "CANCEL_DRAFT"
CREATE_ISSUE = "CREATE_ISSUE"          # args: queue (bool)
APPROVE_ISSUE = "APPROVE_ISSUE"        # args: number, queue (bool)
QUEUE_ISSUE = "QUEUE_ISSUE"            # args: number (approve + queue)
UNQUEUE_ISSUE = "UNQUEUE_ISSUE"        # args: number ("don't work on it yet")
# PR decisions
MERGE_PR = "MERGE_PR"                  # -> confirmation
CONFIRM_MERGE = "CONFIRM_MERGE"        # button only
CANCEL_MERGE = "CANCEL_MERGE"
REJECT_PR = "REJECT_PR"                # -> confirmation
CONFIRM_REJECT = "CONFIRM_REJECT"      # button only
OWNER_CHANGE_REQUEST = "OWNER_CHANGE_REQUEST"
# control
PAUSE_SCHEDULER = "PAUSE_SCHEDULER"
RESUME_SCHEDULER = "RESUME_SCHEDULER"
PAIR = "PAIR"
UNKNOWN = "UNKNOWN"

ACTIONS = (GET_STATUS, GET_AGENTS, LIST_ISSUES, GET_ISSUE, LIST_READY_PRS, GET_PR_DETAILS, PR_QUESTION, ASK, HELP,
           CREATE_ISSUE_DRAFT, UPDATE_ISSUE_DRAFT, SHOW_DRAFT, CANCEL_DRAFT, CREATE_ISSUE, APPROVE_ISSUE, QUEUE_ISSUE,
           UNQUEUE_ISSUE, MERGE_PR, CONFIRM_MERGE, CANCEL_MERGE, REJECT_PR, CONFIRM_REJECT, OWNER_CHANGE_REQUEST,
           PAUSE_SCHEDULER, RESUME_SCHEDULER, PAIR, UNKNOWN)
#: Actions that change GitHub / orchestrator state — always audited, always replay-protected.
MUTATING = (CREATE_ISSUE, APPROVE_ISSUE, QUEUE_ISSUE, UNQUEUE_ISSUE, CONFIRM_MERGE, CONFIRM_REJECT, OWNER_CHANGE_REQUEST,
            PAUSE_SCHEDULER, RESUME_SCHEDULER, PAIR)
#: Actions that may only come from a pressed button (never from text, never from voice).
BUTTON_ONLY = (CONFIRM_MERGE, CONFIRM_REJECT)
#: Actions the LLM interpreter may produce (everything except the button-only confirmations and pairing).
INTERPRETABLE = tuple(a for a in ACTIONS if a not in BUTTON_ONLY + (PAIR,))


@dataclass
class OwnerCommand:
    action: str
    args: dict = field(default_factory=dict)
    command_id: str = ""
    source: str = "telegram"
    user_id: int | None = None
    chat_id: int | None = None
    from_callback: bool = False
    from_voice: bool = False
    raw_text: str = ""

    @property
    def entity(self) -> str | None:
        if "number" in self.args:
            return f"issue:{self.args['number']}"
        if "pr" in self.args:
            return f"pr:{self.args['pr']}"
        if "draft_id" in self.args:
            return f"draft:{self.args['draft_id']}"
        return None


@dataclass
class Reply:
    text: str
    buttons: list[list[dict]] = field(default_factory=list)
    ok: bool = True

    @staticmethod
    def deny(text: str = "Not authorized.") -> "Reply":
        return Reply(text, ok=False)


# -- callback buttons -------------------------------------------------------------------------
# data = "v1|ACTION|entity|ref|nonce"  (Telegram limit 64 bytes). `ref` is a SHA prefix or a draft
# id so a button is bound to the exact state it was rendered for and goes stale with it.

def button(text: str, action: str, entity: str | int = "", ref: str = "", nonce: str = "") -> dict:
    data = "|".join(["v1", action, str(entity), ref[:12], nonce[:10]])
    return {"text": text, "data": data[:64]}


def parse_callback(data: str) -> OwnerCommand | None:
    parts = (data or "").split("|")
    if len(parts) != 5 or parts[0] != "v1" or parts[1] not in ACTIONS:
        return None
    _, action, entity, ref, nonce = parts
    args: dict = {}
    if entity.isdigit():
        if action in (MERGE_PR, CONFIRM_MERGE, CANCEL_MERGE, REJECT_PR, CONFIRM_REJECT, GET_PR_DETAILS):
            args["pr"] = int(entity)
        elif action in (APPROVE_ISSUE, QUEUE_ISSUE, UNQUEUE_ISSUE, GET_ISSUE):
            args["number"] = int(entity)
    elif entity:
        args["draft_id"] = entity
    if ref:
        args["ref"] = ref
    if nonce:
        args["nonce"] = nonce
    if action == CREATE_ISSUE:
        args["queue"] = ref == "queue"
    return OwnerCommand(action=action, args=args, from_callback=True)


def new_nonce() -> str:
    return secrets.token_hex(4)


# -- deterministic quick parser (no LLM) -----------------------------------------------------
_NUM = r"#?\s*(\d+)"
_QUICK: list[tuple[re.Pattern, str, str | None]] = [
    (re.compile(r"^/?pair(?:@\w+)?[\s:]+(\d{4,8})\s*$", re.I), PAIR, "code"),   # /pair 123456, /pair@bot 123456, pair: 123456
    (re.compile(r"^(\d{6})$"), PAIR, "code"),                                      # the bare six-digit code
    (re.compile(r"^/(status|start)\s*$"), GET_STATUS, None),
    (re.compile(r"^/agents\s*$"), GET_AGENTS, None),
    (re.compile(r"^/help\s*$"), HELP, None),
    (re.compile(r"^/pause\s*$"), PAUSE_SCHEDULER, None),
    (re.compile(r"^/resume\s*$"), RESUME_SCHEDULER, None),
    (re.compile(r"^/ready\s*$"), LIST_READY_PRS, None),
    (re.compile(r"^/issues\s*$"), LIST_ISSUES, None),
    (re.compile(r"^/draft\s*$"), SHOW_DRAFT, None),
    (re.compile(r"^/cancel\s*$"), CANCEL_DRAFT, None),
    (re.compile(rf"^/issue\s+{_NUM}\s*$"), GET_ISSUE, "number"),
    (re.compile(rf"^/pr\s+{_NUM}\s*$"), GET_PR_DETAILS, "pr"),
    (re.compile(rf"^/merge\s+{_NUM}\s*$"), MERGE_PR, "pr"),
    (re.compile(rf"^/reject\s+{_NUM}\s*$"), REJECT_PR, "pr"),
    (re.compile(rf"^/approve\s+{_NUM}\s*$"), APPROVE_ISSUE, "number"),
    (re.compile(rf"^/queue\s+{_NUM}\s*$"), QUEUE_ISSUE, "number"),
    (re.compile(rf"^/unqueue\s+{_NUM}\s*$"), UNQUEUE_ISSUE, "number"),
]


def quick_parse(text: str) -> OwnerCommand | None:
    """Slash commands (and the pairing code forms). Everything else goes to the interpreter."""
    t = (text or "").strip()
    t = re.sub(r"^(/\w+)@\w+", r"\1", t)   # "/status@buildsmart_teamlead_bot" -> "/status"
    if not t.startswith("/") and not re.match(r"^(pair\b|\d{6}$)", t, re.I):
        return None
    for pat, action, argname in _QUICK:
        m = pat.match(t)
        if m:
            args = {}
            if argname:
                args[argname] = int(m.group(1)) if argname != "code" else m.group(1)
            if action == QUEUE_ISSUE:
                args["queue"] = True
            if action == APPROVE_ISSUE:
                args["queue"] = False
            return OwnerCommand(action=action, args=args, raw_text=t)
    return OwnerCommand(action=UNKNOWN, args={"text": t}, raw_text=t)


HELP_TEXT = """BuildSmart Team Lead — owner commands

Talk to me naturally (Hebrew or English), or use:
/status  /agents  /ready  /issues  /issue N  /pr N
/merge N  /reject N  /approve N  /queue N  /unqueue N
/pause  /resume  /draft  /cancel  /help

Examples:
"מה הסוכנים עושים עכשיו?"  "תראה לי את כל ה-PRs שמחכים לי"
"תפתח issue חדש: …"  "תאשר את issue 42 ותתחיל לעבוד"
"מה הבעיה ב-PR 57?"  "תבצע merge ל-PR 57"  "תעצור"  "תמשיך"

Rules: I never merge without your CONFIRM MERGE button; I never add owner:approved by myself;
voice can draft and ask, but never confirm a merge."""
