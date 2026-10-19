"""#213 — turn `results.json` (+ the browser's `label-metrics.json`) into the report's tables.

Every number in `COMPARISON-preview-corpus.md`'s objective section is printed by this module, so a
reader can re-derive any cell rather than trust a hand-typed one. It makes no judgment: there is no
"better" column here. Judgments live in the report's own, separately-labelled section.

    uv run python -m app.ai_harness.comparison_corpus.report <data_dir> [figures_rel_path]
"""
from __future__ import annotations

import json
import os
import sys


def _n(v, fmt="{:.0f}"):
    return "—" if v is None else fmt.format(v)


def _engine_cell(rec: dict, key: str, fmt="{:.0f}"):
    if rec.get("outcome") != "PLAN":
        return rec.get("code", rec.get("outcome", "—"))
    return _n(rec.get(key), fmt)


def corpus_table(rows: list[dict]) -> str:
    out = ["| brief | source | envelope family | envelope | programme | requested m² |",
           "|---|---|---|---|---|---:|"]
    for r in rows:
        p = r["programme"]
        prog = (f"{p['bedrooms']}bd / {p['wet_rooms']}wet"
                f"{' / ממ״ד' if p.get('safe_room') else ''}{' / open' if p.get('open_plan') else ''}")
        src = ("`topology_poc/briefs.py`" if r["source"] == "real"
               else "`shape-agnostic-realizer/cases/frozen-six.json`")
        out.append(f"| {r['brief']} | {src} | {r['family']} | {r['envelope']} | {prog} | {r['requested_m2']:.0f} |")
    return "\n".join(out)


FACTS = (
    ("gross built m²", "gross_m2", "{:.0f}"),
    ("of requested %", "area_fidelity_pct", "{:.0f}"),
    ("net m²", "net_m2", "{:.0f}"),
    ("circulation share %", "circulation_share", "{:.1%}"),
    ("worst bedroom aspect", "worst_bedroom_aspect", "{:.2f}"),
    ("rooms with no window", "rooms_no_window", "len"),
    ("validators failed", "validators_failed", "len"),
    ("seconds", "seconds", "{:.1f}"),
)


def facts_table(rows: list[dict], labels: dict) -> str:
    head = ("| brief | engine | gross m² | % of request | net m² | circ. share | worst bed aspect | "
            "no-window rooms | validators | label collisions | labels outside room | s |")
    out = [head, "|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|"]
    for r in rows:
        for engine in ("production", "brain"):
            rec = r[engine]
            if rec.get("outcome") != "PLAN":
                out.append(f"| {r['brief']} | {engine} | **{rec.get('code', rec['outcome'])}** | | | | | | | | | "
                           f"{_n(rec.get('seconds'), '{:.1f}')} |")
                continue
            lm = labels.get(f"{r['brief']}__{engine}", {})
            checks_total = rec.get("validators_total", 0)
            failed = rec.get("validators_failed") or []
            out.append(
                f"| {r['brief']} | {engine} | {rec['gross_m2']:.0f} | {rec['area_fidelity_pct']:.0f}% | "
                f"{rec['net_m2']:.0f} | {rec['circulation_share']:.1%} | "
                f"{_n(rec.get('worst_bedroom_aspect'), '{:.2f}')} | {len(rec.get('rooms_no_window') or [])} | "
                f"{'all ' + str(checks_total) + ' pass' if not failed else ', '.join(failed)} | "
                f"{len(lm.get('label_collisions', []))} | {len(lm.get('labels_outside_their_room', []))} | "
                f"{rec['seconds']:.1f} |")
    return "\n".join(out)


def site_facts(design: dict) -> dict:
    """The site-drawing facts, read straight off the saved payload (`DemoPlan` draws exactly
    these): the parcel rectangle, the garden regions, the parking bays, how far the entrance walk
    runs, how many footprint wings, and how many room-to-room boundaries are OPEN rather than a
    door — the open-plan semantics the drawing shows as one continuous space."""
    plot = design["plot"]
    return {
        "plot_m": f"{plot['width_m']:.1f} x {plot['depth_m']:.1f}",
        "plot_area_m2": round(plot["width_m"] * plot["depth_m"], 1),
        "garden_rects": len(design.get("garden", [])),
        "parking": len(design.get("parking", [])),
        "walk_depth_m": design["entrance_walk"]["depth_m"],
        "wings": len(design.get("footprints") or [design["footprint"]]),
        "open_interfaces": len(design.get("open_interfaces", [])),
        "cased_openings": sum(1 for d in design["doors"] if d.get("kind") == "CASED_OPENING"),
    }


def site_table(rows: list[dict], designs_dir: str) -> str:
    """What each engine does with the PERSON'S SITE — the facts the site drawing is made of."""
    out = ["| brief | engine | parcel drawn (m) | garden regions | parking bays | entrance walk (m) | "
           "footprint wings | open interfaces | cased openings |",
           "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        for engine in ("production", "brain"):
            rec = r[engine]
            if rec.get("outcome") != "PLAN":
                continue
            path = os.path.join(designs_dir, rec["render"])
            if not os.path.exists(path):
                continue
            f = site_facts(json.load(open(path)))
            out.append(f"| {r['brief']} | {engine} | {f['plot_m']} | {f['garden_rects']} | "
                       f"{f['parking']} | {f['walk_depth_m']:.1f} | {f['wings']} | "
                       f"{f['open_interfaces']} | {f['cased_openings']} |")
    return "\n".join(out)


def main(argv: list[str]) -> None:
    data_dir = argv[0]
    rows = json.load(open(os.path.join(data_dir, "results.json")))
    lm_path = os.path.join(data_dir, "label-metrics.json")
    labels = json.load(open(lm_path)) if os.path.exists(lm_path) else {}
    print("## Corpus\n")
    print(corpus_table(rows))
    print("\n## Objective facts\n")
    print(facts_table(rows, labels))
    print("\n## The site, as each engine hands it to the drawing\n")
    print(site_table(rows, os.path.join(data_dir, "designs")))


if __name__ == "__main__":
    main(sys.argv[1:])
