#!/usr/bin/env bash
# The orchestrator's own deterministic test suite, runnable as a `cmd:` verification target and by CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec uv run --project "$ROOT/scripts/agent_team" --quiet pytest -q "$ROOT/scripts/agent_team/tests" "$@"
