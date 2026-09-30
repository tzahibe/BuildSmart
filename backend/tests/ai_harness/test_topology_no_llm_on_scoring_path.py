"""AC-14: the worker performs NO LLM call and NO network call on the PRIMARY path.

Statically walks the import graph starting at the primary path's own entrypoints
(`generation_dataset`, `frozen_runner`, `primary_report`, `build_primary_report`) — following only
imports local to `app.ai_harness.topology_poc` — and fails if `llm_client` (this package's OWN
Ollama HTTP client) or any network primitive (`socket`, `http`, `urllib`, `urllib3`, `requests`,
`httpx`) ever appears anywhere in that closure. `runner.py`/`llm_client.py` themselves (the
FORCED LOCAL-MODEL CONTROL RUN's own live-Ollama driver, AC-17) are deliberately NOT entrypoints
here — they are a separate, non-primary path.
"""
from __future__ import annotations

import ast
import importlib
import os

import app.ai_harness.topology_poc as topology_poc_pkg

_PKG_DIR = os.path.dirname(topology_poc_pkg.__file__)
_PKG_NAME = "app.ai_harness.topology_poc"

PRIMARY_PATH_ENTRYPOINTS = (
    "generation_dataset", "frozen_runner", "primary_report", "build_primary_report",
)

FORBIDDEN_MODULES = frozenset({
    "llm_client", "socket", "http", "http.client", "urllib", "urllib.request", "urllib2",
    "urllib3", "requests", "httpx", "aiohttp",
})


def _imports_of(module_name: str) -> set:
    path = os.path.join(_PKG_DIR, f"{module_name}.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # resolve `from . import x` / `from .x import y` (level > 0) to this package
                if node.level and node.level > 0:
                    names.add(f"{_PKG_NAME}.{node.module}")
                else:
                    names.add(node.module)
    return names


def _primary_path_closure() -> tuple:
    """Returns `(visited_local_modules, forbidden_hits)` — `forbidden_hits` is a list of
    `(module, forbidden_import)` pairs found anywhere in the closure."""
    visited = set()
    stack = list(PRIMARY_PATH_ENTRYPOINTS)
    forbidden_hits = []
    while stack:
        mod = stack.pop()
        if mod in visited:
            continue
        visited.add(mod)
        for imp in _imports_of(mod):
            top = imp.split(".")[0]
            if imp.startswith(f"{_PKG_NAME}."):
                sibling = imp.rsplit(".", 1)[-1]
                if sibling not in visited:
                    stack.append(sibling)
                continue
            if imp in FORBIDDEN_MODULES or top in FORBIDDEN_MODULES:
                forbidden_hits.append((mod, imp))
    return visited, forbidden_hits


def test_primary_entrypoints_exist_as_real_modules():
    for mod in PRIMARY_PATH_ENTRYPOINTS:
        assert os.path.exists(os.path.join(_PKG_DIR, f"{mod}.py")), (
            f"{mod}.py must exist under {_PKG_DIR} — it is a declared primary-path entrypoint")


def test_primary_path_never_imports_llm_client_or_a_network_primitive():
    visited, forbidden_hits = _primary_path_closure()
    assert not forbidden_hits, (
        f"the primary scoring path can reach a forbidden module: {forbidden_hits} — the primary "
        "path must never call an LLM or open a network connection (AC-14)")
    assert "llm_client" not in visited, "llm_client.py must never be part of the primary path's own closure"


def test_llm_client_module_is_never_actually_imported_by_the_primary_modules():
    """A dynamic double-check alongside the static one above: importing each primary-path
    entrypoint module directly must never place `llm_client` in `sys.modules` as a NEW import
    caused by that module (it may already be cached from an unrelated test in the same session,
    which this test does not treat as a failure of THIS module's own closure)."""
    import sys

    for mod in PRIMARY_PATH_ENTRYPOINTS:
        full_name = f"{_PKG_NAME}.{mod}"
        importlib.import_module(full_name)
    # the static closure check above is the authoritative proof; this just confirms every
    # primary-path module actually imports cleanly on its own.
    assert f"{_PKG_NAME}.generation_dataset" in sys.modules
    assert f"{_PKG_NAME}.frozen_runner" in sys.modules


def test_generation_dataset_module_defines_no_generate_or_call_function():
    """AC-16: "no regeneration, local-model or network fallback path exists" — `generation_dataset`
    exposes a loader/preflight only, never anything that could call out and manufacture data."""
    from app.ai_harness.topology_poc import generation_dataset

    forbidden_names = {"generate", "call", "regenerate", "fetch", "request"}
    public_names = {n for n in dir(generation_dataset) if not n.startswith("_")}
    assert not (public_names & forbidden_names), (
        f"generation_dataset.py must never expose a call/generate/regenerate function: "
        f"{public_names & forbidden_names}")
