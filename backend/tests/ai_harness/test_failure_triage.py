from tests.ai_harness.cache import ResponseCache
from tests.ai_harness.failure_triage import (
    FailingTest,
    parse_pytest_short_summary,
    triage_failures,
)


def test_parse_pytest_short_summary_extracts_names_and_errors():
    output = (
        "FAILED tests/knowledge/test_x.py::test_one - AssertionError: expected 1, got 2\n"
        "FAILED tests/knowledge/test_y.py::test_two[case-a] - ValueError: bad input\n"
        "2 failed in 0.10s\n"
    )
    failures = parse_pytest_short_summary(output)
    assert [f.name for f in failures] == [
        "tests/knowledge/test_x.py::test_one",
        "tests/knowledge/test_y.py::test_two[case-a]",
    ]
    assert failures[0].error_summary == "AssertionError: expected 1, got 2"


def test_no_failures_never_calls_the_model():
    assert triage_failures([]) is None


def test_triage_failures_returns_structured_report(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_TEST_PROVIDER", "mock")
    monkeypatch.setenv("AI_TEST_LOCAL_FAST_MODEL", "mock-v1")
    import tests.ai_harness.failure_triage as ft

    monkeypatch.setattr(ft, "ResponseCache", lambda: ResponseCache(cache_dir=str(tmp_path)))

    failures = [FailingTest(name="tests/x.py::test_a", error_summary="AssertionError: boom")]
    report = triage_failures(failures)

    assert report is not None
    assert report.provider == "mock"
    assert report.cache_hit is False
    # the mock provider returns {"mock_digest": "..."} — extract_json parses it, and absent keys
    # default to empty lists rather than raising, proving the API tolerates a non-matching schema.
    assert report.failure_groups == []
    assert report.knowledge_topics == []


def test_identical_failure_report_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_TEST_PROVIDER", "mock")
    monkeypatch.setenv("AI_TEST_LOCAL_FAST_MODEL", "mock-v1")
    import tests.ai_harness.failure_triage as ft

    shared_cache = ResponseCache(cache_dir=str(tmp_path))
    monkeypatch.setattr(ft, "ResponseCache", lambda: shared_cache)

    failures = [FailingTest(name="tests/x.py::test_a", error_summary="AssertionError: boom")]
    first = triage_failures(failures)
    second = triage_failures(failures)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.raw_text == second.raw_text


def test_triage_never_produces_a_pass_fail_verdict_field():
    """API-shape guard: TriageReport has no field that could be mistaken for merge/release
    evidence or a pass/fail verdict — it only ever summarizes/groups already-known failures."""
    import dataclasses

    from tests.ai_harness.failure_triage import TriageReport

    field_names = {f.name for f in dataclasses.fields(TriageReport)}
    assert not field_names & {"passed", "verdict", "acceptable", "should_merge"}
