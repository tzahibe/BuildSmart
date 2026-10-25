"""#226 Part B.2 — peak RSS and CPU time for ONE request in a FRESH process.

`ru_maxrss` is a high-water mark for the life of the process, so the figure is only honest when
the process serves exactly one request. Run twice, once per engine.
usage: perf_one_request.py <production|brain> <brief>"""
import json, resource, sys, time

ROOT = "/Users/mymacbook/projects/sddproject-brain"
sys.path.insert(0, f"{ROOT}/backend")
ENGINE, BRIEF = sys.argv[1], sys.argv[2]

from tests.vertical_slice.test_brain import _brief
from tests.vertical_slice.test_hub_guard import _project
from app.demo import service as svc


def u():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return round(r.ru_maxrss / (1024 * 1024), 1), round(r.ru_utime + r.ru_stime, 2)


b = _brief(BRIEF)
project = _project(dict(bedrooms=b.bedrooms, wet_rooms=b.wet_rooms, safe_room=b.safe_room,
                        open_plan=b.open_plan, built_area_m2=b.built_area_m2,
                        footprint_width_m=b.footprint_width_m, footprint_depth_m=b.footprint_depth_m,
                        plot_width_m=b.footprint_width_m + 8, plot_depth_m=b.footprint_depth_m + 8))
rss_import, cpu_import = u()
t = time.monotonic()
res = svc.generate_demo_design(project, brain=(ENGINE == "brain"))
el = time.monotonic() - t
rss, cpu = u()
print(json.dumps(dict(engine=ENGINE, brief=BRIEF, seconds=round(el, 2),
                      rss_after_import_mb=rss_import, peak_rss_mb=rss,
                      rss_of_the_request_mb=round(rss - rss_import, 1),
                      cpu_s=round(cpu - cpu_import, 2),
                      cpu_over_wall=round((cpu - cpu_import) / el, 3),
                      plans=1 + len(res.alternatives))))
