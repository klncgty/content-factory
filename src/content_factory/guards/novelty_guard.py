"""NoveltyGuard — yayınlanmış makalelerle aynı konuyu tekrar eden aday konuları eler.

**Neden gerekli.** TopicScout'un prompt'unda "tekrar etme" talimatı var ve kullanılmış
anahtar kelimeler de prompt'a veriliyor; buna rağmen model aynı konuyu biraz farklı
kelimelerle tekrar öneriyor. Ölçülen (30.07.2026, üç ardışık run):

    "Erken Hasat Zeytinyağı ile Yemek Pişirmenin Faydaları"
    "Erken Hasat Zeytinyağı ile Yemek Pişirme"
    "Erken Hasat Zeytinyağı Yemeklerde Nasıl Kullanılır"

Bunlar StateStore'un tekrar kontrolünden geçiyordu, çünkü o kontrol **birebir** anahtar
kelime eşleşmesine bakıyor ("erken hasat zeytinyağı yemek pişirme" ile "erken hasat
zeytinyağı yemeklerde nasıl kullanılır" farklı string'lerdir). Yani sorun modelin
yaratıcılığı değil, filtrenin ölçtüğü şey.

**Nasıl ölçüyor.** Türkçe sondan eklemeli bir dil olduğu için ("yemek" / "yemeklerde",
"pişirme" / "pişirmenin") tam kelime karşılaştırması işe yaramaz. Burada tam bir
biçimbilimsel çözümleme yerine kelimelerin ilk `_PREFIX_LEN` harfi köke yaklaşım olarak
kullanılır — kütüphane bağımlılığı gerektirmeyen, davranışı tahmin edilebilir bir
yaklaşım. İki başlık, ortak kök sayısı `_MIN_SHARED` ve kapsama oranı `threshold`
eşiklerini birlikte aşarsa aynı konu sayılır.

Kapsama oranı (Jaccard değil) kullanılır: kısa bir başlık, uzun bir başlığın alt kümesi
olabilir ("Zeytinyağı Saklama" ⊂ "Zeytinyağı Saklamanın Püf Noktaları"); Jaccard bu
durumu uzunluk farkı yüzünden kaçırır.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from content_factory.domain.models import Article

_PREFIX_LEN = 5
_MIN_SHARED = 2
_DEFAULT_THRESHOLD = 0.5
"""0.7'den 0.5'e indirildi (04.08.2026). Gerçek vakalarla ölçüldü: yayınlanmış
"Erken Hasat Zeytinyağı ile Yemek Pişirmenin Faydaları" makalesine karşı
"Soğuk Sıkım Zeytinyağı ile Yemek Pişirme Teknikleri" 0.50, "Zeytinyağı Duman Noktası
ve Yemek Pişirme Güvenliği" 0.50, "Erken Hasat Zeytinyağı ve Antioksidan Özellikleri"
0.60 kapsama alıyordu — hepsi 0.70'in altında kaldığı için süzgeçten geçip backlog'a
yazılmıştı. Konuyu değiştirmeden başa sıfat eklemek (soğuk sıkım/erken hasat) kapsamayı
düşürüyor; eşik bu yüzden ortak çekirdeğin yarısına çekildi.

Eşiği düşürmenin gerçek tarifleri birbirine benzetme riski `_FORMAT_WORDS` ile
karşılanır: ölçümde farklı yemekler (taze fasulye, barbunya pilaki, kabak mücveri)
yanlış pozitif vermiyor."""

# Konu taşımayan, neredeyse her başlıkta geçen sözcükler. Bunlar sayılırsa "X Nedir" ile
# "Y Nedir" yapay olarak benzer görünür.
_STOPWORDS = frozenset(
    {
        "ve",
        "ile",
        "için",
        "nasıl",
        "nedir",
        "neden",
        "hangi",
        "mi",
        "mı",
        "mu",
        "mü",
        "bir",
        "bu",
        "da",
        "de",
        "en",
        "çok",
        "daha",
        "olur",
        "olarak",
        "hakkında",
        "rehberi",
        "önemli",
        "önemlidir",
    }
)

_FORMAT_WORDS = frozenset(
    {
        # Makalenin BİÇİMİNİ söyleyen, konusunu söylemeyen sözcükler. Bunlar konu taşıyan
        # sözcük sayılırsa iki farklı yemek tarifi ("Zeytinyağlı Enginar Tarifi" /
        # "Zeytinyağlı Taze Fasulye Tarifi") ortak "tarif" kökü yüzünden birbirinin
        # tekrarı görünür; oysa tarifleri ayıran şey YEMEĞİN ADIDIR. Tersi de doğru:
        # bunlar elendiğinde "Zeytinyağlı Enginar Tarifi" ile "Zeytinyağlı Enginar Nasıl
        # Yapılır" geriye aynı çekirdeği (zeytinyağlı + enginar) bıraktığı için gerçek
        # tekrar olarak yakalanır.
        "tarif",
        "tarifi",
        "tarifler",
        "tarifleri",
        "yapılır",
        "yapılışı",
        "yapımı",
        "püf",
        "ipuçları",
        "önerileri",
        "adım",
        "adımda",
    }
)

_WORD_SPLIT = re.compile(r"[^\wçğıöşüÇĞİÖŞÜ]+", re.UNICODE)


@dataclass(frozen=True)
class NoveltyResult:
    """`is_duplicate` True ise `reason` insan-okur bir gerekçe, `similar_slug` çakışılan
    yayınlanmış makaledir (loglama ve ileride geri bildirim için)."""

    is_duplicate: bool
    reason: str = ""
    similar_slug: str | None = None


class NoveltyGuard:
    def __init__(
        self, published: Sequence[Article], *, threshold: float = _DEFAULT_THRESHOLD
    ) -> None:
        self._threshold = threshold
        # (slug, kök kümesi) — her kontrolde yeniden hesaplamamak için bir kez çıkarılır.
        self._published: list[tuple[str, frozenset[str]]] = []
        for article in published:
            stems = _stems(article.title, *(article.target_keyword or "",))
            if stems:
                self._published.append((article.slug or article.title, stems))

    def check(self, *, title: str, seed_keywords: Sequence[str] = ()) -> NoveltyResult:
        candidate = _stems(title, *seed_keywords)
        if not candidate:
            return NoveltyResult(is_duplicate=False)

        for slug, existing in self._published:
            shared = candidate & existing
            if len(shared) < _MIN_SHARED:
                continue
            # Kapsama: küçük kümenin ne kadarı büyük kümede de var?
            coverage = len(shared) / min(len(candidate), len(existing))
            if coverage >= self._threshold:
                return NoveltyResult(
                    is_duplicate=True,
                    reason=(
                        f"Yayınlanmış {slug!r} makalesiyle aynı konu "
                        f"(ortak kök oranı {coverage:.0%})"
                    ),
                    similar_slug=slug,
                )
        return NoveltyResult(is_duplicate=False)


def _stems(*texts: str) -> frozenset[str]:
    """Metinleri konu taşıyan kelime köklerine indirger (küçük harf, aksan/ek normalize,
    stopword'süz, ilk `_PREFIX_LEN` harf)."""
    stems: set[str] = set()
    for text in texts:
        if not text:
            continue
        normalized = unicodedata.normalize("NFC", text).lower()
        for word in _WORD_SPLIT.split(normalized):
            if len(word) < 3 or word in _STOPWORDS or word in _FORMAT_WORDS:
                continue
            stems.add(word[:_PREFIX_LEN])
    return frozenset(stems)
