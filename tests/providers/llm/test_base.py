from __future__ import annotations

import pytest

from content_factory.providers.llm.cache import InMemoryLLMCache
from content_factory.providers.llm.exceptions import (
    LLMAllModelsExhaustedError,
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from content_factory.providers.llm.models import LLMMessage, LLMRequest, LLMResponse
from content_factory.providers.llm.retry import RetryPolicy

from .conftest import FakeLLMProvider


def _request(model: str = "model-a", fallback_models: list[str] | None = None) -> LLMRequest:
    return LLMRequest(
        system_prompt="sistem",
        messages=[LLMMessage(role="user", content="merhaba")],
        model=model,
        fallback_models=fallback_models or [],
    )


def _fast_policy(max_attempts: int = 3) -> RetryPolicy:
    return RetryPolicy(max_attempts=max_attempts, base_delay_seconds=0.0, jitter=False)


def test_successful_call_returns_response_on_first_try() -> None:
    provider = FakeLLMProvider(retry_policy=_fast_policy(), sleep_fn=lambda _: None)
    response = provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert response.content == "ok:model-a"
    assert provider.calls == ["model-a"]


def test_retries_same_model_on_transient_error_then_succeeds() -> None:
    provider = FakeLLMProvider(
        side_effects={"model-a": [LLMTimeoutError("geçici"), LLMTimeoutError("geçici")]},
        retry_policy=_fast_policy(max_attempts=3),
        sleep_fn=lambda _: None,
    )
    response = provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert response.content == "ok:model-a"
    assert provider.calls == ["model-a", "model-a", "model-a"]


def test_falls_back_to_next_model_after_retries_exhausted() -> None:
    provider = FakeLLMProvider(
        side_effects={
            "model-a": [LLMProviderUnavailableError("kapalı")] * 3,
        },
        retry_policy=_fast_policy(max_attempts=3),
        sleep_fn=lambda _: None,
    )
    response = provider.generate(
        _request(fallback_models=["model-b"]), agent_name="writer", run_id="run-1"
    )
    assert response.content == "ok:model-b"
    assert provider.calls == ["model-a", "model-a", "model-a", "model-b"]


def test_all_models_exhausted_raises() -> None:
    provider = FakeLLMProvider(
        side_effects={
            "model-a": [LLMProviderUnavailableError("x")] * 3,
            "model-b": [LLMProviderUnavailableError("x")] * 3,
        },
        retry_policy=_fast_policy(max_attempts=3),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(LLMAllModelsExhaustedError):
        provider.generate(
            _request(fallback_models=["model-b"]), agent_name="writer", run_id="run-1"
        )


def test_rate_limited_model_is_skipped_on_next_call_without_hitting_do_generate() -> None:
    """Fallback tanımlı değilken tek modelin başarısızlığı, genel bir "tükendi" hatası
    yerine doğrudan asıl hatayı (burada `LLMRateLimitError`) yükseltir — bkz. base.py
    `generate()` docstring notu."""
    provider = FakeLLMProvider(
        side_effects={"model-a": [LLMRateLimitError("429", retry_after=999.0)]},
        retry_policy=_fast_policy(),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(LLMRateLimitError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert provider.calls == ["model-a"]

    # İkinci çağrı: model hâlâ rate limit altında olmalı, _do_generate TEKRAR çağrılmamalı.
    with pytest.raises(LLMRateLimitError):
        provider.generate(_request(), agent_name="writer", run_id="run-2")
    assert provider.calls == ["model-a"]  # ikinci kez eklenmedi


def test_rate_limit_falls_back_to_next_model() -> None:
    provider = FakeLLMProvider(
        side_effects={"model-a": [LLMRateLimitError("429", retry_after=30.0)]},
        retry_policy=_fast_policy(),
        sleep_fn=lambda _: None,
    )
    response = provider.generate(
        _request(fallback_models=["model-b"]), agent_name="writer", run_id="run-1"
    )
    assert response.content == "ok:model-b"


def test_authentication_error_propagates_without_trying_fallback() -> None:
    provider = FakeLLMProvider(
        side_effects={"model-a": [LLMAuthenticationError("kötü anahtar")]},
        retry_policy=_fast_policy(),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(LLMAuthenticationError):
        provider.generate(
            _request(fallback_models=["model-b"]), agent_name="writer", run_id="run-1"
        )
    assert provider.calls == ["model-a"]  # model-b hiç denenmedi


def test_invalid_request_error_propagates_without_trying_fallback() -> None:
    provider = FakeLLMProvider(
        side_effects={"model-a": [LLMInvalidRequestError("geçersiz")]},
        retry_policy=_fast_policy(),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(LLMInvalidRequestError):
        provider.generate(
            _request(fallback_models=["model-b"]), agent_name="writer", run_id="run-1"
        )
    assert provider.calls == ["model-a"]


def test_cache_hit_avoids_calling_do_generate() -> None:
    cache = InMemoryLLMCache()
    provider = FakeLLMProvider(cache=cache, retry_policy=_fast_policy(), sleep_fn=lambda _: None)
    request = _request()

    first = provider.generate(request, agent_name="writer", run_id="run-1")
    assert provider.calls == ["model-a"]

    second = provider.generate(request, agent_name="writer", run_id="run-2")
    assert second == first
    assert provider.calls == ["model-a"]  # ikinci çağrıda artmadı, cache'ten geldi


def test_different_requests_do_not_share_cache_entry() -> None:
    cache = InMemoryLLMCache()
    provider = FakeLLMProvider(cache=cache, retry_policy=_fast_policy(), sleep_fn=lambda _: None)

    provider.generate(_request(model="model-a"), agent_name="writer", run_id="run-1")
    provider.generate(_request(model="model-b"), agent_name="writer", run_id="run-1")
    assert provider.calls == ["model-a", "model-b"]


def test_count_tokens_delegates_to_token_counter() -> None:
    provider = FakeLLMProvider()
    assert provider.count_tokens("bu bir test metni", model="model-a") > 0
    assert provider.count_tokens("", model="model-a") == 0


def test_context_manager_calls_close() -> None:
    closed = {"value": False}

    class TrackingProvider(FakeLLMProvider):
        def close(self) -> None:
            closed["value"] = True

    with TrackingProvider() as provider:
        assert provider is not None
    assert closed["value"] is True


def test_response_is_pydantic_model_not_dict() -> None:
    provider = FakeLLMProvider(retry_policy=_fast_policy(), sleep_fn=lambda _: None)
    response = provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert isinstance(response, LLMResponse)
