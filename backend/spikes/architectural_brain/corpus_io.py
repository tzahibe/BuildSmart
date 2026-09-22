"""Loads a directory of ``{"plan_reference": ..., "architectural_pattern": ...}`` JSON files —
the schema both ``build_corpus.py`` (the 199-plan POC corpus) and ``build_fixtures.py`` (the
20-plan committed test fixture set) already write — into ``CorpusEntry`` pairs for
``retrieval.retrieve``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from spikes.architectural_brain.patterns import ArchitecturalPattern
from spikes.architectural_brain.plan_reference import PlanReference


@dataclass(frozen=True)
class CorpusEntry:
    plan_reference: PlanReference
    pattern: ArchitecturalPattern


def load_corpus_dir(dir_path: str) -> list[CorpusEntry]:
    """Every ``*.json`` file directly in ``dir_path``, sorted by filename for a deterministic
    order (retrieval's own sort is a stable tie-break on top of this, but a stable input order
    keeps the whole pipeline reproducible independent of filesystem directory-listing order)."""
    entries: list[CorpusEntry] = []
    for name in sorted(os.listdir(dir_path)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(dir_path, name)) as f:
            raw = json.load(f)
        ref = PlanReference.from_dict(raw["plan_reference"])
        pattern = ArchitecturalPattern.from_dict(raw["architectural_pattern"])
        entries.append(CorpusEntry(plan_reference=ref, pattern=pattern))
    return entries
