"""Approximate token counting — a whitespace/char heuristic, not tied to any specific tokenizer.
Good enough to respect a context-pack budget; not a substitute for a real tokenizer if exact
billing/token accounting is ever needed."""

from __future__ import annotations


def approx_token_count(text: str) -> int:
    # ~4 chars/token is the commonly-cited rule of thumb for English technical prose; documented
    # as approximate rather than chasing exact parity with any one model's tokenizer.
    return max(1, len(text) // 4)
