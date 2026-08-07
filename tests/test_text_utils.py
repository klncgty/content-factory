from __future__ import annotations

import pytest

from content_factory.utils.text import (
    estimate_reading_time_minutes,
    is_probably_turkish,
    normalize_for_comparison,
    slugify,
)


def test_slugify_maps_turkish_characters() -> None:
    assert slugify("Zeytinyağı Donar mı?") == "zeytinyagi-donar-mi"


def test_slugify_collapses_multiple_separators() -> None:
    assert slugify("Zeytin  Ağacı -- Kesme Tahtası!!") == "zeytin-agaci-kesme-tahtasi"


def test_slugify_strips_leading_trailing_dashes() -> None:
    assert slugify("  Zeytinyağı  ") == "zeytinyagi"


def test_slugify_matches_oleart_co_build_script_output() -> None:
    # oleart.co/scripts/build-blog.mjs ile aynı örnek başlıklar, aynı sonuç üretmeli.
    assert slugify("Zeytinyağı Donar mı? Doğru Saklama Rehberi") == (
        "zeytinyagi-donar-mi-dogru-saklama-rehberi"
    )


def test_estimate_reading_time_minimum_one_minute() -> None:
    assert estimate_reading_time_minutes("kısa metin") == 1


def test_estimate_reading_time_scales_with_word_count() -> None:
    text = " ".join(["kelime"] * 400)
    assert estimate_reading_time_minutes(text, words_per_minute=200) == 2


# ------------------------------------------------------------------ dil ve normalizasyon


@pytest.mark.parametrize(
    "text",
    [
        "Bu cümle Türkçedir ve akıcı okunuyor.",
        "Zeytinyagi saklama kosullari uzerine bir yazi",  # Türkçe ama aksansız
        "smoke point",  # karar verilemeyecek kadar kısa -> şüpheden sanık yararlanır
        "Metinde smoke point ifadesi geçiyor, Türkçesini yaz.",  # İngilizce terim içeren Türkçe
    ],
)
def test_is_probably_turkish_accepts(text: str) -> None:
    assert is_probably_turkish(text)


@pytest.mark.parametrize(
    "text",
    [
        "The article contains English words and phrases which are not allowed.",
        "Additionally the tone of this article is not consistent with the brand.",
    ],
)
def test_is_probably_turkish_rejects_english(text: str) -> None:
    assert not is_probably_turkish(text)


def test_normalize_collapses_whitespace_and_markdown() -> None:
    assert normalize_for_comparison("**Serin   ve\nkaranlık**") == "serin ve karanlik"


def test_normalize_maps_turkish_uppercase_i() -> None:
    assert normalize_for_comparison("İSTANBUL") == normalize_for_comparison("istanbul")


def test_normalize_unifies_narrow_no_break_space() -> None:
    assert normalize_for_comparison("250 gr") == normalize_for_comparison("250 gr")


def test_normalize_unifies_curly_quotes() -> None:
    assert normalize_for_comparison("“serin”") == normalize_for_comparison('"serin"')
