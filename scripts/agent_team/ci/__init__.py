"""CI gate scripts run inside GitHub Actions (see .github/workflows/agent-*.yml).

Each module is a pure `evaluate(...)` plus a thin `main()` that reads the Actions environment,
writes a JSON report + a step summary, and exits non-zero on failure. Deterministic only: no
model is consulted in any gate here.
"""
