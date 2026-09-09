"""Every failure the application produces, written to one JSON file we can read afterwards.

WHY A FILE AND NOT A LOGGER
---------------------------
Failures here are not stack traces to skim — they are the product telling somebody "no". A refused
plan, an unsupported request, a footprint that does not fit, a crash: each one is a person who did
not reach a drawing. Keeping them in a structured file means we can ask questions of them — which
code fires most, which briefs never reach a sketch, whether a fix actually removed a failure — which
is the whole point of recording them.

TWO KINDS, DELIBERATELY BOTH
----------------------------
`REFUSAL`  — the system worked and said no on purpose (422 with a product code). These are correct
             behaviour, and they are still failures from where the person sits.
`CRASH`    — an unhandled exception. Always a defect.

Keeping them in one file, distinguished by `kind`, is what makes "why did nobody reach a plan
today?" answerable in a single pass.

FORMAT
------
A single JSON array, rewritten atomically on each append. Chosen over JSON Lines because the point
is that a person can open it; at demo volumes the cost is irrelevant. The file is capped at
`MAX_ENTRIES` so it cannot grow without bound, oldest dropped first.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Where the log lives. Overridable so tests never touch the real file.
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "failures.json"

#: Oldest entries are dropped past this. Generous — a demo will not reach it — but bounded.
MAX_ENTRIES = 2000

_lock = threading.Lock()
_path: Path = DEFAULT_PATH


def set_path(path: Path | str) -> None:
    """Point the log somewhere else (tests, a separate environment)."""
    global _path
    _path = Path(path)


def current_path() -> Path:
    return _path


def read_all() -> list[dict[str, Any]]:
    """Everything recorded so far. An unreadable or absent file reads as empty — a broken log must
    never become a second failure on top of the one it was trying to record."""
    try:
        with _path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_all(entries: list[dict[str, Any]]) -> None:
    """Atomic replace, so a crash mid-write cannot leave a truncated file behind."""
    _path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=_path.parent, delete=False, suffix=".tmp")
    try:
        with handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
        os.replace(handle.name, _path)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def record(kind: str, *, code: str, message: str, detail: str = "",
           where: str = "", context: dict[str, Any] | None = None,
           exception: BaseException | None = None) -> dict[str, Any]:
    """Append one failure. Never raises — recording a failure must not create one.

    `context` carries whatever makes the entry actionable later: the project, the brief, the plot
    and footprint dimensions. It is written as-is, so callers decide what is worth keeping.
    """
    entry: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": kind,
        "code": code,
        "message": message,
        "detail": detail,
        "where": where,
        "context": context or {},
    }
    if exception is not None:
        entry["exception"] = {
            "type": type(exception).__name__,
            "str": str(exception),
            "traceback": "".join(traceback.format_exception(
                type(exception), exception, exception.__traceback__))[-4000:],
        }

    try:
        with _lock:
            entries = read_all()
            entries.append(entry)
            _write_all(entries[-MAX_ENTRIES:])
    except Exception:  # noqa: BLE001 - a failing log must stay silent, never mask the real failure
        pass
    return entry


def refusal(code: str, message: str, detail: str = "", *, where: str = "",
            context: dict[str, Any] | None = None) -> None:
    """The system deliberately said no. Correct behaviour, and still somebody without a drawing."""
    record("REFUSAL", code=code, message=message, detail=detail, where=where, context=context)


def crash(exception: BaseException, *, where: str = "",
          context: dict[str, Any] | None = None) -> None:
    """An unhandled exception. Always a defect."""
    record("CRASH", code=type(exception).__name__, message=str(exception),
           where=where, context=context, exception=exception)


def clear() -> None:
    with _lock:
        _write_all([])


def summary() -> dict[str, Any]:
    """Counts by kind and by code, most frequent first — the view worth having at a glance."""
    entries = read_all()
    by_kind: dict[str, int] = {}
    by_code: dict[str, int] = {}
    for entry in entries:
        by_kind[entry.get("kind", "?")] = by_kind.get(entry.get("kind", "?"), 0) + 1
        by_code[entry.get("code", "?")] = by_code.get(entry.get("code", "?"), 0) + 1
    return {
        "total": len(entries),
        "by_kind": by_kind,
        "by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
        "path": str(_path),
    }
