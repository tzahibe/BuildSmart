"""#226 Part B.3/B.4 — concurrency and failure isolation against the scratch server.

B.3  N = 1, 2, 4, 8 simultaneous `?engine=brain` requests: wall latency per request, whether the
     30 s brain budget still holds, and the server's RSS while they run.
B.4  production latency (no `engine` parameter at all, the path real traffic takes) measured QUIET
     and then again WHILE brain requests are in flight. The endpoint is a `def`, so Starlette runs
     it in the anyio threadpool — whether that is enough depends on whether HiGHS holds the GIL,
     which is what this measures rather than infers.

usage: perf_load.py <base-url> <server-pid> <out.json>
"""
import json, statistics, subprocess, sys, threading, time, urllib.error, urllib.request

BASE, PID, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BRAIN_BRIEFS = ["B11", "B16", "B19", "B09", "B02", "B06", "B08", "B20"]
PROD_BRIEF = "B09"


def request(brief, engine=None, timeout=300):
    url = f"{BASE}/projects/{brief}/design/demo" + (f"?engine={engine}" if engine else "")
    req = urllib.request.Request(url, data=b"", method="POST",
                                 headers={"Content-Type": "application/json"})
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(); code = r.status
    except urllib.error.HTTPError as e:
        body = e.read(); code = e.code
    except Exception as e:                                     # noqa: BLE001
        return dict(brief=brief, engine=engine or "production", seconds=round(time.monotonic() - t, 2),
                    code=None, error=f"{type(e).__name__}: {e}")
    return dict(brief=brief, engine=engine or "production", seconds=round(time.monotonic() - t, 2),
                code=code, bytes=len(body),
                error=None if code == 200 else json.loads(body or b"{}").get("detail", "")if body[:1] == b"{" else None)


def rss_mb():
    out = subprocess.run(["ps", "-o", "rss=", "-p", PID], capture_output=True, text=True).stdout.strip()
    return round(int(out) / 1024, 1) if out else None


def sampler(stop, samples):
    while not stop.is_set():
        v = rss_mb()
        if v:
            samples.append(v)
        stop.wait(1.0)


def parallel(n, engine):
    """n requests fired at once; RSS sampled for the duration."""
    results = [None] * n
    stop = threading.Event(); samples = []
    s = threading.Thread(target=sampler, args=(stop, samples), daemon=True); s.start()

    def one(i):
        results[i] = request(BRAIN_BRIEFS[i % len(BRAIN_BRIEFS)], engine)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    t = time.monotonic()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    wall = time.monotonic() - t
    stop.set(); s.join(timeout=2)
    return dict(n=n, engine=engine, wall_s=round(wall, 2), rss_peak_mb=max(samples) if samples else None,
                rss_start_mb=samples[0] if samples else None, results=results)


report = {}

print("--- warm-up (one production request, discarded)", flush=True)
request(PROD_BRIEF)
report["rss_after_warmup_mb"] = rss_mb()

print("--- B.4a production baseline, machine quiet: 6 sequential requests", flush=True)
quiet = [request(PROD_BRIEF) for _ in range(6)]
report["production_quiet"] = quiet
qs = [r["seconds"] for r in quiet]
print(f"    production quiet: median {statistics.median(qs):.2f} s  max {max(qs):.2f} s  {qs}", flush=True)

print("--- B.3 brain concurrency", flush=True)
report["brain_concurrency"] = []
for n in (1, 2, 4, 8):
    r = parallel(n, "brain")
    report["brain_concurrency"].append(r)
    secs = [x["seconds"] for x in r["results"]]
    codes = sorted({x["code"] for x in r["results"]})
    print(f"    N={n}: wall {r['wall_s']:.1f} s  per-request min {min(secs):.1f} / median "
          f"{statistics.median(secs):.1f} / max {max(secs):.1f} s  codes {codes}  "
          f"rss {r['rss_start_mb']} -> {r['rss_peak_mb']} MB", flush=True)
    time.sleep(3)

print("--- B.4b production WHILE 2 brain requests are in flight", flush=True)
for load in (2, 4):
    probes = []
    stop = threading.Event()

    def probe():
        while not stop.is_set():
            probes.append(request(PROD_BRIEF))

    brain_done = []

    def brain(i):
        brain_done.append(request(BRAIN_BRIEFS[i], "brain"))

    p = threading.Thread(target=probe, daemon=True)
    bs = [threading.Thread(target=brain, args=(i,)) for i in range(load)]
    for th in bs:
        th.start()
    time.sleep(1.0)
    p.start()
    for th in bs:
        th.join()
    stop.set(); p.join(timeout=400)
    ps = [r["seconds"] for r in probes]
    report[f"production_under_brain_load_{load}"] = dict(probes=probes, brain=brain_done)
    if ps:
        print(f"    under {load} brain requests: production median {statistics.median(ps):.2f} s  "
              f"max {max(ps):.2f} s  n={len(ps)}  {[round(x, 1) for x in ps]}", flush=True)

print("--- B.4c production baseline again, machine quiet (drift check)", flush=True)
after = [request(PROD_BRIEF) for _ in range(6)]
report["production_quiet_after"] = after
asec = [r["seconds"] for r in after]
print(f"    production quiet after: median {statistics.median(asec):.2f} s  max {max(asec):.2f} s", flush=True)
report["rss_final_mb"] = rss_mb()

json.dump(report, open(OUT, "w"), indent=1)
print("DONE", flush=True)
