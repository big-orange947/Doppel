"""Lossless, query-independent text spans; no storage or inference policy."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class TextSpanConfig:
    """Lengths/offsets count Python Unicode code points, not bytes or tokens."""

    max_chars: int = 1200
    overlap_chars: int = 160

    def __post_init__(self) -> None:
        if (
            type(self.max_chars) is not int
            or self.max_chars < 1
            or type(self.overlap_chars) is not int
            or not 0 <= self.overlap_chars < self.max_chars
        ):
            raise ValueError(
                "positive span size and smaller nonnegative overlap required"
            )


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


def iter_text_spans(
    text: str, config: TextSpanConfig | None = None
) -> Iterator[TextSpan]:
    """Cover the original without stripping, rewriting, or query/gold access.

    Prefer the last whitespace boundary in the latter half of a window. Fall
    back to exact character windows for unbroken text, including CJK and code.
    Half-open offsets always refer to the caller's unchanged original string.
    """
    if not isinstance(text, str):
        raise TypeError("source text must be a string")
    config = config or TextSpanConfig()
    start = 0
    while start < len(text):
        end = min(start + config.max_chars, len(text))
        if end < len(text):
            lower = start + max(1, config.max_chars // 2)
            boundaries = list(re.finditer(r"\s+", text[lower:end]))
            if boundaries:
                end = lower + boundaries[-1].end()
        yield TextSpan(start, end, text[start:end])
        if end == len(text):
            break
        start = max(start + 1, end - config.overlap_chars)
