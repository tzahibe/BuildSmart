"""Measure OpenAIRequirementParser.extract() wall-clock latency (Issue #89).

    OPENAI_API_KEY=... uv run python scripts/measure_parser_latency.py
    OPENAI_API_KEY=... REQUIREMENTS_REASONING_EFFORT=low uv run python scripts/measure_parser_latency.py
    OPENAI_API_KEY=... uv run python scripts/measure_parser_latency.py --repeats 5

Run from `backend/`. Parses a fixed list of 6 real Hebrew briefs (five from
`tests/wet_room_corpus/corpus.json`, plus the owner's own Abu Snan brief that motivated this
Issue) `--repeats` times each against the real OpenAI API, and prints p50/p95 wall time per brief
plus the extraction JSON of the last parse — so the lead/owner can compare `reasoning_effort`
settings with a real key. This script makes real API calls: CI never runs it. The reasoning effort
sent is whatever `OpenAIRequirementParser` resolves (default "minimal", or the
`REQUIREMENTS_REASONING_EFFORT` env var if set) — set that env var before running to compare
efforts.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The owner's own brief measured 2026-09-21 (Abu Snan, 15x17 m, 130 m^2) plus five real briefs
# from the hand-labelled wet-room corpus, covering a spread of field combinations.
BRIEFS: list[str] = [
    'שלושה חדרי שינה, חדר הורים עם מקלחת, מקלחת משותפת, חדר כביסה, סלון ומטבח',
    'בית פרטי בן קומה אחת עם 3 חדרי שינה, ממ"ד, סלון ומטבח פתוחים זה לזה, 2 חדרי רחצה ו-2 מקומות חניה.',
    'בית עם 2 חדרי שינה, חדר הורים עם שירותים, שירותי אורחים\nסלון ומטבח',
    'בית עם 4 חדרים, חדר הורים, 2 שירותים, מקלחת מטבח וסלון',
    '2 חדרי ילדים, חדר הורים גדול עם מקלחת ושירותים, סלון, מטבח, חדר עבודה קטן, ו2 חניות',
    'בית עם שלושה חדרי שינה, מקלחת, שירותים, סלון ומטבח',
]


def _percentile(sorted_values: list[float], pct: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def run(repeats: int) -> None:
    from app.requirements.parser import OpenAIRequirementParser

    parser = OpenAIRequirementParser()
    print(f"reasoning_effort={parser._reasoning_effort!r} model={parser._model!r} repeats={repeats}\n")

    all_times: list[float] = []
    for i, brief in enumerate(BRIEFS):
        times: list[float] = []
        extraction_json = ""
        for _ in range(repeats):
            start = time.monotonic()
            extraction = parser.extract(brief)
            times.append(time.monotonic() - start)
            extraction_json = extraction.model_dump_json()
        times.sort()
        all_times.extend(times)
        print(f"brief {i}: {brief!r}")
        print(f"  p50={median(times):.2f}s p95={_percentile(times, 0.95):.2f}s samples={times}")
        print(f"  extraction: {extraction_json}\n")

    all_times.sort()
    print(f"overall p50={median(all_times):.2f}s p95={_percentile(all_times, 0.95):.2f}s "
          f"across {len(all_times)} parses")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=3, help="parses per brief (default 3)")
    args = ap.parse_args()
    run(args.repeats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
