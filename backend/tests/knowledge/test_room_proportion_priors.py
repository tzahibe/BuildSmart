"""Issue #140, AC-2: the scanner fails loudly (raises, and the CLI exits non-zero) on an empty
measurement — never a silent zero that could pass for a real answer."""
import json
import os

import pytest

from app.knowledge import room_proportion_priors as rpp


def test_raises_on_missing_corpus_dir(tmp_path):
    with pytest.raises(rpp.EmptyCorpusError):
        rpp.load_room_samples(str(tmp_path / "does-not-exist"))


def test_raises_on_empty_corpus_dir(tmp_path):
    """Zero `*.json` files under the corpus dir — the exact "scans zero plans" case."""
    with pytest.raises(rpp.EmptyCorpusError):
        rpp.load_room_samples(str(tmp_path))


def test_raises_when_every_plan_is_synthetic(tmp_path):
    """A corpus dir that has files, but every one is excluded — an empty RESULT, not an empty
    directory, and the exact defect this Issue names: "a sweep ... looked like a real answer"."""
    _write_plan(tmp_path / "synthetic.json", provenance={"source_dataset": "SYNTHETIC"})
    with pytest.raises(rpp.EmptyCorpusError):
        rpp.load_room_samples(str(tmp_path))


def test_raises_when_real_plans_yield_zero_usable_rooms(tmp_path):
    """Real (non-synthetic) plans present, but no room has enough fields to sample — still an
    empty result, and still raised rather than silently returning zero rows."""
    _write_plan(tmp_path / "0.json", rooms=[{"type": "LIVING", "area_m2": 20.0}])  # no width/depth
    with pytest.raises(rpp.EmptyCorpusError):
        rpp.load_room_samples(str(tmp_path))


def test_cli_exits_non_zero_on_empty_corpus(tmp_path, capsys):
    exit_code = rpp.main(["--corpus-dir", str(tmp_path)])
    assert exit_code != 0
    assert "room_proportion_priors" in capsys.readouterr().err


def test_cli_exits_zero_on_a_real_minimal_corpus(tmp_path):
    """The mirror case: a genuinely usable corpus does NOT raise, and the CLI succeeds — proves
    the empty-source tests above are failing for the right reason, not because the fixture helper
    itself is broken."""
    _write_plan(tmp_path / "0.json", footprint_area_m2=100.0, bedroom_count=3,
               rooms=[{"type": "LIVING", "area_m2": 20.0, "width_m": 4.0, "depth_m": 5.0}])
    exit_code = rpp.main(["--corpus-dir", str(tmp_path)])
    assert exit_code == 0


def test_load_priors_table_raises_when_artifact_missing(tmp_path):
    with pytest.raises(rpp.EmptyCorpusError):
        rpp.load_priors_table(str(tmp_path / "missing.json"))


def test_load_priors_table_raises_when_artifact_has_zero_rows(tmp_path):
    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({
        "corpus_dir": "x", "plans_scanned": 0, "plans_excluded_synthetic": 0,
        "edges": {"house_size_terciles": None, "bedroom_count_terciles": None,
                  "bedroom_count_median": 0}, "rows": [],
    }))
    with pytest.raises(rpp.EmptyCorpusError):
        rpp.load_priors_table(str(empty_path))


def test_real_minimal_corpus_computes_expected_row(tmp_path):
    """A sanity check on the measurement itself, not just the failure path: two plans, one role,
    one bucket combination -> exactly one row with the expected median/sample_count."""
    _write_plan(tmp_path / "0.json", footprint_area_m2=100.0, bedroom_count=3,
               rooms=[{"type": "BEDROOM", "area_m2": 10.0, "width_m": 3.0, "depth_m": 3.333}])
    _write_plan(tmp_path / "1.json", footprint_area_m2=100.0, bedroom_count=3,
               rooms=[{"type": "BEDROOM", "area_m2": 12.0, "width_m": 3.0, "depth_m": 4.0}])
    table = rpp.build_priors_table(str(tmp_path))
    assert table.plans_scanned == 2
    assert len(table.rows) == 1
    row = table.rows[0]
    assert row.role == "BEDROOM"
    assert row.sample_count == 2
    assert row.median_area_m2 == pytest.approx(11.0)


def _write_plan(path, *, provenance=None, footprint_area_m2=None, bedroom_count=None, rooms=None):
    room_type_counts = {"BEDROOM": bedroom_count} if bedroom_count is not None else {}
    plan_reference = {
        "plan_id": os.path.basename(str(path)),
        "provenance": provenance or {"source_dataset": "ResPlan"},
        "derived": {"footprint_area_m2": footprint_area_m2, "room_type_counts": room_type_counts},
        "rooms": rooms or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"plan_reference": plan_reference}, f)
