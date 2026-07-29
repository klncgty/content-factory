from __future__ import annotations

from content_factory.providers.llm.cache import InMemoryLLMCache, make_cache_key
from content_factory.providers.llm.models import LLMMessage, LLMRequest, LLMResponse


def _request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "system_prompt": "sistem",
        "messages": [LLMMessage(role="user", content="merhaba")],
        "model": "model-a",
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


def test_make_cache_key_is_deterministic() -> None:
    r1 = _request()
    r2 = _request()
    assert make_cache_key(r1) == make_cache_key(r2)


def test_make_cache_key_differs_for_different_requests() -> None:
    r1 = _request()
    r2 = _request(temperature=0.9)
    assert make_cache_key(r1) != make_cache_key(r2)


def test_cache_get_miss_returns_none() -> None:
    cache = InMemoryLLMCache()
    assert cache.get("nope") is None


def test_cache_set_then_get_returns_response() -> None:
    cache = InMemoryLLMCache()
    response = LLMResponse(content="merhaba", model="model-a", provider="fake")
    cache.set("key-1", response)
    assert cache.get("key-1") == response


def test_cache_ttl_expiry() -> None:
    clock = {"t": 0.0}
    cache = InMemoryLLMCache(clock=lambda: clock["t"])
    response = LLMResponse(content="x", model="model-a", provider="fake")

    cache.set("key-1", response, ttl_seconds=10)
    clock["t"] = 5.0
    assert cache.get("key-1") == response

    clock["t"] = 11.0
    assert cache.get("key-1") is None


def test_cache_default_ttl_used_when_not_overridden() -> None:
    clock = {"t": 0.0}
    cache = InMemoryLLMCache(default_ttl_seconds=5, clock=lambda: clock["t"])
    response = LLMResponse(content="x", model="model-a", provider="fake")

    cache.set("key-1", response)
    clock["t"] = 6.0
    assert cache.get("key-1") is None


def test_cache_without_ttl_never_expires() -> None:
    clock = {"t": 0.0}
    cache = InMemoryLLMCache(clock=lambda: clock["t"])
    response = LLMResponse(content="x", model="model-a", provider="fake")

    cache.set("key-1", response)
    clock["t"] = 10_000.0
    assert cache.get("key-1") == response


def test_cache_clear_removes_all_entries() -> None:
    cache = InMemoryLLMCache()
    cache.set("key-1", LLMResponse(content="x", model="model-a", provider="fake"))
    cache.clear()
    assert cache.get("key-1") is None
