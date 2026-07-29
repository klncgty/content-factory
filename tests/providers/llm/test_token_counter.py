from __future__ import annotations

import pytest

from content_factory.providers.llm.token_counter import HeuristicTokenCounter


def test_empty_text_is_zero_tokens() -> None:
    counter = HeuristicTokenCounter()
    assert counter.count("", model="any") == 0


def test_short_text_counts_at_least_one_token() -> None:
    counter = HeuristicTokenCounter()
    assert counter.count("a", model="any") == 1


def test_count_scales_with_length() -> None:
    counter = HeuristicTokenCounter(chars_per_token=4.0)
    assert counter.count("a" * 40, model="any") == 10


def test_invalid_chars_per_token_raises() -> None:
    with pytest.raises(ValueError):
        HeuristicTokenCounter(chars_per_token=0)
    with pytest.raises(ValueError):
        HeuristicTokenCounter(chars_per_token=-1)
