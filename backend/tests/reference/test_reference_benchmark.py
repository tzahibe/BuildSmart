"""Reference benchmark (Issue #32): `app.vertical_slice.reference_benchmark.benchmark()`.

AC-1/AC-2 replay real briefs through `generate_demo_design`, the same real-pipeline convention
`tests/test_demo_quality.py` already uses for M1-M6 — findings must carry numeric values off
REALIZED geometry, not a synthetic duck-typed fixture. AC-3 exercises the reference-range
citation mechanism directly against two different footprint families.
"""
from __future__ import annotations

import json
import pathlib

from app.demo import service as svc
from app.vertical_slice.reference_benchmark import benchmark, classify_footprint_family
from tests.vertical_slice.test_hub_guard import NARROW_DEEP, WIDE_SQUARE, _project

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
REFERENCES_PATH = REPO_ROOT / "docs" / "architecture_reference" / "references" / "index.json"

MEASURED_SECTIONS = ("A", "B", "C", "H", "K", "L")
NOT_MEASURED_SECTIONS = ("D", "E", "F", "G", "I", "J", "M", "N", "O")


def _references() -> list[dict]:
    return json.loads(REFERENCES_PATH.read_text(encoding="utf-8"))["entries"]


def _canonical_design():
    return svc.generate_demo_design(_project(WIDE_SQUARE)).design


# ------------------------------------------------------------------------------------ AC-1


def test_sections_with_signals_are_measured_on_the_canonical_fixture():
    design = _canonical_design()
    report = benchmark(design, _references())

    assert report.footprint_family == classify_footprint_family(design)
    assert [s.section for s in report.sections] == list("ABCDEFGHIJKLMNO")

    for code in MEASURED_SECTIONS:
        section = report.section(code)
        assert section.measured is True, code
        assert section.value is not None, code
        assert section.finding and section.finding != "not_measured"

    for code in NOT_MEASURED_SECTIONS:
        section = report.section(code)
        assert section.measured is False, code
        assert section.value is None, code
        assert section.finding == "not_measured"

    # Numeric values genuinely come off the realized geometry, not a placeholder.
    b = report.section("B")
    assert b.value["circulation_area_m2"] > 0
    assert 0.0 < b.value["circulation_ratio"] < 1.0
    assert b.value["corridor_length_m"] > 0

    a = report.section("A")
    assert a.value["opens_into_role"] == "HALL"
    assert a.value["is_public_or_circulation"] is True

    h = report.section("H")
    assert h.value["required"] > 0
    assert h.value["windowed_ratio"] is not None

    k = report.section("K")
    assert k.value == 0.0

    consistency = report.section("L")
    assert consistency.value["max_relative_gap"] >= 0.0


# ------------------------------------------------------------------------------------ AC-2


def test_benchmark_reports_circulation_and_entrance_findings():
    references = _references()

    canonical_design = _canonical_design()
    canonical_report = benchmark(canonical_design, references)
    assert "high relative dedicated circulation" not in canonical_report.section("B").finding

    long_corridor_design = svc.generate_demo_design(_project(NARROW_DEEP)).design
    long_corridor_report = benchmark(long_corridor_design, references)
    assert "high relative dedicated circulation" in long_corridor_report.section("B").finding
    # The long-corridor fixture's own B value backs the finding: above the reference band's
    # upper bound, and a materially longer hall than the canonical fixture's.
    b = long_corridor_report.section("B")
    assert b.value["circulation_ratio"] > b.reference_range[1]
    assert b.value["corridor_length_m"] > canonical_report.section("B").value["corridor_length_m"]

    # Entrance findings (section A) are present and meaningful on both.
    for report in (canonical_report, long_corridor_report):
        a = report.section("A")
        assert a.measured and "public/circulation" in a.finding


# ------------------------------------------------------------------------------------ AC-3


def test_reference_range_uses_same_footprint_family():
    references = _references()

    rectangle_design = _canonical_design()
    rectangle_report = benchmark(rectangle_design, references)
    assert rectangle_report.footprint_family == "rectangle"
    rectangle_b = rectangle_report.section("B")
    assert rectangle_b.reference_range == (0.08, 0.14)
    assert rectangle_b.reference_entries, "expected at least one matching rectangle entry"
    assert all(entry_id.startswith("rect-") for entry_id in rectangle_b.reference_entries)

    narrow_deep_design = svc.generate_demo_design(_project(NARROW_DEEP)).design
    narrow_deep_report = benchmark(narrow_deep_design, references)
    assert narrow_deep_report.footprint_family == "narrow-deep"
    narrow_deep_b = narrow_deep_report.section("B")
    assert narrow_deep_b.reference_entries, "expected at least one matching narrow-deep entry"

    # Different footprint families cite different reference entries, and neither list is the
    # generic full index — the citation genuinely keys off `footprint_family`.
    assert set(rectangle_b.reference_entries) != set(narrow_deep_b.reference_entries)
    assert set(rectangle_b.reference_entries).isdisjoint(narrow_deep_b.reference_entries)

    all_entry_ids = {e["id"] for e in references}
    for entry_id in rectangle_b.reference_entries:
        assert entry_id in all_entry_ids

    # The report names the actual entries used, not just a count.
    assert all(entry_id in rectangle_report.section("B").finding
              for entry_id in rectangle_b.reference_entries)
