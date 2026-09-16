"""Markdown-structural chunking: split by heading hierarchy first, then by paragraph within an
oversized section. Never blindly split every N characters — a chunk always ends at a heading or a
blank-line paragraph boundary, so a decision/invariant is never cut mid-sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")

#: Sections larger than this are further split by paragraph, so retrieval doesn't have to swallow
#: an entire long section to answer a narrow question — but a chunk is still never smaller than a
#: full paragraph.
DEFAULT_MAX_CHARS = 1800


@dataclass(frozen=True)
class Chunk:
    doc_path: str
    heading_path: str
    ordinal: int
    text: str

    @property
    def chunk_id(self) -> str:
        return f"{self.doc_path}::{self.heading_path}::{self.ordinal}"


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading_path, body) pairs, in document order. Text before the first heading gets an empty
    heading_path."""
    stack: list[str] = []
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            stack = stack[: level - 1] + [title]
            sections.append((" > ".join(stack), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections if "\n".join(lines).strip()]


def _split_by_paragraph(body: str, max_chars: int) -> list[str]:
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    groups: list[str] = []
    current = ""
    for p in paragraphs:
        candidate = f"{current}\n\n{p}" if current else p
        if len(candidate) > max_chars and current:
            groups.append(current)
            current = p
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups or [body]


def chunk_markdown(doc_path: str, text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 0
    for heading_path, body in _sections(text):
        pieces = _split_by_paragraph(body, max_chars) if len(body) > max_chars else [body]
        for piece in pieces:
            chunks.append(Chunk(doc_path=doc_path, heading_path=heading_path, ordinal=ordinal, text=piece))
            ordinal += 1
    return chunks
