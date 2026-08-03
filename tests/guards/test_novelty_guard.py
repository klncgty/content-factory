from __future__ import annotations

import pytest

from content_factory.domain.models import Article
from content_factory.guards.novelty_guard import NoveltyGuard


def _article(slug: str, title: str, target_keyword: str = "") -> Article:
    return Article(brand="oleart", slug=slug, title=title, target_keyword=target_keyword)


@pytest.fixture
def guard() -> NoveltyGuard:
    return NoveltyGuard(
        [
            _article(
                "erken-hasat-zeytinyagi-ile-yemek-pisirmenin-faydalari",
                "Erken Hasat Zeytinyağı ile Yemek Pişirmenin Faydaları",
                "erken hasat zeytinyağı yemek pişirme",
            ),
            _article(
                "zeytinyagi-donar-mi",
                "Zeytinyağı Donar mı? Doğru Saklama Rehberi",
                "zeytinyağı donar mı",
            ),
        ]
    )


def test_rejects_same_topic_worded_differently(guard: NoveltyGuard) -> None:
    """Gerçek vaka (30.07.2026): birebir anahtar kelime eşleşmesi bu tekrarı kaçırıyordu."""
    result = guard.check(title="Erken Hasat Zeytinyağı Yemeklerde Nasıl Kullanılır")

    assert result.is_duplicate
    assert result.similar_slug == "erken-hasat-zeytinyagi-ile-yemek-pisirmenin-faydalari"


def test_rejects_shorter_subset_title(guard: NoveltyGuard) -> None:
    result = guard.check(title="Erken Hasat Zeytinyağı ile Yemek Pişirme")

    assert result.is_duplicate


def test_allows_genuinely_different_topic(guard: NoveltyGuard) -> None:
    result = guard.check(
        title="Zeytin Ağacı Kesme Tahtası Nasıl Bakılır",
        seed_keywords=["ahşap kesme tahtası bakımı"],
    )

    assert not result.is_duplicate


def test_allows_different_angle_on_same_product(guard: NoveltyGuard) -> None:
    """Aynı ürün ekseni farklı bir soruya cevap veriyorsa tekrar DEĞİLDİR — filtre burayı
    fazla geniş tutarsa konu havuzu gereksiz yere daralır."""
    result = guard.check(title="Zeytinyağının Asit Oranı Ne Anlama Gelir")

    assert not result.is_duplicate


def test_shared_generic_word_is_not_enough(guard: NoveltyGuard) -> None:
    """Tek ortak kök ('zeytinyağı') her konuda geçer; tek başına tekrar sayılmamalı."""
    result = guard.check(title="Zeytinyağı Sabunu Nasıl Yapılır")

    assert not result.is_duplicate


def test_no_published_articles_means_everything_is_new() -> None:
    result = NoveltyGuard([]).check(title="Erken Hasat Zeytinyağı Nedir")

    assert not result.is_duplicate


def test_rejects_same_axis_with_different_adjective(guard: NoveltyGuard) -> None:
    """Gerçek vaka (03.08.2026): backlog bu üç konuyla dolmuştu. Başa sıfat eklemek
    ("soğuk sıkım" / "duman noktası") konuyu değiştirmez; eski 0.7 eşiği bunların
    hepsini kaçırıyordu (ölçülen kapsama 0.50-0.60)."""
    for title in (
        "Soğuk Sıkım Zeytinyağı ile Yemek Pişirme Teknikleri",
        "Zeytinyağı Duman Noktası ve Yemek Pişirme Güvenliği",
    ):
        assert guard.check(title=title).is_duplicate, title


def test_different_dishes_are_not_duplicates() -> None:
    """Tarifler birbirini engellememeli: onları ayıran şey yemeğin adıdır, ortak
    'zeytinyağlı'/'tarifi' sözcükleri değil. Bu bozulursa ilk tariften sonra hiçbir
    tarif yayınlanamaz."""
    guard = NoveltyGuard([_article("zeytinyagli-enginar", "Zeytinyağlı Enginar Tarifi")])

    for title in (
        "Zeytinyağlı Taze Fasulye Tarifi",
        "Zeytinyağlı Barbunya Pilaki Tarifi",
        "Zeytinyağlı Kabak Mücveri Tarifi",
    ):
        assert not guard.check(title=title).is_duplicate, title


def test_same_dish_in_another_format_is_duplicate() -> None:
    """Aynı yemek, farklı kalıp ("Tarifi" / "Nasıl Yapılır") tekrardır — biçim sözcükleri
    elendiği için geriye aynı çekirdek kalır."""
    guard = NoveltyGuard([_article("zeytinyagli-enginar", "Zeytinyağlı Enginar Tarifi")])

    assert guard.check(title="Zeytinyağlı Enginar Nasıl Yapılır").is_duplicate
