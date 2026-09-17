"""The authoritative doc-status table (`doc_status.json`), not an LLM guess and not trusted from a
report's own prose — six entries were explicitly corrected against `git log`/`git branch
--contains` after an earlier pass wrongly inferred status from doc wording alone (see the file's
own `_comment` and each corrected entry's `confidence`/evidence fields).

Any doc not in the table gets a conservative heuristic fallback: `ACTIVE_RESEARCH` /
`capability_status=UNKNOWN` / `confidence=low` — never assumed current, never assumed dead.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

_TABLE_PATH = os.path.join(os.path.dirname(__file__), "doc_status.json")

#: Bounded reranking multipliers — see retrieval.py's scoring pipeline for why this range is
#: deliberately narrow (it must be able to break a near-tie but never flip a large relevance gap).
_STATUS_WEIGHT = {
    "IMPLEMENTED_MERGED": 1.15,
    "IMPLEMENTED": 1.15,
    "APPROVED": 1.10,
    "ACTIVE_RESEARCH": 1.00,
    "HISTORICAL": 0.90,
    "SUPERSEDED": 0.75,
    "PARTIAL": 1.00,
    "NOT_IMPLEMENTED": 0.95,
    "UNKNOWN": 0.95,
    "N/A": 1.00,
}

_DECISION_BONUS = {
    "APPROVED_FOR_IMPLEMENTATION": 1.05,
}

#: A floor, not a multiplier — canonical Wiki/PROJECT_STATE sources are guaranteed at least this
#: reranking weight regardless of their doc_status, so a semantically-similar old investigation
#: can win on raw relevance but never simply outrank the canonical current-truth source on status
#: alone. Still bounded (1.20 vs the 0.75 SUPERSEDED floor is a ~1.6x spread) — it can break a
#: near-tie, never flip a real relevance gap; see retrieval.py's scoring pipeline and
#: test_retrieval_priority.py's worked-example invariants.
_SOURCE_TYPE_MIN_WEIGHT = {
    "WIKI_CANONICAL": 1.20,
    "PROJECT_STATE": 1.20,
}

#: Path-pattern based default when a doc_status.json entry doesn't set source_type explicitly —
#: existing entries (authored before source_type existed) still get a sensible classification
#: without needing every one hand-edited.
_SPEC_PATH_RE = re.compile(r"^specs/")
_WIKI_PATH_RE = re.compile(r"^docs/wiki/")


def _default_source_type(path: str, doc_status: str) -> str:
    if _WIKI_PATH_RE.match(path):
        return "WIKI_CANONICAL"
    if path == "docs/PROJECT_STATE.md":
        return "PROJECT_STATE"
    if _SPEC_PATH_RE.match(path):
        return "SPEC"
    if doc_status in ("SUPERSEDED", "HISTORICAL"):
        return "HISTORICAL"
    if doc_status == "ACTIVE_RESEARCH":
        return "INVESTIGATION"
    return "IMPLEMENTATION_REPORT"

_CONTENT_HINTS = [
    (re.compile(r"\bSUPERSEDED\b", re.I), "SUPERSEDED"),
    (re.compile(r"STATUS\s*=\s*DONE", re.I), "IMPLEMENTED"),
    (re.compile(r"\bREJECTED\b", re.I), "HISTORICAL"),
]


@dataclass(frozen=True)
class DocStatusEntry:
    path: str
    topic: str = "general"
    tags: tuple[str, ...] = ()
    doc_status: str = "ACTIVE_RESEARCH"
    capability_status: str = "UNKNOWN"
    decision_status: str = "N/A"
    commit: str | None = None
    branch: str | None = None
    merged_to_main: bool | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    confidence: str = "low"
    last_verified_at: str | None = None
    #: WIKI_CANONICAL | PROJECT_STATE | IMPLEMENTATION_REPORT | INVESTIGATION | SPEC | HISTORICAL.
    #: Derived from path/doc_status when not set explicitly — see `_default_source_type`.
    source_type: str = ""

    @property
    def status_weight(self) -> float:
        weight = _STATUS_WEIGHT.get(self.doc_status, 1.0)
        # capability_status can further inform ranking when it's stronger evidence than doc_status
        # alone (e.g. an ACTIVE_RESEARCH doc whose capability already merged).
        if self.capability_status in ("IMPLEMENTED_MERGED",) and self.doc_status == "ACTIVE_RESEARCH":
            weight = max(weight, _STATUS_WEIGHT["IMPLEMENTED_MERGED"])
        weight *= _DECISION_BONUS.get(self.decision_status, 1.0)
        # A floor, not a multiplier — see _SOURCE_TYPE_MIN_WEIGHT's docstring above.
        weight = max(weight, _SOURCE_TYPE_MIN_WEIGHT.get(self.source_type, 0.0))
        return weight


def _load_table() -> dict:
    with open(_TABLE_PATH, encoding="utf-8") as f:
        return json.load(f)["docs"]


_TABLE_CACHE: dict | None = None


def _table() -> dict:
    global _TABLE_CACHE
    if _TABLE_CACHE is None:
        _TABLE_CACHE = _load_table()
    return _TABLE_CACHE


def reload_table() -> None:
    """Test seam — clears the module-level cache so a test can point at a different table."""
    global _TABLE_CACHE
    _TABLE_CACHE = None


def set_table_for_testing(table: dict) -> None:
    """Test seam — injects a table directly (bypassing the JSON file) for controlled scoring
    tests. Mirrors `app.observability.failure_log`'s `set_path()` convention."""
    global _TABLE_CACHE
    _TABLE_CACHE = table


def status_for(doc_path: str, *, content: str | None = None) -> DocStatusEntry:
    entry = _table().get(doc_path)
    if entry is not None:
        doc_status = entry.get("doc_status", "ACTIVE_RESEARCH")
        source_type = entry.get("source_type") or _default_source_type(doc_path, doc_status)
        return DocStatusEntry(path=doc_path, tags=tuple(entry.get("tags", ())), source_type=source_type, **{
            k: v for k, v in entry.items() if k not in ("tags", "source_type")
        })

    doc_status, confidence = "ACTIVE_RESEARCH", "low"
    if content:
        for pattern, hinted_status in _CONTENT_HINTS:
            if pattern.search(content):
                doc_status, confidence = hinted_status, "low"
                break
    source_type = _default_source_type(doc_path, doc_status)
    return DocStatusEntry(path=doc_path, doc_status=doc_status, capability_status="UNKNOWN",
                           confidence=confidence, source_type=source_type)


def stale_entries(*, max_age_note: str = "review manually") -> list[str]:
    """`knowledge doctor` support: entries whose confidence is not high, worth a human recheck."""
    return [path for path, entry in _table().items() if entry.get("confidence") != "high"]
