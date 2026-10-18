from __future__ import annotations

import pytest

from doppel_memory.passages import TextSpanConfig, iter_text_spans


@pytest.mark.parametrize(
    "text",
    ["", " ", " abc \r\ndef  ", "中文🙂e\u0301" * 30, "x" * 300, "a b c\n" * 100],
)
@pytest.mark.parametrize("size,overlap", [(1, 0), (12, 3), (20, 19)])
def test_lossless_offsets_coverage_bounds_and_progress(text, size, overlap):
    spans = list(iter_text_spans(text, TextSpanConfig(size, overlap)))
    covered = set()
    previous = -1
    for span in spans:
        assert previous < span.start < span.end <= len(text)
        assert span.end - span.start <= size
        assert span.text == text[span.start : span.end]
        covered.update(range(span.start, span.end))
        previous = span.start
    assert covered == set(range(len(text)))
    if spans:
        assert spans[0].start == 0 and spans[-1].end == len(text)


@pytest.mark.parametrize(
    "size,overlap", [(0, 0), (3, -1), (3, 3), (True, 0), (3, False), (3.1, 0)]
)
def test_invalid_configuration_rejected(size, overlap):
    with pytest.raises(ValueError):
        TextSpanConfig(size, overlap)


def test_whitespace_boundary_without_trimming_or_query_input():
    text = " leading words here and then trailing  "
    spans = list(iter_text_spans(text, TextSpanConfig(20, 3)))
    assert spans[0].text.endswith(" ")
    assert spans[-1].text.endswith("  ")
    with pytest.raises(TypeError):
        list(iter_text_spans(None))
