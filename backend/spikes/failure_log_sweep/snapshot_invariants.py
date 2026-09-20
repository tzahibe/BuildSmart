"""Gate-4 corpus outcome invariants (status + refusal code per context), evaluated from a
`corpus_snapshot.py --save` snapshot instead of replaying `generate_demo_design` a third time.

`test_frozen_regression_corpus.py::test_frozen_context_reproduces_expected_outcome` has always
asserted exactly two facts per frozen context: `status == expected_outcome` and, for refusals,
`code == expected_code`. The head snapshot gate-4 already computes for `test_quality_baseline.py`
carries both fields per context — `evaluate()` below re-derives the same verdict from that data,
with zero calls to `generate_demo_design`.

Shipped in shadow mode (Issue #66): CI still runs the old replay *and* this snapshot-based
evaluation, then fails the job if the two verdicts ever differ. The old replay is only removed
once several real PRs have shown identical verdicts (not yet — see
docs/wiki/architecture/agent-team-workflow.md, gate-4 section).

    uv run python spikes/failure_log_sweep/snapshot_invariants.py evaluate \\
        --snapshot .agent/ci/head_snapshot.json --report .agent/ci/invariants_from_snapshot.json
    uv run python spikes/failure_log_sweep/snapshot_invariants.py from-junit \\
        --junit .agent/ci/regression_junit.xml --report .agent/ci/invariants_replay.json
    uv run python spikes/failure_log_sweep/snapshot_invariants.py compare \\
        --from-snapshot .agent/ci/invariants_from_snapshot.json --from-replay .agent/ci/invariants_replay.json
"""
from __future__ import annotations

import argparse
import functools
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "tests" / "regression_corpus" / "corpus.json"


class SnapshotError(Exception):
    """The snapshot is unusable for evaluation — never silently accepted."""


@dataclass(frozen=True)
class Mismatch:
    key: str
    reason: str
    expected: dict
    actual: dict | None

    def to_dict(self) -> dict:
        return {"key": self.key, "reason": self.reason, "expected": self.expected, "actual": self.actual}


@dataclass(frozen=True)
class InvariantsReport:
    total: int
    mismatches: tuple[Mismatch, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches

    @property
    def failed(self) -> int:
        return len(self.mismatches)

    @property
    def passed(self) -> int:
        return self.total - self.failed

    def failing_keys(self) -> list[str]:
        return sorted(m.key for m in self.mismatches)

    def to_dict(self) -> dict:
        return {
            "total": self.total, "passed": self.passed, "failed": self.failed, "ok": self.ok,
            "mismatches": [m.to_dict() for m in self.mismatches],
        }


@functools.lru_cache(maxsize=1)
def current_head_sha(repo_root: Path | None = None) -> str:
    root = repo_root or Path(__file__).resolve().parents[2]
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=str(root),
    ).stdout.strip()


def validate_snapshot(snapshot: dict, corpus_cases: list[dict], *, expected_sha: str | None = None) -> None:
    """Raise `SnapshotError` naming the mismatch — a stale or short snapshot must never be
    silently accepted as evaluable."""
    if expected_sha is not None:
        snap_sha = snapshot.get("sha")
        if snap_sha != expected_sha:
            raise SnapshotError(f"snapshot head_sha {snap_sha!r} does not match current HEAD {expected_sha!r}")
    results = snapshot.get("results", {})
    if len(results) != len(corpus_cases):
        raise SnapshotError(f"snapshot has {len(results)} context(s), corpus has {len(corpus_cases)}")


def evaluate(corpus_cases: list[dict], snapshot: dict) -> InvariantsReport:
    """The same two facts the replay has always asserted (`status == expected_outcome`, and for
    refusals `code == expected_code`), read from `snapshot["results"]` instead of calling
    `generate_demo_design`."""
    results = snapshot.get("results", {})
    mismatches: list[Mismatch] = []
    for case in corpus_cases:
        key = case["source_key"]
        expected = {"status": case["expected_outcome"], "code": case.get("expected_code")}
        row = results.get(key)
        if row is None:
            mismatches.append(Mismatch(key, "missing from snapshot", expected, None))
            continue
        actual = {"status": row.get("status"), "code": row.get("code")}
        if actual["status"] != expected["status"]:
            mismatches.append(Mismatch(key, "status mismatch", expected, actual))
        elif expected["status"] == "REFUSED" and actual["code"] != expected["code"]:
            mismatches.append(Mismatch(key, "refusal code mismatch", expected, actual))
    return InvariantsReport(total=len(corpus_cases), mismatches=tuple(mismatches))


_JUNIT_TEST_NAME = "test_frozen_context_reproduces_expected_outcome"


def replay_verdict_from_junit(path: Path) -> dict:
    """The same pass/fail + failing-context-keys verdict as `evaluate()`, read from the replay's
    own `--junitxml` report instead of a snapshot — so the two can be compared directly."""
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find(".//testsuite")
    total = 0
    failing: list[str] = []
    for case in suite.iter("testcase"):
        name = case.get("name", "")
        if not name.startswith(_JUNIT_TEST_NAME + "["):
            continue
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            failing.append(name[len(_JUNIT_TEST_NAME) + 1 : -1])
    return {"total": total, "passed": total - len(failing), "failed": len(failing), "ok": not failing,
            "failing_keys": sorted(failing)}


def compare_verdicts(from_snapshot: dict, from_replay: dict) -> list[str]:
    """Discrepancy descriptions between the two verdicts — empty means they agree."""
    diffs = []
    if bool(from_snapshot.get("ok")) != bool(from_replay.get("ok")):
        diffs.append(f"pass/fail differs: from-snapshot ok={from_snapshot.get('ok')} from-replay ok={from_replay.get('ok')}")
    snap_failing = {m["key"] for m in from_snapshot.get("mismatches", [])}
    replay_failing = set(from_replay.get("failing_keys", []))
    if snap_failing != replay_failing:
        diffs.append(
            "failing-context sets differ: only in from-snapshot="
            f"{sorted(snap_failing - replay_failing)[:10]} only in from-replay={sorted(replay_failing - snap_failing)[:10]}"
        )
    return diffs


def _cmd_evaluate(args: argparse.Namespace) -> int:
    with open(args.corpus, encoding="utf-8") as f:
        corpus_cases = json.load(f)["cases"]
    with open(args.snapshot, encoding="utf-8") as f:
        snapshot = json.load(f)
    t0 = time.time()
    expected_sha = None if args.skip_sha_check else current_head_sha()
    try:
        validate_snapshot(snapshot, corpus_cases, expected_sha=expected_sha)
    except SnapshotError as exc:
        print(f"snapshot invalid: {exc}", file=sys.stderr)
        return 2
    report = evaluate(corpus_cases, snapshot)
    doc = {**report.to_dict(), "seconds": round(time.time() - t0, 3)}
    _write_report(args.report, doc)
    print(f"from-snapshot: {report.passed}/{report.total} passed"
          + ("" if report.ok else f", {report.failed} mismatch(es)") + f" ({doc['seconds']}s)")
    for m in report.mismatches[:20]:
        print(f"  MISMATCH {m.key} {m.reason}: expected={m.expected} actual={m.actual}")
    return 0 if report.ok else 1


def _cmd_from_junit(args: argparse.Namespace) -> int:
    t0 = time.time()
    doc = replay_verdict_from_junit(Path(args.junit))
    doc["seconds"] = round(time.time() - t0, 3)
    _write_report(args.report, doc)
    print(f"from-replay: {doc['passed']}/{doc['total']} passed"
          + ("" if doc["ok"] else f", {doc['failed']} mismatch(es)") + f" ({doc['seconds']}s)")
    return 0 if doc["ok"] else 1


def _cmd_compare(args: argparse.Namespace) -> int:
    with open(args.from_snapshot, encoding="utf-8") as f:
        snap_doc = json.load(f)
    with open(args.from_replay, encoding="utf-8") as f:
        replay_doc = json.load(f)
    print(f"from-snapshot: ok={snap_doc.get('ok')} total={snap_doc.get('total')} seconds={snap_doc.get('seconds')}")
    print(f"from-replay:   ok={replay_doc.get('ok')} total={replay_doc.get('total')} seconds={replay_doc.get('seconds')}")
    diffs = compare_verdicts(snap_doc, replay_doc)
    if diffs:
        for d in diffs:
            print(f"MISMATCH: {d}")
        return 1
    print("verdicts match")
    return 0


def _write_report(path: Path | None, doc: dict) -> None:
    if path is None:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p_eval = sub.add_parser("evaluate", help="corpus outcome invariants from a head snapshot")
    p_eval.add_argument("--snapshot", type=Path, required=True)
    p_eval.add_argument("--corpus", type=Path, default=CORPUS)
    p_eval.add_argument("--report", type=Path)
    p_eval.add_argument("--skip-sha-check", action="store_true",
                        help="do not require the snapshot's sha to match the current HEAD")
    p_eval.set_defaults(func=_cmd_evaluate)

    p_junit = sub.add_parser("from-junit", help="the replay's own pass/fail verdict from its junit report")
    p_junit.add_argument("--junit", type=Path, required=True)
    p_junit.add_argument("--report", type=Path)
    p_junit.set_defaults(func=_cmd_from_junit)

    p_cmp = sub.add_parser("compare", help="fail if the two verdicts differ")
    p_cmp.add_argument("--from-snapshot", type=Path, required=True)
    p_cmp.add_argument("--from-replay", type=Path, required=True)
    p_cmp.set_defaults(func=_cmd_compare)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
