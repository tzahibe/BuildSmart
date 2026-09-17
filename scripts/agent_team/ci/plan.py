"""Decide which expensive gates a PR needs, from the manifest and the changed paths.

Outputs (GITHUB_OUTPUT): backend_changed, frontend_changed, orchestrator_changed,
regression_required. Regression is required when the manifest says so (regression domains or a
`regression:corpus` target) AND product backend code actually changed — a docs-only PR under a
backend Issue does not burn 10 minutes of corpus replay, and the skip is recorded explicitly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent_team.ci.common import repo_root, run, set_output

BACKEND_PRODUCT = ("backend/app/", "backend/pyproject.toml", "backend/uv.lock", "backend/spikes/failure_log_sweep/")
# Backend code/tests/deps that warrant the fast tier — backend documentation (e.g. backend/README.md)
# alone does not, so a docs-only backend change no longer pays for compileall + import + pytest.
BACKEND_CODE = ("backend/app/", "backend/tests/", "backend/spikes/", "backend/pyproject.toml", "backend/uv.lock")
FRONTEND = ("frontend/",)
ORCHESTRATOR = ("scripts/agent_team/", "scripts/agentctl", ".agent/config.yaml", ".github/workflows/")


def decide(changed: list[str], manifest: dict | None) -> dict:
    backend_product = any(f.startswith(BACKEND_PRODUCT) for f in changed)
    backend_code = any(f.startswith(BACKEND_CODE) for f in changed)
    frontend = any(f.startswith(FRONTEND) for f in changed)
    orchestrator = any(f.startswith(ORCHESTRATOR) for f in changed)
    wants = bool(manifest and manifest.get("regression_required"))
    risk = (manifest or {}).get("risk", "MEDIUM")
    regression = (wants and backend_product) or (risk == "HIGH" and backend_product)
    reason = ("required by contract and backend product code changed" if regression else
              "not required: " + ("contract does not require it" if not wants else "no backend product code changed"))
    return {"backend_changed": backend_code, "frontend_changed": frontend, "orchestrator_changed": orchestrator,
            "regression_required": regression, "regression_reason": reason, "changed_count": len(changed)}


def main() -> int:
    root = repo_root()
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    proc = run(f"git diff --name-only {base}...HEAD", root)
    changed = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    manifest_path = root / ".agent" / "ci" / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    d = decide(changed, manifest)
    for k, v in d.items():
        set_output(k, str(v).lower() if isinstance(v, bool) else str(v))
    print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
