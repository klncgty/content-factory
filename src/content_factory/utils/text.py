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


def estimate_reading_time_minutes(text: str, *, words_per_minute: int = 200) -> int:
    """oleart.co'daki fallback hesaplamayla tutarlı: kelime sayısı / dakika başına
    kelime, en az 1 dakika."""
    word_count = len(text.split())
    return max(1, round(word_count / words_per_minute))
