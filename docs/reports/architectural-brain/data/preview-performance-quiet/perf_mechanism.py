"""#226 Part B.3/B.4 — the mechanism, and the cost to the PLAN rather than to the clock.

(a) Is the serialization the GIL or the cores? If four concurrent brain requests pin ~100 % of one
    core the solver holds the GIL; if they reach ~400 % they are genuinely parallel and the machine
    (10 cores here) is the limit. Sampled from `ps -o %cpu` on the server process.
(b) The brain's budget is WALL-CLOCK, so contention does not only add seconds: fewer candidates get
    sized inside the same 30 s and the product shows a DIFFERENT plan. Measured by asking for the
    same brief alone and then again beside three other brain requests, and comparing the primary
    plan's family and its notes.

usage: perf_mechanism.py <base-url> <server-pid> <out.json>"""
import json, statistics, subprocess, sys, threading, time, urllib.request

BASE, PID, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
SUBJECT = "B08"                     # 807 MILP solves when it runs alone: sensitive to the budget
OTHERS = ["B11", "B16", "B19"]


def post(brief, engine=None, timeout=400):
    url = f"{BASE}/projects/{brief}/design/demo" + (f"?engine={engine}" if engine else "")
    req = urllib.request.Request(url, data=b"", method="POST",
                                 headers={"Content-Type": "application/json"})
    t = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return round(time.monotonic() - t, 2), body


def primary(body):
    p = body["plan"]
    return dict(family=p.get("family"), gross=p.get("gross_area_m2"), rooms=len(p.get("rooms", [])),
                notes=[n for n in (p.get("notes") or [])][:6],
                alternatives=len(body.get("alternatives", [])))


def cpu_sampler(stop, out):
    while not stop.is_set():
        v = subprocess.run(["ps", "-o", "%cpu=", "-p", PID], capture_output=True, text=True).stdout.strip()
        if v:
            out.append(float(v))
        stop.wait(0.5)


report = {}
print("--- alone", flush=True)
stop = threading.Event(); cpu = []
s = threading.Thread(target=cpu_sampler, args=(stop, cpu), daemon=True); s.start()
sec, body = post(SUBJECT, "brain")
stop.set(); s.join(timeout=2)
report["alone"] = dict(seconds=sec, cpu_pct_max=max(cpu) if cpu else None,
                       cpu_pct_median=round(statistics.median(cpu), 1) if cpu else None,
                       primary=primary(body))
print(f"    {SUBJECT} alone: {sec} s, server CPU median {report['alone']['cpu_pct_median']} % "
      f"max {report['alone']['cpu_pct_max']} %", flush=True)
print(f"    primary {report['alone']['primary']['family']}  gross {report['alone']['primary']['gross']}  "
      f"rooms {report['alone']['primary']['rooms']}  alternatives {report['alone']['primary']['alternatives']}", flush=True)
for n in report["alone"]["primary"]["notes"]:
    print(f"      {n[:140]}", flush=True)

time.sleep(3)
print("--- beside three other brain requests", flush=True)
stop = threading.Event(); cpu = []
s = threading.Thread(target=cpu_sampler, args=(stop, cpu), daemon=True); s.start()
holder = {}


def other(b):
    try:
        post(b, "brain")
    except Exception:                                            # noqa: BLE001
        pass


def subject():
    holder["r"] = post(SUBJECT, "brain")


ts = [threading.Thread(target=other, args=(b,)) for b in OTHERS]
for th in ts:
    th.start()
time.sleep(0.5)
sj = threading.Thread(target=subject); sj.start(); sj.join()
for th in ts:
    th.join()
stop.set(); s.join(timeout=2)
sec, body = holder["r"]
report["under_load"] = dict(seconds=sec, cpu_pct_max=max(cpu) if cpu else None,
                            cpu_pct_median=round(statistics.median(cpu), 1) if cpu else None,
                            primary=primary(body))
print(f"    {SUBJECT} under 3 others: {sec} s, server CPU median {report['under_load']['cpu_pct_median']} % "
      f"max {report['under_load']['cpu_pct_max']} %", flush=True)
print(f"    primary {report['under_load']['primary']['family']}  gross {report['under_load']['primary']['gross']}  "
      f"rooms {report['under_load']['primary']['rooms']}  alternatives {report['under_load']['primary']['alternatives']}", flush=True)
for n in report["under_load"]["primary"]["notes"]:
    print(f"      {n[:140]}", flush=True)

same = report["alone"]["primary"]["family"] == report["under_load"]["primary"]["family"]
report["same_primary_family"] = same
print(f"\n    SAME PRIMARY FAMILY: {same}", flush=True)
json.dump(report, open(OUT, "w"), indent=1)
print("DONE")
