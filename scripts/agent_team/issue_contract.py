"""The GitHub Issue is the authoritative work contract. This module parses and validates it.

The body format is exactly what the Issue Form (`.github/ISSUE_TEMPLATE/agent-task.yml`) renders:
`### <Section label>` headings followed by the field value. The Team Lead's `agentctl issue create`
renders the same format (`render_body`), so a form-authored Issue and a CLI-authored Issue parse
identically, and CI (`ci/contract_check.py`) re-parses the live Issue rather than trusting anything
committed in the PR.

A contract that does not validate is never executable: the orchestrator refuses to claim it and
`agentctl issue queue` refuses to label it `agent:queued`.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace

from agent_team.config import DOMAINS, RESOURCE_CLASSES, RISKS

# Section labels exactly as the Issue Form renders them (`### <label>`).
SECTION_GOAL = "Goal"
SECTION_CURRENT = "Current behavior"
SECTION_REQUIRED = "Required behavior"
SECTION_AC = "Acceptance Criteria"
SECTION_OUT_OF_SCOPE = "Out of scope"
SECTION_DOMAINS = "Affected domains"
SECTION_RISK = "Risk"
SECTION_RESOURCE = "Resource class"
SECTION_DEPENDENCIES = "Dependencies"
SECTION_LOCKS = "Required locks"
SECTION_VERIFICATION = "Verification plan"
SECTION_BUDGET = "Regression budget"
SECTION_DOCS = "Expected documentation changes"
SECTION_AUTHORIZATION = "Authorization"     # optional: a child Issue's inherited authorization
SECTION_KNOWLEDGE = "Knowledge check"        # optional: what the Wiki/RAG already cover

REQUIRED_SECTIONS = (
    SECTION_GOAL, SECTION_CURRENT, SECTION_REQUIRED, SECTION_AC, SECTION_OUT_OF_SCOPE,
    SECTION_DOMAINS, SECTION_RISK, SECTION_RESOURCE, SECTION_DEPENDENCIES, SECTION_LOCKS,
    SECTION_VERIFICATION, SECTION_BUDGET, SECTION_DOCS,
)

NO_RESPONSE = "_No response_"

# Verification TYPES (what kind of evidence a target is) and the concrete KINDS that produce it.
#   TEST            an executed test:          pytest:<nodeid> | vitest:<file> | cmd:scripts/<script>
#   REGRESSION      the corpus budget gate:    regression:corpus
#   STATIC          a deterministic static check: static:<backend-compile|backend-import|frontend-lint|frontend-types>
#   ARTIFACT        a deliverable exists/contains: file:<path> | grep:<path>:<regex>
#   SEMANTIC_REVIEW an independent-reviewer judgement: review:<what the reviewer must confirm>
# A target may carry its type explicitly (`TEST:pytest:...`) or leave it to be inferred from the kind.
# SEMANTIC_REVIEW is never sufficient on its own for a behavior-changing Issue.
TEST, REGRESSION, STATIC, ARTIFACT, SEMANTIC_REVIEW = "TEST", "REGRESSION", "STATIC", "ARTIFACT", "SEMANTIC_REVIEW"
VERIFICATION_TYPES = (TEST, REGRESSION, STATIC, ARTIFACT, SEMANTIC_REVIEW)
DETERMINISTIC_TYPES = (TEST, REGRESSION, STATIC, ARTIFACT)
KIND_TYPES = {"pytest": TEST, "vitest": TEST, "cmd": TEST, "regression": REGRESSION, "static": STATIC,
              "file": ARTIFACT, "grep": ARTIFACT, "review": SEMANTIC_REVIEW}
VERIFICATION_KINDS = tuple(KIND_TYPES)
STATIC_TARGETS = ("backend-compile", "backend-import", "frontend-lint", "frontend-types")
DEFAULT_BEHAVIOR_DOMAINS = ("backend", "geometry", "validator", "frontend", "ai")

BUDGET_KEYS = ("LOST", "GAINED", "crashes", "status_changes", "refusal_code_changes", "primary_signature_changes")
BUDGET_DEFAULTS = {
    "LOST": "0", "GAINED": "allowed", "crashes": "0", "status_changes": "0",
    "refusal_code_changes": "0", "primary_signature_changes": "none",
}

_AC_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)])?\s*\**(AC-\d+)\**\s*[:\-–—]\s*(.+?)\s*$")
_VERIFY_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)])?\s*\**(AC-\d+)\**\s*(?:->|→|=>|:)\s*(.+?)\s*$")
_ISSUE_REF = re.compile(r"#?(\d+)")
_LOCK_ITEM = re.compile(r"^\s*([a-z0-9][a-z0-9\-]*)\s*(?:\(\s*(exclusive|shared)\s*\))?\s*$", re.I)
_BUDGET_LINE = re.compile(r"^\s*[-*]?\s*([A-Za-z_]+)\s*[:=]\s*(.+?)\s*$")
_TAGGED = re.compile(r"^tagged:\s*([a-z_]+)\s*(==|=|!=|>=|<=|>|<)\s*([A-Za-z0-9_.\-]+)$")
_SECTION = re.compile(r"^###\s+(.+?)\s*$", re.M)
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


class ContractError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class AcceptanceCriterion:
    id: str
    text: str


@dataclass(frozen=True)
class LockRequirement:
    name: str
    mode: str  # exclusive | shared


@dataclass(frozen=True)
class VerificationTarget:
    ac: str
    kind: str      # one of VERIFICATION_KINDS
    target: str    # nodeid / path / "corpus" / "path:regex" / script / static check / review question
    vtype: str = ""  # one of VERIFICATION_TYPES (inferred from kind when not given explicitly)

    def __post_init__(self):
        if not self.vtype:
            object.__setattr__(self, "vtype", KIND_TYPES[self.kind])

    @property
    def spec(self) -> str:
        return f"{self.kind}:{self.target}"

    @property
    def deterministic(self) -> bool:
        return self.vtype in DETERMINISTIC_TYPES


@dataclass(frozen=True)
class BudgetRule:
    key: str
    kind: str            # max | allowed | none | tagged
    limit: int = 0
    tag_field: str = ""
    tag_op: str = ""
    tag_value: str = ""

    def spec(self) -> str:
        if self.kind == "max":
            return str(self.limit)
        if self.kind == "tagged":
            return f"tagged:{self.tag_field}{self.tag_op}{self.tag_value}"
        return self.kind


AUTH_SOURCES = ("owner", "inherited")
_AUTH_KEYS = ("source", "root_issue", "parent_issue", "derived_by", "scope_inherited")
_KV_RE = re.compile(r"^\s*[-*]?\s*`?([a-z_]+)`?\s*[:=]\s*(.+?)\s*$")


@dataclass(frozen=True)
class Authorization:
    """Who authorized execution. A ROOT Issue is authorized by the owner's label; a child Issue is
    authorized by inheritance from its ROOT (`source: inherited`, `root_issue: #N`)."""
    source: str = "owner"
    root_issue: int | None = None
    parent_issue: int | None = None
    derived_by: str = ""
    scope_inherited: bool = False

    @property
    def inherited(self) -> bool:
        return self.source == "inherited"

    def render(self) -> str:
        lines = [f"source: {self.source}"]
        if self.root_issue:
            lines.append(f"root_issue: #{self.root_issue}")
        if self.parent_issue:
            lines.append(f"parent_issue: #{self.parent_issue}")
        if self.derived_by:
            lines.append(f"derived_by: {self.derived_by}")
        lines.append(f"scope_inherited: {'true' if self.scope_inherited else 'false'}")
        return "\n".join(lines)


def parse_authorization(text: str, problems: list[str] | None = None) -> Authorization:
    """`### Authorization` body -> Authorization. Problems are appended (or raised when no list is given)."""
    own: list[str] = [] if problems is None else problems
    values: dict[str, str] = {}
    for line in (text or "").splitlines():
        m = _KV_RE.match(line)
        if m and m.group(1) in _AUTH_KEYS:
            values[m.group(1)] = m.group(2).strip().strip("`")
    source = values.get("source", "owner").lower()
    if source not in AUTH_SOURCES:
        own.append(f"Authorization: source must be one of {', '.join(AUTH_SOURCES)}")
        source = "owner"

    def num(key: str) -> int | None:
        v = values.get(key)
        if v is None:
            return None
        m = re.fullmatch(r"#?(\d+)", v)
        if not m:
            own.append(f"Authorization: {key} must be an Issue number like #120")
            return None
        return int(m.group(1))

    root = num("root_issue")
    parent = num("parent_issue")
    inherited_flag = values.get("scope_inherited", "").lower() in ("true", "yes", "1")
    if source == "inherited":
        if root is None:
            own.append("Authorization: an inherited authorization needs root_issue: #N")
        if not inherited_flag:
            own.append("Authorization: an inherited authorization must state scope_inherited: true")
    if problems is None and own:
        raise ContractError(own)
    return Authorization(source=source, root_issue=root, parent_issue=parent or root,
                         derived_by=values.get("derived_by", ""), scope_inherited=inherited_flag)


def child_scope_problems(child: "IssueContract", root: "IssueContract", *, effective=None) -> list[str]:
    """Deterministic 'the child stays inside its ROOT' check. Decomposition may narrow a ROOT, never
    widen it: domains, locks and the regression budget are bounded by the ROOT's own contract.
    `effective(contract) -> locks` lets the caller compare the locks implied by domains too."""
    problems: list[str] = []
    extra_domains = [d for d in child.domains if d not in root.domains]
    if extra_domains:
        problems.append(f"domains outside the ROOT #{root.number}: {', '.join(extra_domains)} (ROOT has {', '.join(root.domains)})")
    child_locks = effective(child) if effective else child.locks
    root_locks = {l.name: l.mode for l in (effective(root) if effective else root.locks)}
    for l in child_locks:
        if l.name not in root_locks:
            problems.append(f"lock {l.name} not declared by the ROOT #{root.number}")
        elif l.mode == "exclusive" and root_locks[l.name] != "exclusive":
            problems.append(f"lock {l.name} is exclusive in the child but {root_locks[l.name]} in the ROOT #{root.number}")
    for key in ("LOST", "crashes", "status_changes", "refusal_code_changes", "primary_signature_changes"):
        c, r = child.budget_rule(key), root.budget_rule(key)
        if _budget_wider(c, r):
            problems.append(f"regression budget {key}: child allows {c.spec()} but the ROOT #{root.number} allows {r.spec()}")
    auth = child.authorization
    if not auth.inherited or auth.root_issue != root.number:
        problems.append(f"Authorization section must say source: inherited / root_issue: #{root.number}")
    return problems


def _budget_wider(child: "BudgetRule", root: "BudgetRule") -> bool:
    if root.kind == "allowed":
        return False
    if child.kind == "allowed":
        return True
    if root.kind == "none":
        return child.kind != "none"
    if root.kind == "max":
        if child.kind == "none":
            return False
        if child.kind == "max":
            return child.limit > root.limit
        return True          # tagged predicates are not comparable to a number: treat as wider
    return child.kind != "tagged" and child.kind != "none"


@dataclass(frozen=True)
class IssueContract:
    number: int
    title: str
    goal: str
    current_behavior: str
    required_behavior: str
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    out_of_scope: str
    domains: tuple[str, ...]
    risk: str
    resource_class: str
    dependencies: tuple[int, ...]
    locks: tuple[LockRequirement, ...]
    verification: tuple[VerificationTarget, ...]
    budget: tuple[BudgetRule, ...]
    documentation_changes: str
    extra_sections: dict[str, str] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return slugify(self.title)

    @property
    def ac_ids(self) -> tuple[str, ...]:
        return tuple(ac.id for ac in self.acceptance_criteria)

    def targets_for(self, ac_id: str) -> tuple[VerificationTarget, ...]:
        return tuple(t for t in self.verification if t.ac == ac_id)

    def budget_rule(self, key: str) -> BudgetRule:
        for r in self.budget:
            if r.key == key:
                return r
        return parse_budget_value(key, BUDGET_DEFAULTS[key])

    @property
    def lost_allowance(self) -> bool:
        """True when the budget intentionally allows some LOST contexts (a number > 0 or a tagged predicate)."""
        r = self.budget_rule("LOST")
        return r.kind == "tagged" or (r.kind == "max" and r.limit > 0)

    @property
    def semantic_review_acs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(t.ac for t in self.verification if t.vtype == SEMANTIC_REVIEW))

    def is_behavior_changing(self, behavior_domains: tuple[str, ...] = DEFAULT_BEHAVIOR_DOMAINS) -> bool:
        return any(d in behavior_domains for d in self.domains)

    def needs_regression(self, regression_domains: tuple[str, ...]) -> bool:
        return any(t.kind == "regression" for t in self.verification) or any(
            d in regression_domains for d in self.domains
        )

    @property
    def authorization(self) -> Authorization:
        text = self.extra_sections.get(SECTION_AUTHORIZATION)
        if not text:
            return Authorization()
        return parse_authorization(text, problems=[])

    @property
    def root_issue(self) -> int:
        """The ROOT this Issue executes under: its own number, or the inherited root."""
        a = self.authorization
        return a.root_issue if a.inherited and a.root_issue else self.number

    def with_authorization(self, auth: Authorization) -> "IssueContract":
        extra = dict(self.extra_sections)
        extra[SECTION_AUTHORIZATION] = auth.render()
        return replace(self, extra_sections=extra)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["slug"] = self.slug
        return d


def slugify(title: str, max_len: int = 40) -> str:
    t = title.lower()
    t = re.sub(r"^\[agent\]\s*", "", t)
    t = re.sub(r"^#\d+\s*", "", t)
    t = _SLUG_STRIP.sub("-", t).strip("-")
    if len(t) > max_len:
        t = t[:max_len].rstrip("-")
    return t or "task"


_AGENT_PREFIX_RE = re.compile(r"^\[agent\]\s*")
_TITLE_NUMBER_RE = re.compile(r"^#\d+\s*")


def numbered_title(number: int, title: str) -> str:
    """`[agent] <rest>` (with any existing `[agent]`/`#N` prefix stripped first) -> `[agent] #N <rest>`.
    Idempotent: applying it again to its own output is a no-op."""
    t = _AGENT_PREFIX_RE.sub("", title.strip(), count=1)
    t = _TITLE_NUMBER_RE.sub("", t, count=1)
    return f"[agent] #{number} {t}".rstrip()


def strip_title_number(title: str) -> str:
    """Display inverse of `numbered_title`: drop a `#N` that duplicates a number already shown
    elsewhere (e.g. the `#{issue_id}` a status/list line prepends itself), leaving any `[agent] `
    prefix in place."""
    m = _AGENT_PREFIX_RE.match(title)
    prefix, rest = (title[:m.end()], title[m.end():]) if m else ("", title)
    rest = _TITLE_NUMBER_RE.sub("", rest, count=1)
    return (prefix + rest).strip()


# --------------------------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------------------------

def split_sections(body: str) -> dict[str, str]:
    """`### Label\\n\\nvalue` blocks -> {label: value}. Text before the first heading is ignored."""
    body = body.replace("\r\n", "\n")
    matches = list(_SECTION.finditer(body))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        value = body[m.end():end].strip()
        out[m.group(1).strip()] = value
    return out


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    v = value.strip()
    return "" if v == NO_RESPONSE else v


def _parse_ac(text: str, problems: list[str]) -> tuple[AcceptanceCriterion, ...]:
    acs: list[AcceptanceCriterion] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _AC_LINE.match(line)
        if not m:
            problems.append(f"Acceptance Criteria line is not 'AC-n: text': {line.strip()!r}")
            continue
        ac_id, ac_text = m.group(1), m.group(2)
        if ac_id in seen:
            problems.append(f"duplicate acceptance criterion id {ac_id}")
        seen.add(ac_id)
        if len(ac_text) < 8:
            problems.append(f"{ac_id} is too short to be verifiable: {ac_text!r}")
        acs.append(AcceptanceCriterion(ac_id, ac_text))
    if not acs:
        problems.append("no Acceptance Criteria found (need at least AC-1)")
    return tuple(acs)


def _parse_domains(text: str, problems: list[str]) -> tuple[str, ...]:
    if not text:
        problems.append("Affected domains is empty")
        return ()
    items = [d.strip().lower() for d in re.split(r"[,\n]", text) if d.strip()]
    out: list[str] = []
    for d in items:
        d = d.lstrip("-* ").strip()
        d = d.removeprefix("domain:")
        if d not in DOMAINS:
            problems.append(f"unknown domain {d!r} (allowed: {', '.join(DOMAINS)})")
        elif d not in out:
            out.append(d)
    return tuple(out)


def _parse_choice(text: str, allowed: tuple[str, ...], section: str, problems: list[str]) -> str:
    v = text.strip().upper()
    if v not in allowed:
        problems.append(f"{section} must be one of {', '.join(allowed)}, got {text!r}")
        return ""
    return v


def _parse_dependencies(text: str, number: int, problems: list[str]) -> tuple[int, ...]:
    t = text.strip().lower()
    if not t or t in ("none", "-", "n/a", "no"):
        return ()
    deps: list[int] = []
    for token in re.split(r"[,\s]+", text.strip()):
        if not token:
            continue
        m = _ISSUE_REF.fullmatch(token.strip())
        if not m:
            problems.append(f"Dependencies entry is not an issue reference: {token!r}")
            continue
        n = int(m.group(1))
        if n == number:
            problems.append("an Issue cannot depend on itself")
        elif n not in deps:
            deps.append(n)
    return tuple(deps)


def _parse_locks(text: str, known: tuple[str, ...] | None, problems: list[str]) -> tuple[LockRequirement, ...]:
    t = text.strip().lower()
    if not t or t in ("none", "-", "n/a", "default", "defaults"):
        return ()
    out: list[LockRequirement] = []
    for item in re.split(r"[,\n]", text):
        if not item.strip():
            continue
        m = _LOCK_ITEM.match(item.strip().lstrip("-* "))
        if not m:
            problems.append(f"Required locks entry is not '<name> (exclusive|shared)': {item.strip()!r}")
            continue
        name = m.group(1).lower()
        mode = (m.group(2) or "exclusive").lower()
        if known is not None and name not in known:
            problems.append(f"unknown lock {name!r} (known: {', '.join(known)})")
        if any(l.name == name for l in out):
            problems.append(f"lock {name!r} listed twice")
        out.append(LockRequirement(name, mode))
    return tuple(out)


def parse_verification_target(ac: str, spec: str) -> VerificationTarget | str:
    """Returns a target, or an error string. Accepts `[TYPE:]kind:target`."""
    spec = spec.strip().strip("`")
    if ":" not in spec:
        return f"{ac} verification target must be '[TYPE:]<kind>:<target>', got {spec!r}"
    head, rest = spec.split(":", 1)
    explicit_type = ""
    if head.strip() in VERIFICATION_TYPES:          # types are uppercase, kinds lowercase
        explicit_type = head.strip()
        if ":" not in rest:
            return f"{ac} verification target must be '{explicit_type}:<kind>:<target>', got {spec!r}"
        head, rest = rest.split(":", 1)
    kind, target = head.strip().lower(), rest.strip()
    if kind not in VERIFICATION_KINDS:
        return f"{ac} verification kind {kind!r} is not one of {', '.join(VERIFICATION_KINDS)}"
    if explicit_type and KIND_TYPES[kind] != explicit_type:
        return f"{ac} kind {kind!r} produces {KIND_TYPES[kind]} evidence, not {explicit_type}"
    if not target:
        return f"{ac} verification target for {kind} is empty"
    if kind == "regression" and target != "corpus":
        return f"{ac} regression target must be 'regression:corpus', got {target!r}"
    if kind == "grep" and ":" not in target:
        return f"{ac} grep target must be 'grep:<path>:<regex>', got {target!r}"
    if kind == "cmd" and not target.startswith("scripts/"):
        return f"{ac} cmd target must be a script under scripts/, got {target!r}"
    if kind == "static" and target not in STATIC_TARGETS:
        return f"{ac} static target must be one of {', '.join(STATIC_TARGETS)}, got {target!r}"
    if kind == "review" and len(target) < 12:
        return f"{ac} review target must say what the reviewer has to confirm, got {target!r}"
    if kind in ("pytest", "vitest", "file") and (".." in target or target.startswith("/")):
        return f"{ac} {kind} target must be a repo-relative path, got {target!r}"
    return VerificationTarget(ac=ac, kind=kind, target=target, vtype=KIND_TYPES[kind])


def _parse_verification(text: str, ac_ids: tuple[str, ...], problems: list[str], *,
                        behavior_changing: bool) -> tuple[VerificationTarget, ...]:
    out: list[VerificationTarget] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _VERIFY_LINE.match(line)
        if not m:
            problems.append(f"Verification plan line is not 'AC-n -> kind:target': {line.strip()!r}")
            continue
        ac = m.group(1)
        if ac not in ac_ids:
            problems.append(f"Verification plan references unknown criterion {ac}")
        for spec in re.split(r"\s*[;|]\s*", m.group(2)):
            if not spec.strip():
                continue
            res = parse_verification_target(ac, spec)
            if isinstance(res, str):
                problems.append(res)
            else:
                out.append(res)
    covered = {t.ac for t in out}
    deterministic = {t.ac for t in out if t.deterministic}
    for ac in ac_ids:
        if ac not in covered:
            problems.append(f"{ac} has no verification target — every criterion needs evidence")
        elif ac not in deterministic and behavior_changing:
            problems.append(f"{ac} is proven only by SEMANTIC_REVIEW — a behavior-changing Issue needs "
                            f"TEST/REGRESSION/STATIC/ARTIFACT evidence for every criterion")
    if out and not deterministic:
        problems.append("no deterministic verification target at all — at least one TEST/REGRESSION/STATIC/ARTIFACT target is required")
    return tuple(out)


def parse_budget_value(key: str, value: str) -> BudgetRule:
    v = value.strip().strip("`").lower()
    if v in ("allowed", "any", "unbounded"):
        return BudgetRule(key, "allowed")
    if v in ("none", "0", "no", "forbidden"):
        return BudgetRule(key, "max", 0) if v == "0" else BudgetRule(key, "none")
    if v.isdigit():
        return BudgetRule(key, "max", int(v))
    m = _TAGGED.match(v)
    if m:
        op = m.group(2)
        op = "==" if op == "=" else op
        return BudgetRule(key, "tagged", 0, m.group(1), op, m.group(3))
    raise ValueError(f"Regression budget {key}: value {value!r} is not a number, 'allowed', 'none' or 'tagged:<field><op><value>'")


def _parse_budget(text: str, problems: list[str], *, risk: str) -> tuple[BudgetRule, ...]:
    rules: dict[str, BudgetRule] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        m = _BUDGET_LINE.match(line)
        if not m:
            problems.append(f"Regression budget line is not 'key: value': {line.strip()!r}")
            continue
        key = m.group(1)
        canonical = {k.lower(): k for k in BUDGET_KEYS}.get(key.lower())
        if canonical is None:
            problems.append(f"unknown Regression budget key {key!r} (allowed: {', '.join(BUDGET_KEYS)})")
            continue
        try:
            rules[canonical] = parse_budget_value(canonical, m.group(2))
        except ValueError as exc:
            problems.append(str(exc))
    for key in BUDGET_KEYS:
        rules.setdefault(key, parse_budget_value(key, BUDGET_DEFAULTS[key]))
    lost = rules["LOST"]
    if lost.kind == "allowed":
        problems.append("Regression budget LOST: 'allowed' is never accepted — name the intentionally lost contexts "
                        "with 'tagged:<field><op><value>' or an explicit number (default and normal value: 0)")
    elif (lost.kind == "tagged" or (lost.kind == "max" and lost.limit > 0)) and risk == "LOW":
        problems.append("a non-zero LOST allowance requires Risk MEDIUM or HIGH (and Team Lead approval before merge)")
    return tuple(rules[k] for k in BUDGET_KEYS)


def parse_contract(number: int, title: str, body: str, *, known_locks: tuple[str, ...] | None = None,
                   behavior_domains: tuple[str, ...] = DEFAULT_BEHAVIOR_DOMAINS) -> IssueContract:
    """Parse + validate. Raises ContractError listing every problem found (not just the first)."""
    problems: list[str] = []
    sections = split_sections(body or "")
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            problems.append(f"missing section '### {name}'")
    if problems:
        raise ContractError(problems)

    values = {k: _clean(v) for k, v in sections.items()}
    for name in (SECTION_GOAL, SECTION_CURRENT, SECTION_REQUIRED, SECTION_OUT_OF_SCOPE, SECTION_DOCS):
        if not values[name]:
            problems.append(f"section '{name}' is empty")

    acs = _parse_ac(values[SECTION_AC], problems)
    domains = _parse_domains(values[SECTION_DOMAINS], problems)
    risk = _parse_choice(values[SECTION_RISK], RISKS, SECTION_RISK, problems)
    resource = _parse_choice(values[SECTION_RESOURCE], RESOURCE_CLASSES, SECTION_RESOURCE, problems)
    deps = _parse_dependencies(values[SECTION_DEPENDENCIES], number, problems)
    locks = _parse_locks(values[SECTION_LOCKS], known_locks, problems)
    behavior_changing = any(d in behavior_domains for d in domains)
    verification = _parse_verification(values[SECTION_VERIFICATION], tuple(a.id for a in acs), problems,
                                       behavior_changing=behavior_changing)
    budget = _parse_budget(values[SECTION_BUDGET], problems, risk=risk)
    if values.get(SECTION_AUTHORIZATION):
        auth = parse_authorization(values[SECTION_AUTHORIZATION], problems)
        if auth.inherited and auth.root_issue == number:
            problems.append("Authorization: an Issue cannot inherit from itself")

    if problems:
        raise ContractError(problems)

    extra = {k: v for k, v in values.items() if k not in REQUIRED_SECTIONS}
    return IssueContract(
        number=number, title=title.strip(), goal=values[SECTION_GOAL],
        current_behavior=values[SECTION_CURRENT], required_behavior=values[SECTION_REQUIRED],
        acceptance_criteria=acs, out_of_scope=values[SECTION_OUT_OF_SCOPE], domains=domains,
        risk=risk, resource_class=resource, dependencies=deps, locks=locks,
        verification=verification, budget=budget, documentation_changes=values[SECTION_DOCS],
        extra_sections=extra,
    )


# --------------------------------------------------------------------------------------------
# rendering (the inverse — used by `agentctl issue create`)
# --------------------------------------------------------------------------------------------

def render_body(c: IssueContract) -> str:
    def sec(label: str, value: str) -> str:
        return f"### {label}\n\n{value.strip() or NO_RESPONSE}\n"

    ac = "\n".join(f"- {a.id}: {a.text}" for a in c.acceptance_criteria)
    ver = "\n".join(f"- {t.ac} -> {t.vtype}:{t.spec}" for t in c.verification)
    budget = "\n".join(f"{r.key}: {r.spec()}" for r in c.budget)
    deps = ", ".join(f"#{n}" for n in c.dependencies) or "none"
    locks = ", ".join(f"{l.name} ({l.mode})" for l in c.locks) or "none"
    parts = [
        sec(SECTION_GOAL, c.goal), sec(SECTION_CURRENT, c.current_behavior),
        sec(SECTION_REQUIRED, c.required_behavior), sec(SECTION_AC, ac),
        sec(SECTION_OUT_OF_SCOPE, c.out_of_scope), sec(SECTION_DOMAINS, ", ".join(c.domains)),
        sec(SECTION_RISK, c.risk), sec(SECTION_RESOURCE, c.resource_class),
        sec(SECTION_DEPENDENCIES, deps), sec(SECTION_LOCKS, locks),
        sec(SECTION_VERIFICATION, ver), sec(SECTION_BUDGET, budget),
        sec(SECTION_DOCS, c.documentation_changes),
    ]
    for k, v in c.extra_sections.items():
        parts.append(sec(k, v))
    return "\n".join(parts)


# --------------------------------------------------------------------------------------------
# verification manifest (machine-readable; consumed by CI gate 3 and the regression gate)
# --------------------------------------------------------------------------------------------

def verification_manifest(c: IssueContract, *, regression_domains: tuple[str, ...] = ()) -> dict:
    return {
        "issue": c.number,
        "title": c.title,
        "risk": c.risk,
        "resource_class": c.resource_class,
        "domains": list(c.domains),
        "acceptance_criteria": [{"id": a.id, "text": a.text} for a in c.acceptance_criteria],
        "targets": [{"ac": t.ac, "type": t.vtype, "kind": t.kind, "target": t.target} for t in c.verification],
        "semantic_review_acs": list(c.semantic_review_acs),
        "regression_required": c.needs_regression(regression_domains),
        "regression_budget": {r.key: r.spec() for r in c.budget},
        "lost_allowance": c.lost_allowance,
        "locks": [{"name": l.name, "mode": l.mode} for l in c.locks],
        "dependencies": list(c.dependencies),
    }


def manifest_json(c: IssueContract, **kw) -> str:
    return json.dumps(verification_manifest(c, **kw), indent=2, sort_keys=True)
