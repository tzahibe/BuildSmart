"""Reference plan collection V1 (Issue #30): schema, index, rights policy.

Validates docs/architecture_reference/references/index.json against its own schema.json, checks
the minimum entry count and footprint-family coverage, and enforces the rights invariant: an
entry whose rights are metadata-only must never have copied files on disk.
"""
from __future__ import annotations

import json
import pathlib

import jsonschema
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
REFERENCES_DIR = REPO_ROOT / "docs" / "architecture_reference" / "references"
SCHEMA_PATH = REFERENCES_DIR / "schema.json"
INDEX_PATH = REFERENCES_DIR / "index.json"

MIN_ENTRIES = 30
REQUIRED_FOOTPRINT_FAMILIES = {"rectangle", "wide-rectangle", "narrow-deep", "L", "irregular"}


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_index() -> dict:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def test_index_validates_and_has_at_least_thirty_entries() -> None:
    schema = _load_schema()
    index = _load_index()

    jsonschema.validate(instance=index, schema=schema)

    entries = index["entries"]
    assert len(entries) >= MIN_ENTRIES, (
        f"expected at least {MIN_ENTRIES} entries, got {len(entries)}"
    )

    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids)), "duplicate entry ids in index.json"


def test_footprint_families_are_covered() -> None:
    index = _load_index()
    families_present = {entry["footprint_family"] for entry in index["entries"]}

    missing = REQUIRED_FOOTPRINT_FAMILIES - families_present
    assert not missing, f"footprint families missing from index.json: {sorted(missing)}"


def test_no_files_for_metadata_only_entries() -> None:
    index = _load_index()

    for entry in index["entries"]:
        entry_dir = REFERENCES_DIR / entry["id"]
        if entry["rights"] == "metadata-only":
            assert entry["files"] == [], (
                f"entry {entry['id']!r} is rights=metadata-only but lists files: {entry['files']}"
            )
            assert not entry_dir.exists(), (
                f"entry {entry['id']!r} is rights=metadata-only but "
                f"references/{entry['id']}/ exists on disk"
            )
        else:
            for relative_path in entry["files"]:
                file_path = entry_dir / relative_path
                assert file_path.is_file(), (
                    f"entry {entry['id']!r} (rights={entry['rights']}) lists file "
                    f"{relative_path!r} but it does not exist at {file_path}"
                )


@pytest.mark.parametrize("path", [SCHEMA_PATH, INDEX_PATH, REFERENCES_DIR / "README.md"])
def test_expected_files_exist(path: pathlib.Path) -> None:
    assert path.exists(), f"expected {path} to exist"
