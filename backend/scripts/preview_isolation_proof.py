"""MEASURE whether a brain preview request can degrade production (Issue #246, ROOT #211).

Repeats #226's protocol — production latency (median and worst) at 0, 2 and 4 concurrent brain
requests, then 0 again — under three process shapes, each started from scratch as real uvicorn
processes on loopback and driven over real HTTP:

    single    ONE process serves production and the brain, and the preview limit is lifted to 4 (a
              harness-only patch of `preview_limit.MEASURED_MAX_CONCURRENCY`). This is #226's
              condition and is the CONTROL: if it does not reproduce the degradation the other two
              shapes prove nothing.
    two       production is one process, the brain a SECOND one (the shipped shape: the flag is off
              in production). The limit is lifted to 4 in the preview process only, so the rows for
              2 and 4 are the WORST CASE of the isolation, not the shipped configuration.
    enforced  the same two processes with the shipped limit (1): 4 simultaneous brain requests,
              one runs, three are refused with the typed 429.

Alongside production's latency it samples `GET /health` on the process that serves production: the
existing liveness probe, to show whether it moves when users wait (it does not — #226 B.4).

    uv run python scripts/preview_isolation_proof.py single   --out <file.json>
    uv run python scripts/preview_isolation_proof.py two      --out <file.json>
    uv run python scripts/preview_isolation_proof.py enforced --out <file.json>

Run it on an otherwise idle machine, alone (`measure-on-a-quiet-machine`): contention changes which
plan the brain shows and how long everything takes. The load average before and after is recorded.
`serve` is the internal mode that starts one server process; it is not for people.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parent.parent
#: #226's briefs and order (`perf_load.py`): the brain requests take them in turn, production is B09
BRAIN_BRIEFS = ["B11", "B16", "B19", "B09", "B02", "B06", "B08", "B20"]
PRODUCTION = "/projects/B09/design/demo"
BRAIN_PATH = "/projects/{brief}/design/demo?engine=brain"
TOKEN = "isolation-proof-token"
QUIET_SAMPLES = 8


# ------------------------------------------------------------------------------ the server side

def serve(port: int, data: str, ceiling: int | None) -> None:
    sys.path.insert(0, str(BACKEND))
    import uvicorn

    from app.demo import preview_limit
    from app.projects.repository import JsonFileProjectRepository
    from app.projects.routes import base_routes

    base_routes.repository = JsonFileProjectRepository(Path(data))
    if ceiling is not None:
        # HARNESS ONLY: lifts the measured ceiling inside this process so the unbounded condition
        # can be measured. The shipped code never does this, and no environment variable can.
        preview_limit.MEASURED_MAX_CONCURRENCY = ceiling
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def _start(port: int, data: Path, *, preview: bool, ceiling: int | None) -> subprocess.Popen:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BRAIN_PREVIEW_")}
    if preview:
        env["BRAIN_PREVIEW_ENABLED"] = "1"
        env["BRAIN_PREVIEW_TOKEN"] = TOKEN
        if ceiling is not None:
            env["BRAIN_PREVIEW_MAX_CONCURRENCY"] = str(ceiling)
    command = [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(port),
               "--data", str(data)]
    if preview and ceiling is not None:
        command += ["--ceiling", str(ceiling)]
    process = subprocess.Popen(command, cwd=BACKEND, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                return process
        except httpx.HTTPError:
            time.sleep(0.5)
    process.kill()
    raise RuntimeError(f"server on port {port} did not come up")


# ------------------------------------------------------------------------------ the client side

def _timed_post(base: str, path: str, headers: dict | None = None) -> dict:
    started = time.perf_counter()
    try:
        response = httpx.post(base + path, headers=headers, timeout=900)
        status = response.status_code
        body = response.json() if status != 200 else None
    except httpx.HTTPError as error:
        status, body = -1, {"error": type(error).__name__}
    return {"started": started, "seconds": round(time.perf_counter() - started, 3),
            "status": status,
            "code": (body or {}).get("detail", {}).get("code") if isinstance(body, dict)
            and isinstance(body.get("detail"), dict) else None}


def _timed_get(base: str, path: str) -> dict:
    started = time.perf_counter()
    try:
        response = httpx.get(base + path, timeout=120)
        sample = {"started": started, "seconds": round(time.perf_counter() - started, 4),
                  "status": response.status_code}
        return sample
    except httpx.HTTPError as error:
        return {"started": started, "seconds": round(time.perf_counter() - started, 4),
                "status": -1, "error": type(error).__name__}


def _summary(samples: list[dict]) -> dict:
    seconds = [s["seconds"] for s in samples]
    if not seconds:
        return {"n": 0}
    return {"n": len(seconds), "median": round(statistics.median(seconds), 3),
            "worst": round(max(seconds), 3), "best": round(min(seconds), 3),
            "non_200": sum(1 for s in samples if s["status"] != 200)}


def _phase(production_base: str, preview_base: str, n_brain: int) -> dict:
    """Fire `n_brain` brain requests at once; sample production's latency and `/health` meanwhile."""
    brain_results: list[dict] = []
    production: list[dict] = []
    liveness: list[dict] = []
    stop = threading.Event()

    def fire(index: int) -> None:
        path = BRAIN_PATH.format(brief=BRAIN_BRIEFS[index % len(BRAIN_BRIEFS)])
        brain_results.append(_timed_post(preview_base, path, {"X-Brain-Preview-Token": TOKEN}))

    def sample_production() -> None:
        while not stop.is_set():
            production.append(_timed_post(production_base, PRODUCTION))

    def sample_liveness() -> None:
        while not stop.is_set():
            liveness.append(_timed_get(production_base, "/health"))
            time.sleep(1.0)

    samplers = [threading.Thread(target=sample_production), threading.Thread(target=sample_liveness)]
    firing = [threading.Thread(target=fire, args=(i,)) for i in range(n_brain)]
    started = time.perf_counter()
    for thread in samplers:
        thread.start()
    time.sleep(1.0)                      # a request or two of the unloaded state, then the load
    load_started = time.perf_counter()
    for thread in firing:
        thread.start()
    if n_brain:
        for thread in firing:
            thread.join()
    else:
        time.sleep(QUIET_SAMPLES * 1.8)  # the quiet phases sample for about as many requests
    stop.set()
    for thread in samplers:
        thread.join()
    # Only requests that STARTED after the load did count as "under load", so a quiet request
    # cannot dilute the median. Requests still running when the load ended are kept: dropping them
    # could only make the result look better.
    under_load = [s for s in production if s["started"] >= load_started] if n_brain else production
    liveness = [s for s in liveness if s["started"] >= load_started] if n_brain else liveness
    return {
        "concurrent_brain_requests": n_brain,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "production": _summary(under_load),
        "health": _summary(liveness),
        "brain": [{"seconds": r["seconds"], "status": r["status"], "code": r["code"]}
                  for r in brain_results],
    }


def measure(shape: str, out: Path) -> None:
    sys.path.insert(0, str(BACKEND))
    from tests.vertical_slice.test_brain import _brief
    from tests.vertical_slice.test_hub_guard import _project
    from app.projects.repository import JsonFileProjectRepository

    # the same eight projects #226's scratch server built, in a file of their own: the measurement
    # never reads or writes `app/data/projects.json`
    work = Path(tempfile.mkdtemp(prefix="preview-isolation-"))
    data = work / "projects.json"
    repository = JsonFileProjectRepository(data)
    for brief_id in sorted(set(BRAIN_BRIEFS)):
        b = _brief(brief_id)
        repository.replace(brief_id, _project(dict(
            bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
            open_plan=b.open_plan, built_area_m2=b.built_area_m2,
            footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
            plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8)))

    servers: list[subprocess.Popen] = []
    load_before = os.getloadavg()
    try:
        if shape == "single":
            servers.append(_start(8101, data, preview=True, ceiling=4))
            production_base = preview_base = "http://127.0.0.1:8101"
            ladder = [0, 2, 4, 0]
        else:
            servers.append(_start(8102, data, preview=False, ceiling=None))
            ceiling = 4 if shape == "two" else None
            servers.append(_start(8103, data, preview=True, ceiling=ceiling))
            production_base, preview_base = "http://127.0.0.1:8102", "http://127.0.0.1:8103"
            ladder = [0, 2, 4, 0] if shape == "two" else [0, 4, 0]
        # warm both processes: the first request pays imports that no later one does
        _timed_post(production_base, PRODUCTION)
        phases = [_phase(production_base, preview_base, n) for n in ladder]
        flag_off = _timed_post(production_base, BRAIN_PATH.format(brief="B09"),
                               {"X-Brain-Preview-Token": TOKEN})
    finally:
        for server in servers:
            server.terminate()
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill()
    result = {
        "shape": shape, "cpu_count": os.cpu_count(),
        "load_average_before": [round(x, 2) for x in load_before],
        "load_average_after": [round(x, 2) for x in os.getloadavg()],
        "production_refuses_brain": flag_off if shape != "single" else None,
        "phases": phases,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for phase in phases:
        print(shape, phase["concurrent_brain_requests"], "brain ->", phase["production"],
              "| /health", phase["health"],
              "| brain", [(b["status"], b["seconds"]) for b in phase["brain"]])


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode")
    for name in ("single", "two", "enforced"):
        sub.add_parser(name)
    for name in ("single", "two", "enforced"):
        sub.choices[name].add_argument("--out", type=Path, required=True)
    srv = sub.add_parser("serve")
    srv.add_argument("--port", type=int, required=True)
    srv.add_argument("--data", required=True)
    srv.add_argument("--ceiling", type=int, default=None)
    args = parser.parse_args()
    if args.mode == "serve":
        serve(args.port, args.data, args.ceiling)
    elif args.mode in ("single", "two", "enforced"):
        measure(args.mode, args.out)
    else:
        parser.error("choose single, two or enforced")


if __name__ == "__main__":
    main()
