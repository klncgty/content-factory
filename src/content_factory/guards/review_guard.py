"""ReviewGuard — LLM editörün İDDİALARINI makale metnine karşı doğrular.

Neden var (06.08.2026 yayın run'ı): Editor aynı makaleyi dört kez, her seferinde farklı
ve büyük ölçüde UYDURMA gerekçelerle reddetti. Son turda "makalede 'moke point',
'cold press', 'helf life' geçiyor" dedi — oysa bu ifadelerin üçü de metinde yoktu ve
ikisi zaten `brand.yaml: forbidden_words` içinde olduğu için Editor'ün deterministik
birinci katmanı onları görseydi LLM katmanı hiç çalışmayacaktı (bkz. `agents/editor.py`,
katman sıralaması). Yani model makaleyi okumadan gerekçe üretiyordu.

Çözümün özü, LLM'e ne soracağımızı değiştirmek: her gerekçe artık metinden BİREBİR bir
alıntı taşımak zorunda. Alıntı, iddianın doğrulanabilir çıpasıdır — kod alıntının
gerçekten metinde geçip geçmediğini bakar. Geçmiyorsa iddia halüsinasyondur ve karara
katılmaz. Böylece LLM'e bırakılan tek şey ÖZNEL yargı ("bu cümle satış odaklı mı")
kalır; nesnel olan her şey (ifade metinde var mı, hangi dilde yazılmış) kodda ölçülür.

Bu guard, `guards/` altındaki diğerleriyle aynı sözleşmeye uyar: saf, deterministik,
LLM çağırmayan bir yardımcı — girdi metin, çıktı ölçüm.
"""

from __future__ import annotations

from dataclasses import dataclass

from content_factory.utils.text import is_probably_turkish, normalize_for_comparison

MIN_QUOTE_CHARS = 4
"""Bir alıntının çıpa sayılması için gereken en az uzunluk (normalize edilmiş hâlde).

Daha kısası doğrulamayı anlamsız kılar: "ve" ya da "bir" gibi bir alıntı her metinde
geçer ve modelin iddiasını hiç sınamaz."""


@dataclass(frozen=True)
class ReviewFinding:
    """Editörün tek bir bulgusu. `quote` makaleden birebir alıntı, `problem` sorunun ne
    olduğu, `fix` Writer'ın uygulayacağı somut düzeltme."""

    quote: str
    problem: str
    fix: str = ""

    def as_feedback(self) -> str:
        """Writer'ın `feedback` alanına giren biçim. Alıntının başta olması bilinçli:
        Writer prompt'u "yalnızca geri bildirimde geçen yerlere dokun" diyor, dokunulacak
        yeri en net gösteren şey metnin kendisidir."""
        suffix = f" Düzeltme: {self.fix}" if self.fix else ""
        return f'«{self.quote}» — {self.problem}{suffix}'


@dataclass(frozen=True)
class DiscardedFinding:
    finding: ReviewFinding
    reason: str


@dataclass(frozen=True)
class VerifiedReview:
    verified: tuple[ReviewFinding, ...]
    discarded: tuple[DiscardedFinding, ...]

    @property
    def has_verified_findings(self) -> bool:
        return bool(self.verified)

    def feedback_lines(self) -> list[str]:
        return [finding.as_feedback() for finding in self.verified]


class ReviewGuard:
    """Bir makale metnine karşı editör bulgularını doğrular."""

    def __init__(self, article_text: str) -> None:
        self._haystack = normalize_for_comparison(article_text)

    def verify(self, findings: list[ReviewFinding]) -> VerifiedReview:
        verified: list[ReviewFinding] = []
        discarded: list[DiscardedFinding] = []

        for finding in findings:
            rejection = self._rejection_reason(finding)
            if rejection is None:
                verified.append(finding)
            else:
                discarded.append(DiscardedFinding(finding=finding, reason=rejection))

        return VerifiedReview(verified=tuple(verified), discarded=tuple(discarded))

    def _rejection_reason(self, finding: ReviewFinding) -> str | None:
        """Bulgu neden karara katılamaz? Katılabiliyorsa `None`."""
        quote = normalize_for_comparison(finding.quote)
        if len(quote) < MIN_QUOTE_CHARS:
            return "alıntı yok veya doğrulanamayacak kadar kısa"
        if quote not in self._haystack:
            # Halüsinasyonun yakalandığı yer: model metinde olmayan bir ifadeyi
            # varmış gibi gösterdi.
            return "alıntı makalede geçmiyor (uydurma iddia)"
        if not finding.problem.strip():
            return "gerekçe boş"
        if not is_probably_turkish(finding.problem):
            # Türkçe yazmayan bir model prompt'u tümden yok saymış demektir; ayrıca
            # İngilizce geri bildirim Writer'ı da dilden çıkarma riski taşır.
            return "gerekçe Türkçe yazılmamış"
        return None
