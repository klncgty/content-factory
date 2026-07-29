"""Token sayımı — maliyet tahmini ve loglama için.

Not: gerçek çağrılarda `LLMResponse.usage` (sağlayıcının döndürdüğü resmi sayaç)
her zaman önceliklidir; buradaki `TokenCounter` yalnızca sağlayıcı çağrısından
*önce* bir tahmin gerektiğinde (ör. bütçe kontrolü) veya `usage` bilgisi mevcut
olmadığında kullanılır. Kesin bir tokenizer (ör. tiktoken) yalnızca tek bir
sağlayıcıya özgüdür ve provider-bağımsızlık ilkesini bozar; bu yüzden kasıtlı
olarak yaklaşık (heuristic) bir sayaç kullanılır.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


class TokenCounter(ABC):
    @abstractmethod
    def count(self, text: str, *, model: str) -> int: ...


class HeuristicTokenCounter(TokenCounter):
    """~4 karakter ≈ 1 token — karışık Türkçe/İngilizce metin için kabaca doğru,
    sektörde yaygın kullanılan bir varsayılan tahmin oranıdır."""

    def __init__(self, *, chars_per_token: float = 4.0) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token pozitif olmalı")
        self._chars_per_token = chars_per_token

    def count(self, text: str, *, model: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self._chars_per_token))
