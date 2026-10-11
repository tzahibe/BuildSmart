"""Builds docs/reports/142d-exact-cell-sizing/{results.md, results.json, certificates.md} from the run outputs."""
import collections
import json
import os
import re
import sys

W = sys.argv[1]; S = sys.argv[2]
D = os.path.join(W, "docs/reports/142d-exact-cell-sizing")
os.makedirs(D, exist_ok=True)

prod = json.load(open(f"{S}/w142d/results_production.json"))
try:
    prod += json.load(open(f"{S}/w142d/results_production_B18.json"))
except FileNotFoundError:
    pass
corr = json.load(open(f"{S}/w142d/results_corrected.json"))
try:
    netgate = json.load(open(f"{S}/w142d/results_corrected_netgate.json"))
except FileNotFoundError:
    netgate = []
import re as _re
def _fix(res):
    for r in res:
        for o in r["outcomes"]:
            o["validator_failed_checks"] = sorted({t for t in _re.findall(r"\b(C\d+)\b", " ".join(o["validator_failed_checks"]) + " " + (o.get("refusal_detail") or ""))}) if o.get("refusal") == "VALIDATION_FAILED" else []
            if o.get("access_lost") and o["access_lost"] and isinstance(o["access_lost"][0], list):
                o["access_lost"] = ["".join(x) for x in o["access_lost"]]
        if r.get("first_success") and r["first_success"].get("access_lost") and isinstance(r["first_success"]["access_lost"][0] if r["first_success"]["access_lost"] else "", list):
            r["first_success"]["access_lost"] = ["".join(x) for x in r["first_success"]["access_lost"]]
        # dominant rejections: recompute validator keys from fixed check lists
        val = collections.Counter("VALIDATION_FAILED " + "+".join(o["validator_failed_checks"]) for o in r["outcomes"] if o.get("refusal") == "VALIDATION_FAILED")
        if val:
            r["dominant_rejections"]["VALIDATORS"] = dict(val.most_common(6))
for _res in (prod, corr, netgate):
    _fix(_res)
by_bid = {r["brief_id"]: r for r in prod}
cby = {r["brief_id"]: r for r in corr}
order = sorted(by_bid)

STAGES = ("EMBEDDING", "SIZING", "REALIZATION", "VALIDATORS")


KEEP = ("index", "n_rows", "n_cols", "oracle_status", "oracle_method", "envelope_m", "stage_reached", "refusal",
        "validator_failed_checks", "spatial", "access", "flags")


def trim(r):
    out = {k: v for k, v in r.items() if k != "outcomes"}
    out["outcomes"] = [{k: o.get(k) for k in KEEP} for o in r["outcomes"]]
    return out


json.dump({"production": [trim(r) for r in prod], "corrected": [trim(r) for r in corr], "corrected_netgate": [trim(r) for r in netgate]},
          open(f"{D}/results.json", "w"), separators=(",", ":"))

L = []
L.append("# #142D — Exact per-cell band sizing: stage counts (generated)")
L.append("")
L.append("Pipeline per witness: `exact topology witness -> exact per-cell sizing (oracle) -> existing realization -> unchanged validators`. "
         "Counts are over ALL witnesses examined, never only the best one. 'sizing' = the realizer's own `_build_grid_wing` accepted the injected sizing "
         "(its area/short-side re-checks after 5 cm rounding); 'realization' = reached `validate`; 'validators' = unchanged `validate` PASS.")
L.append("")
for label, res in (("PRODUCTION semantics (oracle enforces exactly `_build_grid_wing`: gross area, short side + 0.3 m)", prod),
                   ("CORRECTED semantics counterfactual A (oracle enforces NET area/short side with the real insets, plus max aspect; the production GROSS gate left in place)", corr),
                   ("CORRECTED semantics counterfactual B (as A, with `_build_grid_wing`'s area gate made NET-consistent for the experiment only; validators unchanged)", netgate)):
    if not res:
        continue
    L.append(f"## {label}")
    L.append("")
    L.append("| brief | n | m | family complete | witnesses examined | oracle FEASIBLE / INFEASIBLE / UNKNOWN | sizing pass | realization pass | validator pass | category | dominant rejections |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    bids = sorted({r["brief_id"] for r in res})
    rb = {r["brief_id"]: r for r in res}
    tot = collections.Counter()
    for bid in bids:
        r = rb[bid]; o = r["oracle"]
        dom = "; ".join(f"{st}: " + ", ".join(f"{k} ({v})" for k, v in d.items()) for st, d in r["dominant_rejections"].items())
        cat = r["category"]
        if cat == "BAND_GEOMETRY_LIMIT" and not r["family_complete"]:
            cat = "UNKNOWN_WITHIN_SEARCH_BOUND"
        if res is corr and cat.startswith("SIZING_MODEL_LIMIT (feasible per oracle"):
            cat = "REJECTED_BY_PRODUCTION_GROSS_GATE (net-feasible sizing, `_build_grid_wing` AREA_INFEASIBLE)"
        if bid == "B18":
            cat = cat if cat in ("PASS", "DOWNSTREAM_CONSTRAINT") else "UNKNOWN_WITHIN_SEARCH_BOUND (3,000 of >100,000 layouts)"
        L.append(f"| {bid} | {r['n']} | {r['m']} | {'yes' if r['family_complete'] else 'no'} | {r['witnesses_examined']} | "
                 f"{o['FEASIBLE']} / {o['INFEASIBLE']} / {o['UNKNOWN']} | {r['sizing_pass']} | {r['realization_pass']} | "
                 f"{r['validator_pass']} | {cat} | {dom[:260]} |")
        tot["briefs"] += 1
        tot["oracle_feasible_briefs"] += 1 if o["FEASIBLE"] else 0
        tot["sizing_briefs"] += 1 if r["sizing_pass"] else 0
        tot["realization_briefs"] += 1 if r["realization_pass"] else 0
        tot["validator_briefs"] += 1 if r["validator_pass"] else 0
    L.append("")
    L.append(f"**Briefs (denominator {tot['briefs']}):** oracle finds >= 1 feasible sizing for {tot['oracle_feasible_briefs']}; "
             f"realizer sizing accepts >= 1 for {tot['sizing_briefs']}; realization passes for {tot['realization_briefs']}; "
             f"**validators PASS for {tot['validator_briefs']}/{tot['briefs']}**.")
    L.append("")

# §9 counterfactual witness-selection table (production semantics; measurement only)
L.append("## §9 — entrance / access / exposure properties of witnesses (production semantics; measured, not enforced)")
L.append("")
L.append("Flags are topology-level: `entrance_ok` = a HALL/CIRCULATION/LIVING cell in the street band (row 0); "
         "`access_ok` = every room touches >= 1 room it may legally be entered from (`edge_role_pair_allowed`, wet rooms as `_filter_wet_room_access`); "
         "`exposure_ok` = every REQUIRED_EXTERIOR-role room touches the envelope. 'all three' is the counterfactual selection; "
         "its downstream pass rate is reported next to the unselected rate.")
L.append("")
L.append("| brief | witnesses | entrance_ok | access_ok | exposure_ok | all three | sized (all / all-three) | realized (all / all-three) | validators PASS (all / all-three) | top validator failures among sized witnesses |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
for bid in order:
    r = by_bid[bid]; oc = r["outcomes"]
    f = r.get("flags_count", {})
    sel = [o for o in oc if all(o["flags"].get(k) for k in ("entrance_ok", "access_ok", "exposure_ok"))]
    def cnt(lst, stage):
        idx = STAGES.index(stage)
        return sum(1 for o in lst if STAGES.index(o["stage_reached"]) >= idx)
    vf = collections.Counter()
    for o in oc:
        if o["stage_reached"] == "REALIZATION" and o["validator_failed_checks"]:
            vf["+".join(o["validator_failed_checks"])] += 1
    L.append(f"| {bid} | {len(oc)} | {f.get('entrance_ok', 0)} | {f.get('access_ok', 0)} | {f.get('exposure_ok', 0)} | {len(sel)} | "
             f"{cnt(oc, 'SIZING')} / {cnt(sel, 'SIZING')} | {cnt(oc, 'REALIZATION')} / {cnt(sel, 'REALIZATION')} | "
             f"{cnt(oc, 'VALIDATORS')} / {cnt(sel, 'VALIDATORS')} | {', '.join(f'{k} ({v})' for k, v in vf.most_common(4))} |")
L.append("")

# per-brief first success geometry
L.append("## First validator-passing witness per brief (production semantics)")
L.append("")
for bid in order:
    r = by_bid[bid]
    fs = r["first_success"]
    if not fs:
        continue
    L.append(f"### {bid} — witness {fs['index']} ({fs['n_rows']} bands x {fs['n_cols']} cols), envelope {fs['envelope_m']}, "
             f"spatial {fs['spatial']}, access {fs['access']}" + (f", access lost {fs['access_lost']}" if fs['access_lost'] else ""))
    L.append("")
    L.append("| room | x | y | w | d | gross m2 |")
    L.append("|---|---|---|---|---|---|")
    for k, v in fs["rects_m"].items():
        L.append(f"| {k} | {v['x']} | {v['y']} | {v['w']} | {v['d']} | {v['area_m2']} |")
    L.append("")
open(f"{D}/results.md", "w").write("\n".join(L) + "\n")

# certificates for BAND_GEOMETRY_LIMIT briefs
C = ["# B06 / B09 (and other all-infeasible families): per-witness infeasibility certificates", ""]
for bid in order:
    r = by_bid[bid]
    if r["oracle"]["FEASIBLE"]:
        continue
    oc = r["outcomes"]
    C.append(f"## {bid} — {len(oc)} witnesses, family complete = {r['family_complete']}, oracle: "
             f"{r['oracle']['INFEASIBLE']} INFEASIBLE / {r['oracle']['UNKNOWN']} UNKNOWN, by method {r['oracle']['by_method']}")
    C.append("")
    kinds = collections.Counter()
    pat = collections.Counter()
    for o in oc:
        c = o.get("certificate") or ""
        kinds[c.split(":")[0] if c else ("B&B: " + o["oracle_status"])] += 1
        m = re.search(r"band \d+ needs width >= ([\d.]+) m \(sum of its cells' minimum dimensions (\[.*?\])\) but band \d+ allows at most ([\d.]+) m \(each cell's max area / its minimum depth: (\[.*?\])", c)
        if m:
            pat[(m.group(2), m.group(4))] += 1
    C.append(f"- certificate kinds: {dict(kinds)}")
    C.append(f"- most frequent WIDTH contradictions (band needing the width, band capping it): ")
    for (lo, hi), k in pat.most_common(6):
        C.append(f"  - {k}x: needs {lo} vs cap {hi}")
    ex = next((o["certificate"] for o in oc if o.get("certificate")), None)
    if ex:
        C.append(f"- example: {ex}")
    C.append("")
open(f"{D}/certificates.md", "w").write("\n".join(C) + "\n")
print("wrote", D)
