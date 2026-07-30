"""GroundingGuard — makaledeki sayısal iddiaları knowledge base'e karşı doğrular.

**Neden gerekli.** Writer'a "yalnızca araştırma notlarına dayan" deniyor, Editor'e de
(bkz. `agents/editor.py` katman 3) key_facts veriliyor; buna rağmen model *sayıları
kaydırıyor*. Ölçülen (yayınlanmış makaleler, 30.07.2026):

    knowledge: "yaklaşık 5-8°C'nin altında bulanıklaşır"
    makale:    "trigliseritler yaklaşık 6-8°C'nin altında katılaşır"       <- 5 -> 6

    knowledge: "raf ömrü 18-24 ay; açıldıktan sonra birkaç ay içinde"
    makale:    "Açıldıktan sonraki 6-12 ay içinde tüketmeye özen gösterin" <- uydurma
    makale:    "İdeal aralık 14-18°C'dir"                                  <- uydurma

Bir LLM'e "bu sayı doğru mu" diye sormak bu vakaların hepsini yakalamıyor (sayı makul
göründüğü sürece onaylıyor). Sayının knowledge'da GEÇİP GEÇMEDİĞİ ise deterministik
olarak ölçülebilir — bu guard'ın yaptığı tam olarak budur.

**Ölçüm birimi eşleşmesi zorunludur.** Sayılar birimsiz karşılaştırılırsa knowledge'daki
"18-24 **ay**" ifadesi makaledeki "18 **°C**" iddiasını haklı çıkarır ve yukarıdaki
üçüncü vaka kaçar. Bu yüzden hem knowledge hem makale tarafında sayılar birimleriyle
birlikte indekslenir; birimsiz geçen değerler (ör. asitlik tablosundaki `0,8`) ayrı bir
kovada tutulur ve her birime karşı geçerli sayılır.

**Aralıklar iki uca genişletilir, ARASI DOLDURULMAZ.** "5-8°C" ifadesi 5 ve 8'i
zeminler ama 6'yı zeminlemez — aradaki değerleri kabul etmek yukarıdaki birinci vakayı
(5 -> 6 kaydırması) tam olarak kaçırırdı.

**Yanlış pozitif tasarımı.** Bu bir yayın geçididir: haksız bir red, Writer'ın
düzeltemeyeceği bir gerekçeyle retry döngüsü harcar. Bu yüzden iki daraltma yapılır:

1. Yalnızca **ürün özelliği** bildiren birimli sayılar incelenir (`%`, `°C`, `ay`,
   `yıl`, `mg`, `ml`...). Birimsiz sayılar (madde numarası, "2 kabak") hiç bakılmaz.
2. **Tarif/talimat satırları atlanır** — "180 °C'de 8-10 dakika kızartın" bir olgu
   iddiası değil, yemek tarifidir; knowledge'da geçmemesi normaldir.

Ölçüm (yayınlanmış 4 makale, `tests/guards/test_grounding_guard.py`): 4 gerçek uydurma
yakalandı, tarif satırlarından gelen yanlış pozitif sayısı 0.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Ürün özelliği bildiren birimler. Anahtar = normalize edilmiş birim kimliği; eşanlamlı
# yazımlar aynı kimliğe düşer ("27 derece" ile "27°C" aynı iddiadır).
_UNIT_ALIASES: dict[str, str] = {
    "°c": "°c",
    "derece": "°c",
    "%": "%",
    "meq": "meq",
    "kcal": "kcal",
    "ppm": "ppm",
    "mg": "mg",
    "ml": "ml",
    "litre": "litre",
    "lt": "litre",
    "kg": "kg",
    "gram": "gram",
    "gr": "gram",
    "ay": "ay",
    "yıl": "yıl",
    "yil": "yıl",
}

# Bu işaretlerden biri geçen satır tarif/talimattır; içindeki sayılar olgu iddiası
# değildir ("2 yemek kaşığı", "8-10 dakika sote edin").
_INSTRUCTION_MARKERS: frozenset[str] = frozenset(
    {
        "kaşık",
        "dakika",
        "saniye",
        "porsiyon",
        "kişilik",
        "dilim",
        "adet",
        "demet",
        "bardak",
        "fırın",
        "sote",
        "kızart",
        "haşla",
        "pişir",
        "ısıt",
        "kavur",
        "tarif",
        "malzeme",
    }
)

_NUM = r"\d+(?:[.,]\d+)?"
_UNIT_ALTERNATION = "|".join(
    sorted((re.escape(u) for u in _UNIT_ALIASES), key=len, reverse=True)
)

# "18-24 ay", "190-210°C", "5-8°C" — aralığın birimi yalnızca son uçta yazılır ama
# her iki uç da o birimin iddiasıdır.
_RANGE_RE = re.compile(
    rf"(?P<low>{_NUM})\s*-\s*(?P<high>{_NUM})\s*(?P<unit>{_UNIT_ALTERNATION})\b",
    re.IGNORECASE,
)
# "%40" (önde) ve "40 mg" / "27°C" (arkada) tek sayılı iddialar.
_SINGLE_RE = re.compile(
    rf"(?:(?P<pct>%)\s*(?P<pct_num>{_NUM}))"
    rf"|(?:(?P<num>{_NUM})\s*(?P<unit>{_UNIT_ALTERNATION})\b)",
    re.IGNORECASE,
)
# Knowledge tarafında birimi bitişik olmayan ondalık ölçüler (ör. asitlik tablosundaki
# `0,8`) — bkz. `_UNITLESS`.
_BARE_DECIMAL_RE = re.compile(r"\d+[.,]\d+")

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# Markdown link/görsel hedefleri ve URL'ler: içlerindeki sayılar (tarih, boyut) iddia değildir.
_LINK_TARGET_RE = re.compile(r"\]\([^)]*\)|https?://\S+")

_DASHES = "‐‑‒–—−"
"""Modelin ürettiği tire çeşitleri (non-breaking hyphen, en/em dash, minus) — hepsi
düz `-`'ye normalize edilir, aksi halde "190‑210" tek bir sayı gibi görünür."""

_UNITLESS = ""
"""Knowledge'da birimi bitişik yazılmamış ÖLÇÜ değerlerinin kovası — her birime karşı
geçerli sayılır (ör. asitlik tablosundaki `0,8`, birim sütun başlığında durur).

Bu kovaya yalnızca **ondalıklı** sayılar girer. Çıplak tam sayılar knowledge metninde
neredeyse her zaman yapısaldır (madde numarası, "8 yıl"daki gibi zaten birimli olanın
dışında kalan sayaçlar); onları da kabul etmek "18-24 **ay**" ifadesinin makaledeki
"18 **°C**" iddiasını zeminlemesine yol açıyordu — yani guard'ı işlevsiz bırakıyordu."""


@dataclass(frozen=True)
class NumericClaim:
    """Makalede bulunan tek bir sayısal iddia. `text` orijinal yazımıdır (gerekçede
    kullanıcıya gösterilir), `value`/`unit` karşılaştırma için normalize edilmiş hâlidir."""

    text: str
    value: str
    unit: str
    line: str


@dataclass(frozen=True)
class GroundingResult:
    ungrounded: tuple[NumericClaim, ...] = ()

    @property
    def is_grounded(self) -> bool:
        return not self.ungrounded

    def reasons(self) -> list[str]:
        """Editor'ün `QAReport.reasons`'a ekleyeceği, Writer'ın uygulayabileceği somut
        geri bildirim.

        Aynı ifadeden gelen gerekçeler tekilleştirilir: "14-18°C"de iki uç da zeminsiz
        olduğu için iki ayrı `NumericClaim` doğar, ama Writer'a aynı cümleyi iki kez
        söylemek geri bildirimi gürültülü yapar."""
        seen: set[tuple[str, str]] = set()
        reasons: list[str] = []
        for claim in self.ungrounded:
            key = (claim.text, claim.line)
            if key in seen:
                continue
            seen.add(key)
            reasons.append(
                f"Kaynaksız sayısal iddia: {claim.text!r} — bu değer knowledge base'de "
                f"geçmiyor. Ya araştırma notlarındaki değeri kullan ya da cümleyi sayı "
                f"vermeden yaz. (Geçtiği yer: {_excerpt(claim.line)!r})"
            )
        return reasons


class GroundingGuard:
    """Referans metinlerdeki (knowledge dosyaları + araştırma notları) sayılarla
    makaledeki sayısal iddiaları karşılaştırır."""

    def __init__(self, reference_texts: Iterable[str]) -> None:
        self._known: dict[str, set[str]] = _collect_reference_numbers(reference_texts)

    def check(self, article_body: str) -> GroundingResult:
        ungrounded = [
            claim for claim in self.iter_claims(article_body) if not self._is_known(claim)
        ]
        return GroundingResult(ungrounded=tuple(ungrounded))

    def _is_known(self, claim: NumericClaim) -> bool:
        """Değer ya kendi biriminde ya da knowledge'da birimsiz geçiyorsa zeminlenmiştir."""
        return claim.value in self._known.get(claim.unit, ()) or (
            claim.value in self._known.get(_UNITLESS, ())
        )

    @staticmethod
    def iter_claims(article_body: str) -> list[NumericClaim]:
        """Makale gövdesindeki olgu iddiası sayılan sayıları çıkarır (başlık, kod bloğu,
        link hedefi ve tarif satırları hariç)."""
        claims: list[NumericClaim] = []
        seen: set[tuple[str, str, str]] = set()

        for line in _content_lines(article_body):
            lowered = line.lower()
            if any(marker in lowered for marker in _INSTRUCTION_MARKERS):
                continue

            for text, value, unit, span in _iter_unit_numbers(line):
                del span
                key = (value, unit, line)
                if key in seen:
                    # Aynı iddia aynı satırda tekrar ediyorsa tek gerekçe yeter.
                    continue
                seen.add(key)
                claims.append(NumericClaim(text=text, value=value, unit=unit, line=line))
        return claims


def _content_lines(text: str) -> list[str]:
    """Başlıkları, kod bloklarını ve link hedeflerini ayıklanmış satırlar."""
    lines: list[str] = []
    in_fence = False
    for raw_line in _normalize(text).splitlines():
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence or _HEADING_RE.match(raw_line):
            continue
        lines.append(_LINK_TARGET_RE.sub(" ", raw_line).strip())
    return lines


def _iter_unit_numbers(line: str) -> list[tuple[str, str, str, tuple[int, int]]]:
    """Bir satırdaki birimli sayıları `(ham metin, değer, birim, aralık)` olarak verir.
    Aralıklar iki uca genişletilir; aralık olarak eşleşen bölge tek sayı taramasından
    çıkarılır ki "18-24 ay" ayrıca "24 ay" olarak ikinci kez sayılmasın."""
    found: list[tuple[str, str, str, tuple[int, int]]] = []
    consumed: list[tuple[int, int]] = []

    for match in _RANGE_RE.finditer(line):
        unit = _UNIT_ALIASES[match.group("unit").lower()]
        for group in ("low", "high"):
            found.append(
                (match.group(0).strip(), _normalize_number(match.group(group)), unit, match.span())
            )
        consumed.append(match.span())

    for match in _SINGLE_RE.finditer(line):
        if any(start <= match.start() < end for start, end in consumed):
            continue
        if match.group("pct"):
            value, unit = _normalize_number(match.group("pct_num")), "%"
        else:
            value = _normalize_number(match.group("num"))
            unit = _UNIT_ALIASES[match.group("unit").lower()]
        found.append((match.group(0).strip(), value, unit, match.span()))

    return found


def _collect_reference_numbers(texts: Iterable[str]) -> dict[str, set[str]]:
    """Referans metinlerden birim -> değer kümesi indeksi kurar. Birimli değerler kendi
    kovalarına, kalan tüm sayılar `_UNITLESS` kovasına gider."""
    known: dict[str, set[str]] = {}
    for text in texts:
        if not text:
            continue
        for line in _content_lines(text):
            for _, value, unit, _span in _iter_unit_numbers(line):
                known.setdefault(unit, set()).add(value)
            # Birimsiz kova: yalnızca ondalıklı ölçü değerleri (bkz. `_UNITLESS`).
            for match in _BARE_DECIMAL_RE.finditer(line):
                known.setdefault(_UNITLESS, set()).add(_normalize_number(match.group(0)))
    return known


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    for dash in _DASHES:
        normalized = normalized.replace(dash, "-")
    return normalized


def _normalize_number(raw: str) -> str:
    """ "0,8" ve "0.8" aynı sayıdır; "18" ve "18,0" da öyle. Ondalık ayırıcı birleştirilir
    ve sondaki anlamsız sıfırlar atılır — Türkçe metinde iki yazım da geçiyor."""
    value = raw.replace(",", ".")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value or "0"


def _excerpt(line: str, limit: int = 80) -> str:
    return line if len(line) <= limit else f"{line[:limit].rstrip()}…"


def reference_texts_for(knowledge_texts: Sequence[str], key_facts: Sequence[str]) -> list[str]:
    """Guard'ın referans kümesi: knowledge dosyalarının ham metni + ResearchAgent'ın
    key_facts'i. Araştırma notlarındaki sayılar da zeminlenmiş sayılır — onlar zaten
    knowledge'dan türetilmiş ve `sources_used` doğrulamasından geçmiştir."""
    return [*knowledge_texts, *key_facts]
