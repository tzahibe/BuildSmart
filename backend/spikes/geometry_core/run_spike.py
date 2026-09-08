"""Geometry Core Proof Spike — runner.  `python3 run_spike.py`"""
from __future__ import annotations

import sys
import time

from engine import SpikeInfeasible, net_rect_m, solve_fixture
from fixtures import ALL_FIXTURES
from model import Side, u_to_m
from validate import validate

BAR = "=" * 78


def main() -> int:
    failures: list[str] = []

    for make in ALL_FIXTURES:
        fixture = make()
        print(f"\n{BAR}\n{fixture.name}\n{BAR}")
        t0 = time.perf_counter()
        try:
            res = solve_fixture(fixture)
        except SpikeInfeasible as exc:
            print(f"  !! NOT REALIZABLE: {exc}")
            failures.append(f"{fixture.name}: {exc}")
            continue
        elapsed = (time.perf_counter() - t0) * 1000

        for note in res.notes:
            print(f"  · {note}")
        print(f"  · solved in {elapsed:.0f} ms")

        print(f"\n  {'zone':<12} {'centerline':>14} {'net w×d':>14} {'net m²':>8}  walls")
        for z in fixture.zones:
            if z.zone_id not in res.rects:
                continue
            r = res.rects[z.zone_id]
            nw, nh, na = net_rect_m(z.zone_id, r, res.walls)
            wl = "".join(
                {"EXTERIOR": "X", "PARTITION": "p", "RC_SAFE_ROOM": "R", "OPEN": "·"}[
                    res.walls[(z.zone_id, s)].value] for s in (Side.N, Side.E, Side.S, Side.W))
            print(f"  {z.zone_id:<12} {u_to_m(r.w):>6.2f}×{u_to_m(r.h):<7.2f}"
                  f" {nw:>6.2f}×{nh:<7.2f} {na:>8.2f}  {wl}")
        print("   (walls read N,E,S,W — X=exterior p=partition R=RC ·=no wall)")

        rep = validate(fixture, res)
        print()
        for p in rep.proofs:
            print(f"  [{'PASS' if p.passed else 'FAIL'}] {p.proof_id} {p.name:<34} {p.detail}")
        print("\n  facts: " + " | ".join(f"{k}={v}" for k, v in rep.facts.items()))
        if not rep.ok:
            failures.extend(f"{fixture.name}/{p.proof_id} {p.name}: {p.detail}"
                            for p in rep.proofs if not p.passed)

    print(f"\n{BAR}")
    if failures:
        print(f"SPIKE RESULT: FAILED ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SPIKE RESULT: ALL {len(ALL_FIXTURES)} FIXTURES REALIZED, ALL PROOFS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
