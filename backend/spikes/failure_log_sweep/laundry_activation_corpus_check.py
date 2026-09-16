"""§5A confirmation: the shipped scale_program change is a no-op for the real 418-context corpus
(2026-09-16, docs/LAUNDRY_ROOM_ACTIVATION_REPORT.md).

    .venv/bin/python3 spikes/failure_log_sweep/laundry_activation_corpus_check.py

This is a SINGLE PASS, not an A/B: `_laundry_deficit_targets` (concept_generator.py) only runs
when `scale_program`'s `rooms` argument already contains a `ProgramRole.LAUNDRY` room, and no
context in this log can ever produce one — the field predates the log, and `LAUNDRY_ROOM_ENABLED`
being on changes nothing without an explicit `laundry_requested=True` on the `Project`, which
`project_from_context` never sets. The new branch is provably unreachable for every context here;
this run exists to confirm that reasoning empirically rather than resting on it alone — same
planned/refused counts and zero crashes as the last verified baseline
(64453c8, docs/LAUNDRY_ROOM_PHASE1_REPORT.md §3: 404/432 planned) is the expected, sufficient
result. Row-rescue behaviour (the other 2026-09-16 change) already has its OWN dedicated,
re-runnable A/B — `laundry_gate_ab.py` — not repeated here.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.demo import service as svc  # noqa: E402
from app.vertical_slice import concept_generator as cg  # noqa: E402
from spikes.failure_log_sweep.sweep import distinct_contexts, key_of, project_from_context  # noqa: E402

cg.LAUNDRY_ROOM_ENABLED = True  # matches the state this corpus will actually ship under


def main() -> None:
    contexts = distinct_contexts()
    print(f"scenarios: {len(contexts)}")
    started = time.perf_counter()
    statuses: dict[str, str] = {}
    codes: Counter = Counter()
    crashes: list[tuple[str, str]] = []
    for i, ctx in enumerate(contexts, start=1):
        try:
            res = svc.generate_demo_design(project_from_context(ctx))
            statuses[key_of(ctx)] = "PLANNED"
            assert res.design.validation.passed, "a planned result must pass validation"
            assert not any(r.type == "LAUNDRY" for r in res.design.rooms), (
                "no logged context can ever request a laundry room")
        except svc.DemoGenerationError as exc:
            statuses[key_of(ctx)] = "REFUSED"
            codes[exc.code] += 1
        except Exception as exc:  # noqa: BLE001
            statuses[key_of(ctx)] = "CRASH"
            crashes.append((key_of(ctx), f"{type(exc).__name__}: {exc}"))
        if i % 100 == 0:
            print(f"  {i}/{len(contexts)} ({time.perf_counter() - started:.0f}s)", flush=True)

    planned = sum(1 for s in statuses.values() if s == "PLANNED")
    refused = sum(1 for s in statuses.values() if s == "REFUSED")
    crashed = sum(1 for s in statuses.values() if s == "CRASH")
    print(f"\ndone in {time.perf_counter() - started:.0f}s")
    print(f"planned: {planned}/{len(contexts)}   refused: {refused}   crashed: {crashed}")
    print("refusal codes:", dict(codes))
    for key, msg in crashes:
        print("  CRASH:", key, "->", msg)
    print("\nVERDICT:", "MATCHES the last verified baseline (404 planned, 0 crashes)"
          if planned == 404 and crashed == 0 else
          "DIFFERS from the last verified baseline — investigate before shipping")


if __name__ == "__main__":
    main()
