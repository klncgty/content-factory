"""429 (rate limit) yanıtlarının merkezi yönetimi.

`BaseLLMProvider` her instance için bir `RateLimitState` tutar: bir model rate limit'e
takıldığında, `retry_after` süresi dolana kadar o modele **hiç istek gönderilmez**
(gereksiz API çağrısı yapılmaz, doğrudan bir sonraki `fallback_models` girdisine geçilir).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime


class RateLimitState:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._blocked_until: dict[str, float] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def mark_rate_limited(self, model: str, retry_after_seconds: float) -> None:
        with self._lock:
            self._blocked_until[model] = self._clock() + max(0.0, retry_after_seconds)

    def is_blocked(self, model: str) -> tuple[bool, float]:
        """`(engellendi mi, kalan saniye)` döndürür. Engel süresi dolmuşsa otomatik temizler."""
        with self._lock:
            until = self._blocked_until.get(model)
            if until is None:
                return False, 0.0
            remaining = until - self._clock()
            if remaining <= 0:
                del self._blocked_until[model]
                return False, 0.0
            return True, remaining

    def clear(self, model: str | None = None) -> None:
        with self._lock:
            if model is None:
                self._blocked_until.clear()
            else:
                self._blocked_until.pop(model, None)


def parse_retry_after(header_value: str | None) -> float | None:
    """HTTP `Retry-After` başlığını saniyeye çevirir. Hem saniye tam sayısını
    (``"30"``) hem de HTTP-date formatını (``"Wed, 21 Oct 2026 07:28:00 GMT"``) destekler.
    Ayrıştırılamazsa `None` döner (çağıran taraf kendi varsayılan backoff'una düşer)."""
    if not header_value:
        return None
    header_value = header_value.strip()
    if header_value.isdigit():
        return float(header_value)
    try:
        target = parsedate_to_datetime(header_value)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    now = target.__class__.now(target.tzinfo)
    delta = (target - now).total_seconds()
    return max(0.0, delta)
