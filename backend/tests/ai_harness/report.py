"""AI-test observability log — mirrors app/observability/failure_log.py's conventions (atomic
write, path-overridable, never raises, summary()) for a different kind of record: what an AI test
actually cost and whether it agreed with the golden expectation.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent / "reports" / "ai_test_log.json"
MAX_ENTRIES = 2000

_lock = threading.Lock()
_path: Path = DEFAULT_PATH


def set_path(path: Path | str) -> None:
    global _path
    _path = Path(path)


def read_all() -> list[dict[str, Any]]:
    try:
        with _path.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_all(entries: list[dict[str, Any]]) -> None:
    _path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=_path.parent, delete=False, suffix=".tmp")
    try:
        with handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
        os.replace(handle.name, _path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def record(*, case_id: str, topic: str, provider: str, model: str, latency_ms: float,
           tokens_in: int | None, tokens_out: int | None, cache_hit: bool, passed: bool,
           field_results: dict[str, bool], invalid_json: bool) -> None:
    """Append one AI-test result. Never raises."""
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "case_id": case_id, "topic": topic, "provider": provider, "model": model,
        "latency_ms": latency_ms, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cache_hit": cache_hit, "passed": passed, "field_results": field_results,
        "invalid_json": invalid_json,
    }
    try:
        with _lock:
            entries = read_all()
            entries.append(entry)
            _write_all(entries[-MAX_ENTRIES:])
    except Exception:  # noqa: BLE001 - a failing report log must stay silent
        pass


def clear() -> None:
    with _lock:
        _write_all([])


def summary() -> dict[str, Any]:
    entries = read_all()
    by_provider: dict[str, dict[str, int]] = {}
    for e in entries:
        p = e.get("provider", "?")
        bucket = by_provider.setdefault(p, {"total": 0, "passed": 0, "invalid_json": 0, "cache_hits": 0})
        bucket["total"] += 1
        bucket["passed"] += int(e.get("passed", False))
        bucket["invalid_json"] += int(e.get("invalid_json", False))
        bucket["cache_hits"] += int(e.get("cache_hit", False))
    return {"total": len(entries), "by_provider": by_provider, "path": str(_path)}
