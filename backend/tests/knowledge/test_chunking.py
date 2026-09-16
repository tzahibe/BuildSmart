from app.knowledge.chunking import chunk_markdown


def test_preserves_heading_hierarchy():
    text = "# Top\n\nIntro.\n\n## Sub A\n\nBody A.\n\n### Sub A detail\n\nDeep body.\n\n## Sub B\n\nBody B.\n"
    chunks = chunk_markdown("doc.md", text)
    heading_paths = [c.heading_path for c in chunks]
    assert "Top" in heading_paths
    assert "Top > Sub A" in heading_paths
    assert "Top > Sub A > Sub A detail" in heading_paths
    assert "Top > Sub B" in heading_paths


def test_no_blind_char_splitting_mid_paragraph():
    long_paragraph = "word " * 500  # long enough to exceed DEFAULT_MAX_CHARS if split blindly
    text = f"# Heading\n\n{long_paragraph}\n\n## Next\n\nshort\n"
    chunks = chunk_markdown("doc.md", text)
    # the long paragraph must appear whole in some chunk, never truncated mid-word
    assert any(long_paragraph.strip() == c.text.strip() for c in chunks)


def test_oversized_section_splits_on_paragraph_boundaries():
    paragraphs = [f"Paragraph {i}. " * 40 for i in range(10)]
    text = "# Heading\n\n" + "\n\n".join(paragraphs)
    chunks = chunk_markdown("doc.md", text, max_chars=300)
    assert len(chunks) > 1
    for c in chunks:
        assert c.heading_path == "Heading"
        # every chunk boundary falls on a paragraph boundary, never mid-sentence
        assert c.text.strip().endswith(".") or c.text.strip() == ""


def test_chunk_ids_are_stable_across_runs():
    text = "# H\n\nbody\n"
    a = chunk_markdown("doc.md", text)
    b = chunk_markdown("doc.md", text)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
