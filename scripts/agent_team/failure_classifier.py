"""Classify a red CI run (or a rejected review) before anyone tries to repair anything.

Not every red check is an implementation failure. Rules run in priority order over the gate
results, the JSON reports the gates uploaded, failed-job log tails, and the PR's changed files:

    INFRA_FAILURE           runner/actions/network trouble, cancelled or timed-out jobs
    MERGE_CONFLICT          the PR is not mergeable against its base
    ENVIRONMENT_FAILURE     a missing third-party module/package/tool in the isolated environment
    SPEC_MISMATCH           gate 1: the PR/Issue no longer satisfy the contract format
    REGRESSION              gate 4: the corpus changed outside the declared budget
    TEST_FAILURE            a test the PR itself added/changed fails
    IMPLEMENTATION_FAILURE  product behavior does not satisfy existing tests / AC targets
    FLAKY_TEST              the same head SHA went green on re-run with no code change (hint-driven)
    REVIEW_REJECTED         the independent reviewer requested changes (not a CI class; used by
                            the same repair loop so the audit trail is uniform)

The classification is persisted on the Issue record and posted as a milestone comment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

INFRA_FAILURE = "INFRA_FAILURE"
MERGE_CONFLICT = "MERGE_CONFLICT"
ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
SPEC_MISMATCH = "SPEC_MISMATCH"
REGRESSION = "REGRESSION"
TEST_FAILURE = "TEST_FAILURE"
IMPLEMENTATION_FAILURE = "IMPLEMENTATION_FAILURE"
FLAKY_TEST = "FLAKY_TEST"
REVIEW_REJECTED = "REVIEW_REJECTED"

CLASSES = (IMPLEMENTATION_FAILURE, REGRESSION, TEST_FAILURE, ENVIRONMENT_FAILURE, FLAKY_TEST, SPEC_MISMATCH,
           MERGE_CONFLICT, INFRA_FAILURE, REVIEW_REJECTED)

#: Classes a worker may try to repair. The others need the Team Lead (or a re-run) first.
# What the FIXER (fix-and-resubmit worker, owner rule 2026-09-20) takes automatically. SPEC_MISMATCH only when the
# live Issue contract still parses (the orchestrator checks) — then the PR is what must catch up with the contract;
# MERGE_CONFLICT after the orchestrator has started the merge in the worktree (the fixer resolves the markers).
REPAIRABLE = (IMPLEMENTATION_FAILURE, TEST_FAILURE, REGRESSION, REVIEW_REJECTED, SPEC_MISMATCH, MERGE_CONFLICT)

_INFRA_PATTERNS = [
    r"The runner has received a shutdown signal", r"No space left on device", r"lost communication with the server",
    r"exit code 143", r"The hosted runner", r"Unable to resolve action", r"actions/checkout@[^ ]+ failed",
    r"Error: The operation was canceled", r"HttpError: .*rate limit", r"ETIMEDOUT", r"ECONNRESET", r"ECONNREFUSED",
    r"Could not resolve host", r"Failed to download", r"Cache service responded with 5\d\d",
]
_ENV_PATTERNS = [
    r"openai\.OpenAIError: Missing credentials", r"(?i)set the `?OPENAI_API_KEY`? .*environment variable",
    r"(?i)OPENAI_API_KEY (?:is )?(?:not set|missing|required)",
    r"ModuleNotFoundError: No module named '([^']+)'", r"ImportError: cannot import name .* from '([^']+)'",
    r"npm ERR! code E", r"npm ERR! network", r"error: Failed to (?:download|fetch|build) `?([^`\s]+)",
    r"No solution found when resolving dependencies", r"Unable to locate package", r"command not found: ([^\s]+)",
    r"/bin/sh: .*: not found", r"OSError: \[Errno", r"Playwright.*browser.*not installed",
]
_PYTEST_FAILED_LINE = re.compile(r"^(?:FAILED|ERROR) ([^\s:]+\.py)(?:::[^\s]+)?", re.M)
_COMPILE_ERROR = re.compile(r"(SyntaxError|IndentationError): ")
_FIRST_PARTY = ("app", "tests", "spikes", "agent_team", "src")


@dataclass
class FailureInput:
    gate_results: dict[str, str] = field(default_factory=dict)     # check name -> conclusion
    logs: dict[str, str] = field(default_factory=dict)             # check name -> log tail
    reports: dict[str, dict] = field(default_factory=dict)         # artifact json name -> parsed
    changed_files: list[str] = field(default_factory=list)
    mergeable: bool | None = None
    mergeable_state: str = ""
    rerun_passed: bool = False
    timed_out_waiting: bool = False
    review_verdict: str | None = None


@dataclass(frozen=True)
class Classification:
    kind: str
    summary: str
    evidence: str = ""
    failing_check: str = ""

    @property
    def repairable(self) -> bool:
        return self.kind in REPAIRABLE


def _failed(gates: dict[str, str]) -> list[str]:
    return [n for n, c in gates.items() if c in ("failure", "timed_out", "cancelled", "action_required", "startup_failure")]


def classify(inp: FailureInput) -> Classification:
    failed = _failed(inp.gate_results)
    all_logs = "\n".join(inp.logs.values())

    if inp.review_verdict in ("REQUEST_CHANGES", "BLOCK") and not failed:
        return Classification(REVIEW_REJECTED, f"independent reviewer verdict {inp.review_verdict}", "", "review")

    if inp.rerun_passed:
        return Classification(FLAKY_TEST, "the same head SHA passed on re-run without code changes", "", failed[0] if failed else "")

    if inp.timed_out_waiting:
        return Classification(INFRA_FAILURE, "CI did not report a result within the configured wait", "", "")
    if any(c in ("cancelled", "timed_out", "startup_failure") for c in inp.gate_results.values()):
        bad = [n for n, c in inp.gate_results.items() if c in ("cancelled", "timed_out", "startup_failure")]
        return Classification(INFRA_FAILURE, f"job(s) {bad} were cancelled / timed out / failed to start", "", bad[0])
    for pat in _INFRA_PATTERNS:
        m = re.search(pat, all_logs)
        if m:
            return Classification(INFRA_FAILURE, f"infrastructure error in CI logs: {m.group(0)[:120]}", _excerpt(all_logs, m.start()),
                                  failed[0] if failed else "")

    if inp.mergeable is False or inp.mergeable_state == "dirty":
        return Classification(MERGE_CONFLICT, "the PR branch conflicts with its base and cannot be merged", "", "")

    for pat in _ENV_PATTERNS:
        m = re.search(pat, all_logs)
        if m:
            module = (m.group(1) if m.groups() else "") or ""
            if "credential" in m.group(0).lower() or "OPENAI_API_KEY" in m.group(0):
                return Classification(ENVIRONMENT_FAILURE, f"missing credential in the isolated environment: {m.group(0)[:120]}",
                                      _excerpt(all_logs, m.start()), failed[0] if failed else "")
            top = module.split(".")[0].split("/")[0]
            if top and top in _FIRST_PARTY:
                return Classification(IMPLEMENTATION_FAILURE, f"first-party import error: {m.group(0)[:120]}",
                                      _excerpt(all_logs, m.start()), failed[0] if failed else "")
            return Classification(ENVIRONMENT_FAILURE, f"missing dependency/tool in the isolated environment: {m.group(0)[:120]}",
                                  _excerpt(all_logs, m.start()), failed[0] if failed else "")

    gate1 = [n for n in failed if n.startswith("gate-1")]
    if gate1:
        rep = inp.reports.get("contract_report", {})
        bad = [c["name"] for c in rep.get("checks", []) if not c.get("ok")]
        return Classification(SPEC_MISMATCH, "gate 1 contract validation failed: " + (", ".join(bad) or "see report"), "", gate1[0])

    gate4 = [n for n in failed if n.startswith("gate-4")]
    if gate4:
        rep = inp.reports.get("regression_gate_report", {})
        bad = [f"{c['name']}: {c['detail']}" for c in rep.get("checks", []) if not c.get("ok")]
        if not bad:
            # gate 4 went red WITHOUT a budget verdict: the regression machinery itself failed (a CI script
            # error such as `unrecognized arguments: --shard` on the base checkout — #67, or a missing file —
            # #35). That is implementation/infra work, never "a regression outside the budget".
            gate4_logs = "\n".join(v for k, v in inp.logs.items() if "gate-4" in k or "regression" in k) or all_logs
            m = re.search(r"(error: unrecognized arguments[^\n]*|can't open file[^\n]*|Traceback \(most recent call last\)[^\n]*|"
                          r"No such file or directory[^\n]*|##\[error\][^\n]*)", gate4_logs)
            detail = m.group(1)[:300] if m else "gate 4 failed before producing a budget verdict"
            return Classification(IMPLEMENTATION_FAILURE, f"gate 4 regression machinery failed (no budget verdict): {detail}",
                                  gate4_logs[-3000:], gate4[0])
        return Classification(REGRESSION, "corpus regression outside the declared budget", "\n".join(bad)[:2000], gate4[0])

    gate3 = [n for n in failed if n.startswith("gate-3")]
    if gate3:
        rep = inp.reports.get("verification_report", {})
        bad = [c for c in rep.get("checks", []) if not c.get("ok")]
        names = [c["name"] for c in bad]
        kinds = {n.split(" -> ")[1].split(":")[0] for n in names if " -> " in n}
        failing_tests = [_test_path(n) for n in names if " -> pytest:" in n or " -> vitest:" in n]
        if failing_tests and all(_in_changed(p, inp.changed_files) for p in failing_tests):
            return Classification(TEST_FAILURE, "the PR's own verification tests fail: " + ", ".join(failing_tests),
                                  "\n".join(f"{c['name']}: {c['detail']}" for c in bad)[:2000], gate3[0])
        return Classification(IMPLEMENTATION_FAILURE, "acceptance-criteria evidence failed: " + ", ".join(names)[:300],
                              "\n".join(f"{c['name']}: {c['detail']}" for c in bad)[:2000], gate3[0])

    gate2 = [n for n in failed if n.startswith("gate-2")]
    if gate2 and not all_logs.strip():
        # No log could be fetched for the failed gate: a repair worker would be guessing. Treat the
        # missing evidence itself as an infrastructure problem (one CI re-run, then the Team Lead).
        return Classification(INFRA_FAILURE, f"{gate2[0]} failed but no job log is available — evidence collection failed", "", gate2[0])
    if gate2:
        log = inp.logs.get(gate2[0], all_logs)
        if _COMPILE_ERROR.search(log):
            m = _COMPILE_ERROR.search(log)
            return Classification(IMPLEMENTATION_FAILURE, f"syntax error: {m.group(0)}", _excerpt(log, m.start()), gate2[0])
        tests = sorted(set(_PYTEST_FAILED_LINE.findall(log)))
        if tests and all(_in_changed(t, inp.changed_files) for t in tests):
            return Classification(TEST_FAILURE, "tests changed by the PR fail: " + ", ".join(tests)[:300], _tail(log), gate2[0])
        if tests:
            return Classification(IMPLEMENTATION_FAILURE, "existing tests fail: " + ", ".join(tests)[:300], _tail(log), gate2[0])
        if "oxlint" in log or "eslint" in log or "error TS" in log:
            return Classification(IMPLEMENTATION_FAILURE, "frontend lint/type errors", _tail(log), gate2[0])
        return Classification(IMPLEMENTATION_FAILURE, "static gate failed", _tail(log), gate2[0])

    if failed:
        return Classification(IMPLEMENTATION_FAILURE, f"check(s) failed: {failed}", _tail(all_logs), failed[0])
    return Classification(INFRA_FAILURE, "no failed check found but the run is red — inconsistent CI state", "", "")


def _test_path(check_name: str) -> str:
    target = check_name.split(" -> ", 1)[1].split(":", 1)[1]
    return target.split("::")[0]


def _in_changed(path: str, changed: list[str]) -> bool:
    p = path.lstrip("./")
    return any(c == p or c.endswith("/" + p) or p.endswith("/" + c) or p.endswith(c) for c in changed)


def _excerpt(text: str, pos: int, radius: int = 600) -> str:
    return text[max(0, pos - radius): pos + radius]


def _tail(text: str, n: int = 3000) -> str:
    return text[-n:]
