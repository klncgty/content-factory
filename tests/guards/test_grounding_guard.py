from __future__ import annotations

import pytest

from content_factory.guards.grounding_guard import GroundingGuard, reference_texts_for

# Gerçek knowledge dosyasının (knowledge/brands/oleart/olive_oil.md) sayısal iddia
# taşıyan bölümlerinin özü. Testin bu kopyaya dayanması bilinçli: guard'ın davranışı
# knowledge içeriği düzenlendiğinde sessizce değişmemeli.
_KNOWLEDGE = """
## 1. Sınıflandırma ve Serbest Asitlik

| Natürel sızma zeytinyağı | **0,8** | Doğrudan tüketilir |
| Natürel birinci zeytinyağı | **2,0** | Doğrudan tüketilir |
| Rafine zeytinyağı | 0,3 | Rafinasyon ürünü |

Ek kriter: peroksit değeri en fazla **20 meq O₂/kg**'dır.

## 2. Soğuk Sıkım

**27°C'nin altında** işlenmesi koşuluyla kullanılabilir.

## 4. Saklama Koşulları

- **Raf ömrü:** üretim tarihinden itibaren tipik olarak **18-24 ay**; açıldıktan
  sonra birkaç ay içinde tüketilmesi tavsiye edilir.

## 5. Soğukta Katılaşma

Zeytinyağı yaklaşık **5-8°C'nin altında** bulanıklaşır.

## 6. Kullanım

- **Sıcak kullanım:** duman noktası genellikle **190-210°C** aralığında bildirilir.
"""


@pytest.fixture
def guard() -> GroundingGuard:
    return GroundingGuard([_KNOWLEDGE])


def _values(guard: GroundingGuard, body: str) -> set[str]:
    return {f"{c.value}{c.unit}" for c in guard.check(body).ungrounded}


# --------------------------------------------------------------- zeminlenmiş iddialar


def test_value_present_in_knowledge_is_grounded(guard: GroundingGuard) -> None:
    assert guard.check("Duman noktası 190-210°C aralığındadır.").is_grounded


def test_single_endpoint_of_known_range_is_grounded(guard: GroundingGuard) -> None:
    assert guard.check("Sıcaklığı 190°C'yi aşmamak gerekir.").is_grounded


def test_decimal_separator_variants_are_equivalent(guard: GroundingGuard) -> None:
    """Knowledge `0,8` yazıyor; makale `0.8` yazarsa aynı sayıdır."""
    assert guard.check("Serbest asitlik oranı %0.8 sınırındadır.").is_grounded


def test_unicode_dash_variants_are_normalized(guard: GroundingGuard) -> None:
    """Model non-breaking hyphen (U+2011) üretiyor — düz tire gibi ele alınmalı."""
    assert guard.check("Duman noktası 190‑210 °C arasındadır.").is_grounded


def test_article_without_numbers_is_grounded(guard: GroundingGuard) -> None:
    assert guard.check("Zeytinyağı serin ve karanlık bir yerde saklanmalıdır.").is_grounded


# ------------------------------------------------------------- gerçek uydurma vakaları
# Aşağıdakiler yayınlanmış makalelerden alınmıştır (30.07.2026) — guard bunları
# yakalamak için yazıldı, regresyon olarak sabitlenmiştir.


def test_catches_shifted_range_endpoint(guard: GroundingGuard) -> None:
    """knowledge: "5-8°C" -> makale: "6-8°C". Aralık ARASI doldurulmadığı için 6 yakalanır."""
    result = guard.check("Trigliseritler yaklaşık 6-8°C'nin altında katılaşmaya başlar.")
    assert [c.value for c in result.ungrounded] == ["6"]


def test_catches_invented_storage_range(guard: GroundingGuard) -> None:
    """Knowledge saklama sıcaklığı için hiç sayı vermiyor; makale uydurmuş."""
    assert _values(guard, "İdeal saklama aralığı 14-18°C'dir.") == {"14°c", "18°c"}


def test_catches_invented_shelf_life_after_opening(guard: GroundingGuard) -> None:
    assert _values(guard, "Açıldıktan sonraki 6-12 ay içinde tüketin.") == {"6ay", "12ay"}


def test_unit_mismatch_is_not_grounded(guard: GroundingGuard) -> None:
    """Knowledge'da 18 yalnızca "ay" birimiyle geçiyor — "18°C" iddiasını zeminlemez.
    Birimsiz karşılaştırma yapılsaydı bu iddia sessizce onaylanırdı."""
    assert _values(guard, "Yağı 18°C sıcaklıkta saklayın.") == {"18°c"}


def test_percentage_not_in_knowledge_is_flagged(guard: GroundingGuard) -> None:
    assert _values(guard, "Zeytinyağının %75 kadarı oleik asittir.") == {"75%"}


# --------------------------------------------------------------- yanlış pozitif önleme


def test_recipe_lines_are_ignored(guard: GroundingGuard) -> None:
    """Tarif satırlarındaki sayılar olgu iddiası değildir; knowledge'da geçmemeleri normal."""
    body = (
        "- 2 yemek kaşığı zeytinyağı ekleyin.\n"
        "- Fırında 180 °C'de 8-10 dakika kızartın.\n"
        "- Balığı 190 °C'ye yakın sıcaklıkta 2-3 dakika pişirin.\n"
    )
    assert guard.check(body).is_grounded


def test_headings_and_list_numbers_are_ignored(guard: GroundingGuard) -> None:
    """Başlık numaraları ve birimsiz sayılar iddia sayılmaz."""
    body = "## 3. Saklama\n\nBu bölümde 5 farklı yöntem anlatılır.\n"
    assert guard.check(body).is_grounded


def test_code_blocks_are_ignored(guard: GroundingGuard) -> None:
    body = "```\nasitlik = 99.9\n```\n\nZeytinyağı serin yerde saklanır.\n"
    assert guard.check(body).is_grounded


def test_link_targets_are_ignored(guard: GroundingGuard) -> None:
    """Slug/URL içindeki tarihler (2026-08-01) sayısal iddia değildir."""
    body = "Ayrıntı için [şu yazıya](/blog/2026-08-01-zeytinyagi-donar-mi) bakın.\n"
    assert guard.check(body).is_grounded


# ------------------------------------------------------------ araştırma notu entegrasyonu


def test_key_facts_ground_claims_absent_from_knowledge() -> None:
    """ResearchAgent'ın notlarındaki sayılar da zeminlenmiş sayılır — bunlar zaten
    knowledge'dan türetilmiş ve `sources_used` doğrulamasından geçmiştir."""
    guard = GroundingGuard(
        reference_texts_for([_KNOWLEDGE], ["Sele zeytini salamurada 6 ay bekletilir."])
    )
    assert guard.check("Sele zeytini yaklaşık 6 ay salamurada kalır.").is_grounded


def test_reason_mentions_the_claim_and_its_context(guard: GroundingGuard) -> None:
    """Writer'ın düzeltebilmesi için gerekçe hem değeri hem geçtiği cümleyi taşımalı."""
    result = guard.check("İdeal saklama aralığı 14-18°C'dir.")
    reason = result.reasons()[0]
    assert "14-18°C" in reason
    assert "İdeal saklama aralığı" in reason


def test_same_expression_yields_a_single_reason(guard: GroundingGuard) -> None:
    """"14-18°C"de iki uç da zeminsizdir ama Writer'a tek bir gerekçe gitmeli."""
    result = guard.check("İdeal saklama aralığı 14-18°C'dir.")
    assert len(result.ungrounded) == 2
    assert len(result.reasons()) == 1
