from __future__ import annotations

import pytest

from content_factory.guards.review_guard import ReviewFinding, ReviewGuard

_ARTICLE = """# Zeytinyağı Nasıl Saklanır?

Zeytinyağını **serin ve karanlık** bir yerde sakladığınızda tazeliğini korur.
Şişeyi 250 gr'lık kavanozlara bölmek, her açılışta yağın havayla temasını azaltır.
İstanbul'daki mutfaklarda cam kavanoz tercih edilir.
"""


def _guard() -> ReviewGuard:
    return ReviewGuard(_ARTICLE)


def test_finding_with_verbatim_quote_is_kept() -> None:
    finding = ReviewFinding(
        quote="serin ve karanlık bir yerde sakladığınızda",
        problem="Bu cümle bir önceki paragrafta da geçiyor.",
        fix="İkinci geçişi çıkar.",
    )

    review = _guard().verify([finding])

    assert review.verified == (finding,)
    assert review.discarded == ()


def test_hallucinated_quote_is_discarded() -> None:
    """Asıl vaka: model metinde olmayan bir ifadeyi varmış gibi gösteriyor."""
    review = _guard().verify([
        ReviewFinding(quote="smoke point", problem="İngilizce sözcük kullanılmış.")
    ])

    assert review.verified == ()
    assert not review.has_verified_findings
    assert "uydurma" in review.discarded[0].reason


def test_markdown_emphasis_does_not_break_a_correct_quote() -> None:
    """Model alıntıyı düz metin olarak kopyalar; makalede aynı yer `**kalın**` olabilir.
    Biçim farkı doğru bir iddiayı elemeye yetmemeli."""
    review = _guard().verify([
        ReviewFinding(quote="serin ve karanlık", problem="Gereksiz vurgu var.")
    ])

    assert review.has_verified_findings


def test_narrow_no_break_space_does_not_break_a_correct_quote() -> None:
    """Makalede `250 gr` (dar kırılmaz boşluk) geçiyor; model bunu normal boşlukla
    alıntılıyor. Normalize edilmezse doğru alıntı "metinde yok" sayılırdı."""
    review = _guard().verify([
        ReviewFinding(quote="250 gr'lık kavanozlara", problem="Ölçü araştırma notlarında yok.")
    ])

    assert review.has_verified_findings


def test_turkish_uppercase_i_does_not_break_a_correct_quote() -> None:
    """`str.lower()` tek başına `İSTANBUL`u eşleşmez hâle getirirdi."""
    review = _guard().verify([
        ReviewFinding(quote="İSTANBUL'DAKİ MUTFAKLARDA", problem="Konu dışına çıkıyor.")
    ])

    assert review.has_verified_findings


@pytest.mark.parametrize("quote", ["", "   ", "ve"])
def test_missing_or_too_short_quote_is_discarded(quote: str) -> None:
    """Çıpasız bir iddia sınanamaz; "ve" gibi bir alıntı her metinde geçer ve iddiayı
    hiç doğrulamaz."""
    review = _guard().verify([ReviewFinding(quote=quote, problem="Metin zayıf.")])

    assert review.verified == ()


def test_english_problem_statement_is_discarded() -> None:
    review = _guard().verify([
        ReviewFinding(
            quote="serin ve karanlık",
            problem="The article contains phrases which are not allowed by the brand tone.",
        )
    ])

    assert review.verified == ()
    assert "Türkçe" in review.discarded[0].reason


def test_empty_problem_is_discarded() -> None:
    review = _guard().verify([ReviewFinding(quote="serin ve karanlık", problem="  ")])

    assert review.verified == ()


def test_verified_and_hallucinated_findings_are_separated() -> None:
    """Karışık bir incelemede doğrulanan bulgular korunur, uydurma olanlar düşer."""
    good = ReviewFinding(
        quote="cam kavanoz tercih edilir",
        problem="Bu iddia araştırma notlarında yok.",
        fix="Cümleyi kaldır.",
    )
    bad = ReviewFinding(quote="cold press", problem="İngilizce sözcük.")

    review = _guard().verify([good, bad])

    assert review.verified == (good,)
    assert len(review.discarded) == 1


def test_feedback_line_carries_quote_problem_and_fix() -> None:
    review = _guard().verify([
        ReviewFinding(
            quote="cam kavanoz tercih edilir",
            problem="Kaynaksız iddia.",
            fix="Cümleyi kaldır.",
        )
    ])

    assert review.feedback_lines() == [
        "«cam kavanoz tercih edilir» — Kaynaksız iddia. Düzeltme: Cümleyi kaldır."
    ]
