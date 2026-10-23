"""GATE 3 — requirement verification: every acceptance criterion's mapped evidence must pass.

Runs each deterministic target from the manifest — TEST (`pytest:`, `vitest:`, `cmd:`), STATIC
(`static:<check>`), ARTIFACT (`file:`, `grep:`) — and records its real result. REGRESSION
(`regression:corpus`) is satisfied by gate 4's budget evaluation and SEMANTIC_REVIEW (`review:`)
by gate 5's independent reviewer; both are recorded here as deferred, never as a pass on their
own. An AC with no deterministic target passing (and nothing deferred) fails the gate.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from agent_team.ci.common import GateReport, repo_root, run, write_report


def run_target(kind: str, target: str, root: Path, *, timeout: int = 1800) -> tuple[bool, str]:
    if kind == "pytest":
        # TEST_MODE=REGRESSION so a target carrying the `regression` marker (tests/conftest.py)
        # actually executes here instead of being silently skipped-but-exit-0 and recorded as a
        # false PASS (Issue #38 review finding). Harmless for unmarked targets: TEST_MODE only
        # gates marker collection, nothing else reads it.
        env = {"TEST_MODE": "REGRESSION"}
        # The whole suite directory ("scripts/agent_team/tests") as well as a file or a nodeid under
        # it: without the directory form, a plan target naming the orchestrator's own suite ran
        # `uv run pytest scripts/agent_team/tests` from backend/, collected nothing, and failed the
        # gate for the wrong reason (#252).
        if target.startswith("scripts/agent_team"):
            proc = run(f"uv run --project scripts/agent_team pytest -q -p no:cacheprovider {target}", root, timeout=timeout, env=env)
        else:
            rel = target[len("backend/"):] if target.startswith("backend/") else target
            proc = run(f"uv run pytest -q -p no:cacheprovider {rel}", root / "backend", timeout=timeout, env=env)
        tail = (proc.stdout.strip().splitlines() or [""])[-1]
        detail = tail[:300] or proc.stderr[-300:]
        # Name what failed. "1 failed, 302 passed" alone cannot be acted on: a red gate has to say
        # WHICH test, or the only way to read it is to re-run it and hope (#252).
        failed = [l.split(" ", 1)[1] for l in proc.stdout.splitlines() if l.startswith("FAILED ")]
        if failed:
            detail = f"{detail} — FAILED: {'; '.join(failed)}"[:300]
        if proc.returncode == 0 and "passed" not in tail:
            return False, f"no test actually passed (skipped or deselected): {detail}"
        return proc.returncode == 0, detail
    if kind == "vitest":
        rel = target[len("frontend/"):] if target.startswith("frontend/") else target
        proc = run(f"npx vitest run {rel}", root / "frontend", timeout=timeout)
        tail = " ".join(l.strip() for l in proc.stdout.strip().splitlines()[-3:])
        return proc.returncode == 0, tail[:300] or proc.stderr[-300:]
    if kind == "file":
        p = root / target
        ok = p.is_file() and p.stat().st_size > 0
        return ok, "exists, non-empty" if ok else "missing or empty"
    if kind == "grep":
        path, _, pattern = target.partition(":")
        p = root / path
        if not p.is_file():
            return False, f"{path} missing"
        text = p.read_text(encoding="utf-8", errors="replace")
        found = re.search(pattern, text, re.M) is not None
        return found, "pattern found" if found else f"pattern {pattern!r} not found in {path}"
    if kind == "cmd":
        p = root / target
        if not p.is_file():
            return False, f"{target} missing"
        runner = "python3" if p.suffix == ".py" else "bash"
        proc = run(f"{runner} {target}", root, timeout=timeout)
        tail = (proc.stdout.strip().splitlines() or [""])[-1]
        return proc.returncode == 0, tail[:300] or proc.stderr[-300:]
    if kind == "static":
        return run_static(target, root, timeout=timeout)
    if kind == "regression":
        return True, "deferred to gate-4-regression (budget evaluation)"
    if kind == "review":
        return True, "deferred to gate-5 independent review (semantic; not deterministic evidence)"
    return False, f"unknown verification kind {kind!r}"


STATIC_COMMANDS = {
    "backend-compile": ("backend", "uv run python -m compileall -q app tests spikes"),
    "backend-import": ("backend", "uv run python -c 'import app.main'"),
    "frontend-lint": ("frontend", "npm run lint"),
    "frontend-types": ("frontend", "npx tsc -b"),
}


def run_static(target: str, root: Path, *, timeout: int = 1800) -> tuple[bool, str]:
    if target not in STATIC_COMMANDS:
        return False, f"unknown static check {target!r}"
    cwd, cmd = STATIC_COMMANDS[target]
    proc = run(cmd, root / cwd, timeout=timeout)
    tail = " ".join(l.strip() for l in (proc.stdout + proc.stderr).strip().splitlines()[-2:])
    return proc.returncode == 0, (tail[:300] or "ok")


def evaluate(manifest: dict, root: Path, *, runner=run_target) -> GateReport:
    rep = GateReport("gate-3-verification")
    results_by_ac: dict[str, list[bool]] = {}
    # Several acceptance criteria legitimately name the SAME deterministic target (four of #252's
    # name `pytest:scripts/agent_team/tests`). Running it once and reusing the result is the same
    # evidence — a deterministic target cannot disagree with itself — at a quarter of the wall time
    # and a quarter of the exposure to any flake it carries. The reuse is stated in the row.
    ran: dict[tuple[str, str], tuple[bool, str]] = {}
    for t in manifest.get("targets", []):
        key = (t["kind"], t["target"])
        if key in ran:
            ok, detail = ran[key][0], f"{ran[key][1]} (same target as an earlier criterion: executed once)"
        else:
            ok, detail = runner(t["kind"], t["target"], root)
            ran[key] = (ok, detail)
        rep.add(f"{t['ac']} -> {t['kind']}:{t['target']}", ok, detail)
        results_by_ac.setdefault(t["ac"], []).append(ok)
    for ac in manifest.get("acceptance_criteria", []):
        outcomes = results_by_ac.get(ac["id"])
        if not outcomes:
            rep.add(f"{ac['id']} has evidence", False, "no verification target ran for this criterion")
        elif not all(outcomes):
            rep.add(f"{ac['id']} evidence passes", False, f"{outcomes.count(False)} of {len(outcomes)} targets failed")
    rep.extra["issue"] = manifest.get("issue")
    return rep


def main() -> int:
    root = repo_root()
    manifest_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / ".agent" / "ci" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rep = evaluate(manifest, root)
    write_report(rep, root / ".agent" / "ci" / "verification_report.json")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
