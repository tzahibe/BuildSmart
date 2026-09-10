"""Test-wide fixtures.

The one thing here is a hard separation between the test suite and the PRODUCT's failure log.
"""
from __future__ import annotations

import pytest

from app.observability import failure_log


@pytest.fixture(autouse=True)
def _isolate_failure_log(tmp_path, monkeypatch):
    """Never let a test write into `app/data/failures.json`.

    That file is a diagnostic about REAL people who did not get a drawing. A suite that deliberately
    provokes refusals — a 200 x 3 m plot, six bedrooms, a footprint that cannot fit — was writing
    hundreds of entries into it, and the handful of genuine failures were buried underneath: 280
    entries, of which 5 were a person. A log nobody can read is not a log.
    """
    monkeypatch.setattr(failure_log, "_path", tmp_path / "failures.json")
