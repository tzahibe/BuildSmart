"""Reference plan collection V1 (Issue #30) and annotations (Issue #31): schema, index, rights
policy, and per-entry "why this plan works" annotations.

Validates docs/architecture_reference/references/index.json against its own schema.json, checks
the minimum entry count and footprint-family coverage, and enforces the rights invariant: an
entry whose rights are metadata-only must never have copied plan files on disk (an annotation.md
is not a copied plan file and is the one exception). Also validates that every entry has an
annotation.md with a rubric-tagged "why this plan works" section and at least one trade-off.
"""
from __future__ import annotations

import json
import pathlib
import re

import jsonschema
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
REFERENCES_DIR = REPO_ROOT / "docs" / "architecture_reference" / "references"
SCHEMA_PATH = REFERENCES_DIR / "schema.json"
INDEX_PATH = REFERENCES_DIR / "index.json"
RUBRIC_PATH = REPO_ROOT / "docs" / "architecture_reference" / "quality_rubric.md"

MIN_ENTRIES = 30
REQUIRED_FOOTPRINT_FAMILIES = {"rectangle", "wide-rectangle", "narrow-deep", "L", "irregular"}
MIN_WHY_BULLETS = 3
MAX_WHY_BULLETS = 8
RUBRIC_TAG_RE = re.compile(r"\[([A-O])\]\s*$")


def _section_lines(markdown: str, heading: str) -> list[str]:
    """Return the non-empty lines under a `## heading` up to the next `## ` heading or EOF."""
    lines = markdown.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    assert start is not None, f"missing {heading!r} section"

    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            collected.append(line.rstrip())
    return collected


def _rubric_sections() -> set[str]:
    letters = set()
    for line in RUBRIC_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^## ([A-O])\. ", line)
        if match:
            letters.add(match.group(1))
    return letters


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
    """metadata-only entries may never carry a copied plan file (see rights policy in README.md).

    An annotation.md is original documentation, not a copied plan file, so its directory is the
    one thing a metadata-only entry's references/<id>/ is allowed to contain (Issue #31).
    """
    index = _load_index()

    for entry in index["entries"]:
        entry_dir = REFERENCES_DIR / entry["id"]
        if entry["rights"] == "metadata-only":
            assert entry["files"] == [], (
                f"entry {entry['id']!r} is rights=metadata-only but lists files: {entry['files']}"
            )
            if entry_dir.exists():
                on_disk = {p.name for p in entry_dir.iterdir()}
                unexpected = on_disk - {"annotation.md"}
                assert not unexpected, (
                    f"entry {entry['id']!r} is rights=metadata-only but "
                    f"references/{entry['id']}/ contains copied files: {sorted(unexpected)}"
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


def test_every_entry_has_an_annotation_with_why_it_works() -> None:
    """AC-1 (Issue #31): every index entry has annotation: true and an annotation.md whose

    '## Why this plan works' section carries 3-8 bullets, each tagged with a rubric section.
    """
    index = _load_index()
    rubric_sections = _rubric_sections()
    assert rubric_sections, "could not parse any rubric sections (A-O) from quality_rubric.md"

    for entry in index["entries"]:
        assert entry.get("annotation") is True, (
            f"entry {entry['id']!r} is missing annotation: true in index.json"
        )

        annotation_path = REFERENCES_DIR / entry["id"] / "annotation.md"
        assert annotation_path.is_file(), (
            f"entry {entry['id']!r} has annotation: true but "
            f"references/{entry['id']}/annotation.md does not exist"
        )

        markdown = annotation_path.read_text(encoding="utf-8")
        bullets = [
            line for line in _section_lines(markdown, "## Why this plan works")
            if line.lstrip().startswith("- ")
        ]
        assert MIN_WHY_BULLETS <= len(bullets) <= MAX_WHY_BULLETS, (
            f"entry {entry['id']!r} annotation.md 'Why this plan works' has {len(bullets)} "
            f"bullets, expected {MIN_WHY_BULLETS}-{MAX_WHY_BULLETS}"
        )

        for bullet in bullets:
            match = RUBRIC_TAG_RE.search(bullet)
            assert match, (
                f"entry {entry['id']!r} annotation.md bullet does not end with a rubric tag "
                f"like '[A]': {bullet!r}"
            )
            assert match.group(1) in rubric_sections, (
                f"entry {entry['id']!r} annotation.md bullet tags rubric section "
                f"{match.group(1)!r}, which is not a section in quality_rubric.md"
            )


def test_every_annotation_lists_a_trade_off() -> None:
    """AC-2 (Issue #31): every annotation.md's '## Trade-offs' section has real content."""
    index = _load_index()

    for entry in index["entries"]:
        annotation_path = REFERENCES_DIR / entry["id"] / "annotation.md"
        markdown = annotation_path.read_text(encoding="utf-8")
        trade_off_lines = _section_lines(markdown, "## Trade-offs")
        assert trade_off_lines, (
            f"entry {entry['id']!r} annotation.md 'Trade-offs' section has no content"
        )
