import pytest

from app.knowledge import doc_status


@pytest.fixture(autouse=True)
def _isolate_doc_status_table():
    """Every test gets a clean doc_status cache; the real table is restored afterward so other
    test modules (and a real `knowledge` CLI run later in the same process) aren't affected."""
    doc_status.reload_table()
    yield
    doc_status.reload_table()


@pytest.fixture
def tmp_docs(tmp_path):
    """A tiny docs/ tree with a mix of statuses, for indexer/retrieval tests."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CURRENT_APPROACH.md").write_text(
        "# Current Approach\n\n"
        "The VerticalCore stair seat is the accepted approach for multi-level circulation.\n\n"
        "## Details\n\nSee C22 seam validation for the geometry contract.\n"
    )
    (docs / "OLD_APPROACH.md").write_text(
        "# Old Approach\n\n"
        "SUPERSEDED. The old stair placement heuristic is no longer used.\n"
    )
    (docs / "UNRELATED.md").write_text(
        "# Unrelated Topic\n\nThis document is about parking lot striping paint colors.\n"
    )
    return tmp_path
