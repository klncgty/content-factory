"""Metin yardımcı fonksiyonları — birden çok agent'ın (SEOOptimizer, Publisher) ihtiyaç
duyduğu, saf/deterministik (LLM gerektirmeyen) dönüşümler.
"""

from __future__ import annotations

import re
import unicodedata

_TR_MAP = {
    "ç": "c",
    "Ç": "c",
    "ğ": "g",
    "Ğ": "g",
    "ı": "i",
    "İ": "i",
    "ö": "o",
    "Ö": "o",
    "ş": "s",
    "Ş": "s",
    "ü": "u",
    "Ü": "u",
}


def slugify(text: str) -> str:
    """Türkçe karakterleri ASCII'ye çevirip URL-güvenli bir slug üretir.
    oleart.co `scripts/build-blog.mjs` içindeki slugify ile aynı kurallara uyar —
    iki taraf da aynı slug'ı üretmelidir (bkz. ARCHITECTURE.md §6 yayın sözleşmesi)."""
    mapped = "".join(_TR_MAP.get(ch, ch) for ch in text)
    normalized = unicodedata.normalize("NFD", mapped)
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    lowered = without_marks.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug


def blog_url(slug: str) -> str:
    """Bir makale slug'ının site içi URL'i. LinkerAgent gövdeye link yazarken,
    EditorAgent o linklerin gerçekten işlendiğini doğrularken bu TEK fonksiyonu
    kullanır — iki taraf ayrı ayrı biçim kurarsa sessizce birbirinden kayarlar."""
    return f"/blog/{slug}/"


_MARKDOWN_NOISE = re.compile(r"[*_`~#>\[\]]")
"""Vurgu/başlık işaretleri. Karşılaştırmadan önce silinir: model bir cümleyi alıntılarken
metindeki `**kalın**` işaretlerini yazmaz, o yüzden alıntı biçim yüzünden eşleşmezlik
üretmemelidir."""

_UNICODE_LOOKALIKES = {
    "‘": "'", "’": "'", "“": '"', "”": '"',  # eğri tırnaklar
    "–": "-", "—": "-", "−": "-",                  # tire varyantları
    "…": "...",
    " ": " ", " ": " ", " ": " ",                  # kırılmaz/dar boşluklar
    "‑": "-",                                                 # kırılmaz tire
}
"""Modelin yanıtında ve makalede FARKLI yazılabilen aynı anlamlı karakterler.

Gerçek vaka: makalede `250 gr` (dar kırılmaz boşluk) geçerken model bunu `250 gr`
diye alıntılıyor — normalize edilmezse doğru bir alıntı "metinde yok" sayılırdı."""


def normalize_for_comparison(text: str) -> str:
    """İki metin parçasının "aynı şeyi söyleyip söylemediğini" karşılaştırmak için ortak
    biçime indirger: unicode benzerleri sadeleşir, markdown işaretleri düşer, tüm boşluk
    dizileri tek boşluğa iner ve metin küçük harfe çevrilir.

    Türkçe büyük/küçük harf tuzağı (`I`/`ı`, `İ`/`i`) `slugify`'daki aynı `_TR_MAP` ile
    aşılır — `str.lower()` tek başına `İSTANBUL`u `i̇stanbul` yapıp eşleşmeyi bozardı."""
    for source, target in _UNICODE_LOOKALIKES.items():
        text = text.replace(source, target)
    mapped = "".join(_TR_MAP.get(ch, ch) for ch in text)
    without_markdown = _MARKDOWN_NOISE.sub("", mapped)
    return re.sub(r"\s+", " ", without_markdown).strip().lower()


_ENGLISH_MARKERS = frozenset({
    "the", "and", "is", "are", "was", "were", "of", "to", "in", "for", "with", "that",
    "this", "which", "not", "should", "would", "contains", "article", "words", "phrases",
    "such", "as", "additionally", "some", "sentences", "tone", "brand", "allowed", "its",
    "there", "have", "has", "been", "from", "your", "please", "review", "content",
})
"""Türkçe bir metinde tek başına geçmesi beklenmeyen İngilizce işlev sözcükleri."""

_TURKISH_LETTERS = frozenset("çğıöşüÇĞİÖŞÜ")


def is_probably_turkish(text: str) -> bool:
    """Metin Türkçe mi? Kütüphane bağımlılığı olmayan, bilinçli olarak MUHAFAZAKÂR bir
    sezgisel: emin olunamayan her durumda `True` döner.

    Neden gerekli: 06.08.2026 run'ında editör son reddetme gerekçesini İNGİLİZCE yazdı
    ("The article contains English words..."). Türkçe yazmayan bir model prompt'u tümden
    yok saymış demektir; o incelemenin içeriği de güvenilir değildir. Ayrıca İngilizce
    bir geri bildirim Writer prompt'una girdiğinde Writer'ı da dilden çıkarma riski taşır.

    Kural: Türkçeye özgü bir harf varsa Türkçedir. Yoksa, İngilizce işlev sözcüğü sayısı
    hem bir eşiği aşıyor hem de metnin kayda değer bir oranını kaplıyorsa Türkçe değildir
    — böylece içinde birkaç İngilizce terim geçen Türkçe cümleler yanlışlıkla elenmez."""
    if any(ch in _TURKISH_LETTERS for ch in text):
        return True
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if len(words) < 4:
        # Çok kısa metinde ("smoke point") dil kararı verilemez; şüpheden sanık yararlanır.
        return True
    english_hits = sum(1 for word in words if word in _ENGLISH_MARKERS)
    return not (english_hits >= 3 and english_hits / len(words) >= 0.15)


def estimate_reading_time_minutes(text: str, *, words_per_minute: int = 200) -> int:
    """oleart.co'daki fallback hesaplamayla tutarlı: kelime sayısı / dakika başına
    kelime, en az 1 dakika."""
    word_count = len(text.split())
    return max(1, round(word_count / words_per_minute))
