"""Issue #134 — Stage 2 (B/2) AC-6: every Stage 2 flag defaults off, and no production caller
imports `app.vertical_slice.stage2` at all — the frozen 432-context regression corpus is
unaffected by construction, regardless of these flags' values (the corpus itself is proven
byte-identical separately by `tests/regression_corpus/test_frozen_regression_corpus.py`).
"""
from __future__ import annotations

import ast
import os

from app.vertical_slice.stage2 import contract, pipeline, realizer

_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "app")


def test_every_stage2_flag_defaults_off():
    assert contract.STAGE2_CONTRACT_ENABLED is False
    assert realizer.STAGE2_REALIZER_ENABLED is False
    assert pipeline.STAGE2_END_TO_END_ENABLED is False


def _imports_stage2(path: str) -> bool:
    with open(path, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=path)
        except SyntaxError:
            return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("app.vertical_slice.stage2") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("app.vertical_slice.stage2") or (
                node.level > 0 and "stage2" in module):
                return True
    return False


def test_no_production_module_imports_stage2():
    """Every `.py` file under `app/` OUTSIDE `app/vertical_slice/stage2/` itself must not import
    it — the same static proof `contract.py`'s own module docstring claims ("no existing caller
    imports this package"), now checked, not merely asserted in a comment."""
    offenders = []
    for root, _dirs, files in os.walk(_APP_DIR):
        if os.path.normpath(root).endswith(os.path.normpath("vertical_slice/stage2")):
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            if _imports_stage2(path):
                offenders.append(path)
    assert offenders == [], f"production modules importing stage2: {offenders}"
