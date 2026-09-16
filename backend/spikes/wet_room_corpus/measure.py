"""Before/after on the wet-room corpus (`tests/wet_room_corpus/corpus.json`).

    PYTHONPATH=. .venv/bin/python spikes/wet_room_corpus/measure.py            # offline
    PYTHONPATH=. .venv/bin/python spikes/wet_room_corpus/measure.py --live     # + the real parser

OFFLINE. "Before" is what the old count-based parser stored for each record and what the engine
built from it; "after" is the same record with the wet rooms the normalizer derives from the
brief's LABELLED demand, planned through the real `generate_demo_design`. Same plot, same target
area, same everything else. Reports, over the records that planned before: surplus wet rooms by
kind, TOILET rooms and their m², questions now asked instead of silently planned.

LIVE (`--live`, needs OPENAI_API_KEY; ~61 gpt-5-nano calls). Runs the real `extract()` on every
distinct brief and scores the model's `FixtureDemand` against the labels, then normalizes it and
scores the rooms against the expected ones — the end-to-end number for the new pipeline. Also
re-parses a few briefs three times for stability.

Throwaway measurement code, per spikes/ policy: never imported by production code.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from app.demo.service import DemoGenerationError, generate_demo_design
from app.projects.models import Project
from app.requirements.parser import FixtureDemand
from app.requirements.wet_room_normalizer import normalize_wet_rooms

ROOT = Path(__file__).resolve().parents[2]
CORPUS = json.loads((ROOT / "tests/wet_room_corpus/corpus.json").read_text(encoding="utf-8"))["briefs"]
PROJECTS = json.loads((ROOT / "app/data/projects.json").read_text(encoding="utf-8"))


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"


def wet_rooms_of(design):
    return [(r.type, round(r.area_m2, 1)) for r in design.rooms if r.type in ("BATHROOM", "TOILET")]


def plan(record: dict):
    try:
        result = generate_demo_design(Project.model_validate(record))
        return "PLANNED", wet_rooms_of(result.design), None
    except DemoGenerationError as exc:
        return "REFUSED", [], exc.code
    except Exception as exc:  # noqa: BLE001 — a measurement, not a gate
        return "ERROR", [], repr(exc)[:80]


def record_with(record: dict, normalized) -> dict:
    out = dict(record)
    out["wet_rooms"] = {"value": normalized.wet_rooms.value, "source": normalized.wet_rooms.source.value}
    out["wet_room_kinds"] = [dict(kind=k.kind, host=k.host, strength=k.strength, source_text=k.source_text,
                                  origin=k.origin, source="requested") for k in normalized.kinds]
    out["wet_room_questions"] = [dict(code=q.code, text=q.text, source_text=q.source_text,
                                      proposal_kinds=[dict(kind=k.kind, host=k.host, strength=k.strength,
                                                           source_text=k.source_text, origin=k.origin)
                                                      for k in q.proposal_kinds])
                                 for q in normalized.questions]
    return out


def offline() -> None:
    full = {pid[:8]: pid for pid in PROJECTS}
    rows = []
    for brief in CORPUS:
        labels = brief["labels"]
        exp_bath = labels["ensuites"] + labels["bathrooms"] - labels["ensuites"] if labels["bathrooms"] else 0
        normalized = normalize_wet_rooms(FixtureDemand.model_validate(brief["demand"]))
        exp_wc = sum(k.kind == "guest_wc" for k in normalized.kinds)
        exp_bath = sum(k.kind != "guest_wc" for k in normalized.kinds)
        for stored in brief["stored"]:
            record = PROJECTS[full[stored["project_id"]]]
            before_status, before_wet, _ = plan(record)
            if before_status != "PLANNED":
                continue
            after_status, after_wet, code = plan(record_with(record, normalized))
            rows.append(dict(idx=brief["idx"], cls=brief["class"], pid=stored["project_id"],
                             before=before_wet, after=after_wet, after_status=after_status, code=code,
                             exp_bath=exp_bath, exp_wc=exp_wc, questions=[q.code for q in normalized.questions],
                             text=brief["text"].replace("\n", " ")[:60]))
            print(f"[{brief['idx']:02d}] {stored['project_id']} before={before_wet} -> {after_status} {after_wet or code}", flush=True)

    n = len(rows)
    print(f"\n=== OFFLINE: {n} records that planned before ===")
    for label, key in (("BEFORE", "before"), ("AFTER", "after")):
        planned = [r for r in rows if key == "before" or r["after_status"] == "PLANNED"]
        surplus_b = sum(max(0, sum(t == "BATHROOM" for t, _ in r[key]) - r["exp_bath"]) for r in planned)
        surplus_t = sum(max(0, sum(t == "TOILET" for t, _ in r[key]) - r["exp_wc"]) for r in planned)
        missing_t = sum(max(0, r["exp_wc"] - sum(t == "TOILET" for t, _ in r[key])) for r in planned)
        exact = sum(sum(t == "BATHROOM" for t, _ in r[key]) == r["exp_bath"]
                    and sum(t == "TOILET" for t, _ in r[key]) == r["exp_wc"] for r in planned)
        toilets = [a for r in planned for t, a in r[key] if t == "TOILET"]
        wet_m2 = sum(a for r in planned for _, a in r[key])
        print(f"{label}: plans={len(planned)}  wet rooms exactly as the brief's functions: {pct(exact, len(planned))}  "
              f"surplus BATHROOMS={surplus_b}  surplus TOILETS={surplus_t}  missing WCs={missing_t}  "
              f"TOILET rooms={len(toilets)} ({sum(toilets):.1f} m², mean {sum(toilets)/len(toilets) if toilets else 0:.1f})  "
              f"wet-room area total {wet_m2:.1f} m² (mean {wet_m2/len(planned):.1f}/plan)")
    asked = [r for r in rows if r["after_status"] == "REFUSED" and r["code"] == "NEEDS_CLARIFICATION"]
    other = [r for r in rows if r["after_status"] != "PLANNED" and r not in asked]
    print(f"AFTER: questions asked instead of a plan: {len(asked)} "
          f"({collections.Counter(tuple(r['questions']) or ('I4',) for r in asked)}); other refusals: {len(other)} "
          f"{[(r['pid'], r['code']) for r in other]}")
    (ROOT / "spikes/wet_room_corpus/offline.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def demand_shape(d: dict) -> dict:
    return dict(bathrooms=sum(b.get("count", 1) for b in d["bathrooms"]),
                attached=sorted((a["host"], a["fixtures"]) for a in d["attached"] for _ in range(a.get("count", 1))),
                separate_wcs=sum(w.get("count", 1) for w in d["separate_wcs"]),
                toilet_mentions=d["toilet_mentions"])


def live() -> None:
    from dotenv import load_dotenv

    from app.requirements.parser import OpenAIRequirementParser
    load_dotenv(ROOT / ".env")   # what app.main does before constructing the parser
    from openai import OpenAI
    parser = OpenAIRequirementParser()
    # The SDK's default per-request timeout is 10 minutes; a measurement wants to see a hang.
    parser._client = OpenAI(timeout=90.0, max_retries=2)
    ok_demand = ok_rooms = ok_questions = 0
    misses = []
    live_rows = []
    import time
    for brief in CORPUS:
        started = time.time()
        extracted = parser.extract(brief["text"]).wet_room_demand
        print(f"    extract {brief['idx']:02d} took {time.time() - started:.1f}s", flush=True)
        got, want = demand_shape(extracted.model_dump()), demand_shape(brief["demand"])
        normalized = normalize_wet_rooms(extracted, brief["text"])   # with the backstop
        rooms = [[k.kind, k.host, k.origin] for k in normalized.kinds]
        questions = [q.code for q in normalized.questions]
        d_ok, r_ok, q_ok = got == want, rooms == brief["expected"]["kinds"], questions == brief["expected"]["questions"]
        ok_demand += d_ok; ok_rooms += r_ok; ok_questions += q_ok
        if not (d_ok and r_ok and q_ok):
            misses.append((brief["idx"], brief["class"], got, want, rooms, brief["expected"]["kinds"], brief["text"][:70]))
        live_rows.append(dict(idx=brief["idx"], demand=extracted.model_dump(), rooms=rooms, questions=questions,
                              demand_ok=d_ok, rooms_ok=r_ok))
        print(f"[{brief['idx']:02d}] {brief['class']} demand {'ok' if d_ok else 'MISS'} rooms {'ok' if r_ok else 'MISS'}", flush=True)
    n = len(CORPUS)
    print(f"\n=== LIVE ({parser._model}): {n} distinct briefs ===")
    print(f"FixtureDemand matches the labels: {pct(ok_demand, n)}; rooms after normalization match: {pct(ok_rooms, n)}; "
          f"questions match: {pct(ok_questions, n)}")
    for cls in ("P1", "P2", "P3", "P4", "P5"):
        g = [r for r, b in zip(live_rows, CORPUS) if b["class"] == cls]
        print(f"   {cls}: rooms ok {pct(sum(r['rooms_ok'] for r in g), len(g))}")
    for m in misses:
        print("   MISS", m)
    (ROOT / "spikes/wet_room_corpus/live.json").write_text(json.dumps(live_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    stability(parser)


def stability(parser=None) -> None:
    """The briefs the old parser was least stable on, three parses each, through the backstop:
    distinct room lists per brief, and whether any parse would have passed a wrong room list
    silently (no question) — the number the backstop exists to hold at zero."""
    if parser is None:
        from dotenv import load_dotenv

        from openai import OpenAI

        from app.requirements.parser import OpenAIRequirementParser
        load_dotenv(ROOT / ".env")
        parser = OpenAIRequirementParser()
        parser._client = OpenAI(timeout=90.0, max_retries=2)
    unstable = [b for b in CORPUS if b["idx"] in (3, 5, 9, 2, 1)]
    flips = silent = converted = 0
    for b in unstable:
        seen = set()
        for _ in range(3):
            got = normalize_wet_rooms(parser.extract(b["text"]).wet_room_demand, b["text"])
            rooms = [[k.kind, k.host, k.origin] for k in got.kinds]
            asked = any(q.code == "EXTRACTION_MISMATCH" for q in got.questions)
            seen.add(json.dumps(rooms))
            if rooms != b["expected"]["kinds"]:
                converted += asked
                silent += not asked
        flips += len(seen) > 1
        print(f"   stability [{b['idx']:02d}]: {len(seen)} distinct room lists in 3 parses", flush=True)
    print(f"briefs whose rooms changed between parses: {flips}/{len(unstable)}; wrong room lists: "
          f"{converted} converted to a question, {silent} silent")


if __name__ == "__main__":
    if "--live" in sys.argv:
        live()
    elif "--stability" in sys.argv:
        stability()
    else:
        offline()
