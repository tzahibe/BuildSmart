"""Write real `DemoDesign` payloads for the E1 comparison, for the PRODUCT renderer to draw.

Production and E1 come from the same entry point the product uses
(`app.demo.service.generate_demo_design`), so the JSON below is exactly what the browser receives.

    PYTHONPATH=backend python -m app.ai_harness.e1_orientation.dump_designs <out-dir>
"""
from __future__ import annotations

import json
import os
import sys

from app.ai_harness.e1_orientation.measure import _project_for
from app.ai_harness.topology_poc import briefs as briefs_mod
from app.demo import service as svc

#: The three briefs the owner asked to see, plus the one that is the actual comparison.
BRIEFS = ("B19", "B06", "B16", "B09")


def main(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for bid in BRIEFS:
        b = {x.brief_id: x for x in briefs_mod.select_briefs()}[bid]
        project = _project_for(b)
        production = svc.generate_demo_design(project)
        with open(os.path.join(out_dir, f"{bid}__production.json"), "w") as fh:
            json.dump(production.design.model_dump(mode="json"), fh)
        print(f"{bid}: production written", flush=True)
        try:
            e1 = svc.generate_demo_design(project, rear_band_preview=True)
        except svc.DemoGenerationError as exc:
            print(f"{bid}: E1 REFUSED {exc.code} — {exc.detail[:120]}", flush=True)
            continue
        with open(os.path.join(out_dir, f"{bid}__e1-rear-band.json"), "w") as fh:
            json.dump(e1.design.model_dump(mode="json"), fh)
        print(f"{bid}: E1 written", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "designs")
