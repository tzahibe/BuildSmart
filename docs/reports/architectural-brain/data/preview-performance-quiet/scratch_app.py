"""#226 Part B.3/B.4 — a SCRATCH server for the concurrency and failure-isolation measurements.

The real `app.main:app`, on a port of its own, with one thing replaced: `_project_or_404` reads an
in-memory dict of the eight briefs instead of `app/data/projects.json`, so the measurement never
writes to the repository and never goes near the live server. Everything that decides latency —
the router, the threadpool, the pipeline, HiGHS — is the production object.
"""
import sys

ROOT = "/Users/mymacbook/projects/sddproject-brain"
sys.path.insert(0, f"{ROOT}/backend")

from fastapi import HTTPException
from app.main import app                                    # noqa: F401  (uvicorn imports `app`)
from app.demo import router as demo_router
from tests.vertical_slice.test_brain import _brief
from tests.vertical_slice.test_hub_guard import _project

BRIEFS = ["B02", "B06", "B08", "B09", "B11", "B16", "B19", "B20"]


def project_for(bid):
    b = _brief(bid)
    return _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                         open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                         footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                         plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))


PROJECTS = {bid: project_for(bid) for bid in BRIEFS}


def _in_memory_project_or_404(project_id: str):
    project = PROJECTS.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


demo_router._project_or_404 = _in_memory_project_or_404
