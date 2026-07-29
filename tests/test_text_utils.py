from __future__ import annotations

from content_factory.utils.text import estimate_reading_time_minutes, slugify


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
