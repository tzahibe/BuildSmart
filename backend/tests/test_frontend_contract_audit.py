"""AC-4 (Issue #34): the frontend renders only backend-provided numbers.

Every width/depth/area a person sees on the demo plan is read straight off
`app.demo.contract.RoomOut`/`DemoDesign` — never recomputed client-side. That is exactly the
guarantee that would have masked Issue #34's bug from a code reviewer skimming the frontend: a
local `width * depth` would have silently matched whatever the backend sent, correct or not. This
greps the live demo-contract consumers (`ReviewPage.tsx`, the plan renderer and its label layout)
for that pattern, so a FUTURE change reintroducing local area/dimension math is caught here rather
than by eyeballing a diff.

Deliberately does not audit `frontend/src/design/ArchitecturalFloorPlan.tsx`/`geometricDesign.ts`/
`SketchSvg.tsx` — those render a different, older solver's contract entirely
(`app.geometry.geometric_design`), out of this Issue's scope.
"""
from __future__ import annotations

import re
from pathlib import Path

_AUDITED_FILES = (
    "frontend/src/design/ReviewPage.tsx",
    "frontend/src/design/DemoPlan.tsx",
    "frontend/src/design/DemoWorkspace.tsx",
    "frontend/src/design/demoRoomLabel.ts",
)

#: A width-ish identifier multiplied by a depth/height-ish one, in either order — the shape of the
#: historical bug (`ArchitecturalFloorPlan.tsx`'s `maxX * maxDepth`), not a literal `* height`
#: string match, since real code never spells it that plainly.
_AREA_MATH = re.compile(
    r"\b[\w.]*(?:width|Width)[\w.]*\s*\*\s*[\w.]*(?:depth|height|Depth|Height)[\w.]*\b"
    r"|\b[\w.]*(?:depth|height|Depth|Height)[\w.]*\s*\*\s*[\w.]*(?:width|Width)[\w.]*\b"
)


def _repo_root() -> Path:
    # backend/tests/test_frontend_contract_audit.py -> backend -> repo root
    return Path(__file__).resolve().parents[2]


def test_frontend_does_not_recompute_areas():
    root = _repo_root()
    offenders: list[str] = []
    for rel in _AUDITED_FILES:
        path = root / rel
        assert path.exists(), f"expected audited file to exist: {rel}"
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _AREA_MATH.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, "local area/dimension math found in the frontend:\n" + "\n".join(offenders)
