"""Opsiyonel LLM yanıt cache'i — aynı istek (aynı prompt + aynı parametreler) tekrar
gelirse sağlayıcıya gitmeden yanıt döndürür.

Bu iterasyonda gerçek bir cache zorunlu değildir (`BaseLLMProvider(cache=None)`
varsayılanı); mimari hazırdır — `InMemoryLLMCache` somut implementasyonu ve `LLMCache`
arayüzü mevcuttur, ileride Redis vb. bir implementasyon aynı arayüzle eklenebilir.
"""

from __future__ import annotations

import hashlib
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from content_factory.providers.llm.models import LLMRequest, LLMResponse


def make_cache_key(request: LLMRequest) -> str:
    """Aynı istek her zaman aynı anahtarı üretir (deterministik); `LLMRequest` frozen
    olduğu için pydantic'in alan sırası tutarlıdır."""
    payload = request.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LLMCache(ABC):
    @abstractmethod
    def get(self, key: str) -> LLMResponse | None: ...

    @abstractmethod
    def set(self, key: str, response: LLMResponse, *, ttl_seconds: int | None = None) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...


@dataclass
class _CacheEntry:
    response: LLMResponse
    expires_at: float | None


class InMemoryLLMCache(LLMCache):
    """Basit, süreç-içi TTL cache — tek bir pipeline run'ı içinde aynı isteğin tekrar
    tekrar sağlayıcıya gitmesini önlemek için yeterlidir. Çok-süreçli/kalıcı bir cache
    gerekirse (ör. Redis) yalnızca `LLMCache`'i implemente eden yeni bir sınıf eklenir;
    `BaseLLMProvider` implementasyon detayını bilmez."""

    def __init__(
        self, *, default_ttl_seconds: int | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._default_ttl = default_ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()

    def get(self, key: str) -> LLMResponse | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at is not None and self._clock() >= entry.expires_at:
                del self._store[key]
                return None
            return entry.response

    def set(self, key: str, response: LLMResponse, *, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = self._clock() + ttl if ttl is not None else None
        with self._lock:
            self._store[key] = _CacheEntry(response=response, expires_at=expires_at)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
