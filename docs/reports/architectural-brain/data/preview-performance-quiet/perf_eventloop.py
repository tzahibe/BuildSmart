"""#226 Part B.4 — is the ASYNCIO EVENT LOOP blocked, or is it the GIL?

The demo endpoint is a plain `def`, so Starlette runs it in the anyio threadpool and the loop
should stay free. That is a claim about code; this measures it. A TRIVIAL route (`/docs`, which
Starlette answers from the loop itself, and `/openapi.json`) is polled while brain requests are in
flight. If the loop were blocked those would stall for tens of seconds. If only the GIL is
contended they answer late but in milliseconds-to-low-seconds, while real work crawls.

usage: perf_eventloop.py <base-url> <out.json>"""
import json, statistics, sys, threading, time, urllib.request

BASE, OUT = sys.argv[1], sys.argv[2]


def get(path, timeout=120):
    t = time.monotonic()
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=timeout) as r:
            r.read()
        return round(time.monotonic() - t, 3)
    except Exception:                                            # noqa: BLE001
        return None


def post(brief, timeout=400):
    req = urllib.request.Request(f"{BASE}/projects/{brief}/design/demo?engine=brain",
                                 data=b"", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


report = {}
for path in ("/docs", "/openapi.json"):
    quiet = [get(path) for _ in range(10)]
    report[f"quiet{path}"] = quiet
    print(f"quiet  {path:16s} median {statistics.median(quiet):.3f} s  max {max(quiet):.3f} s", flush=True)

stop = threading.Event(); samples = {p: [] for p in ("/docs", "/openapi.json")}


def poller():
    while not stop.is_set():
        for p in samples:
            v = get(p)
            if v is not None:
                samples[p].append(v)
        stop.wait(0.3)


ts = [threading.Thread(target=post, args=(b,)) for b in ("B11", "B16", "B19", "B08")]
for th in ts:
    th.start()
time.sleep(1.0)
p = threading.Thread(target=poller, daemon=True); p.start()
for th in ts:
    th.join()
stop.set(); p.join(timeout=5)
for path, vals in samples.items():
    report[f"under_load{path}"] = vals
    print(f"loaded {path:16s} median {statistics.median(vals):.3f} s  max {max(vals):.3f} s  n={len(vals)}", flush=True)
json.dump(report, open(OUT, "w"), indent=1)
print("DONE")
