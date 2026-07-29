from __future__ import annotations

import json

import httpx
import pytest

from content_factory.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMInsufficientCreditError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from content_factory.providers.llm.models import LLMMessage, LLMRequest
from content_factory.providers.llm.openrouter import OpenRouterProvider
from content_factory.providers.llm.retry import RetryPolicy


def _request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "system_prompt": "sen yardımcı bir asistansın",
        "messages": [LLMMessage(role="user", content="merhaba")],
        "model": "anthropic/claude-sonnet-5",
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


def _success_response(model: str = "anthropic/claude-sonnet-5") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [
                {"message": {"role": "assistant", "content": "merhaba!"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def _provider(handler, *, retry_policy: RetryPolicy | None = None) -> OpenRouterProvider:
    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1", transport=httpx.MockTransport(handler)
    )
    return OpenRouterProvider(
        api_key="test-key",
        client=client,
        retry_policy=retry_policy or RetryPolicy(max_attempts=2, base_delay_seconds=0.0),
        sleep_fn=lambda _: None,
    )


# --------------------------------------------------------------------------- generate()


def test_generate_success_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = json.loads(request.content)
        assert body["model"] == "anthropic/claude-sonnet-5"
        assert body["stream"] is False
        return _success_response()

    provider = _provider(handler)
    response = provider.generate(_request(), agent_name="writer", run_id="run-1")

    assert response.content == "merhaba!"
    assert response.provider == "openrouter"
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5
    provider.close()


def test_generate_includes_system_prompt_as_first_message() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _success_response()

    provider = _provider(handler)
    provider.generate(_request(), agent_name="writer", run_id="run-1")
    messages = captured["body"]["messages"]
    assert messages[0] == {"role": "system", "content": "sen yardımcı bir asistansın"}
    assert messages[1] == {"role": "user", "content": "merhaba"}
    provider.close()


def test_generate_without_api_key_raises_authentication_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - çağrılmamalı
        raise AssertionError("API anahtarı yokken istek gönderilmemeli")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key=None, client=client, sleep_fn=lambda _: None)
    # OPENROUTER_API_KEY ortamda tanımlıysa test yanıltıcı geçebilir; env'i açıkça boşaltıyoruz.
    provider._api_key = None  # noqa: SLF001

    with pytest.raises(LLMAuthenticationError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


def test_generate_401_raises_authentication_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    provider = _provider(handler)
    with pytest.raises(LLMAuthenticationError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


def test_generate_429_raises_rate_limit_with_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "42"}, json={"error": "rate limited"})

    provider = _provider(handler)
    with pytest.raises(LLMRateLimitError) as exc_info:
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert exc_info.value.retry_after == 42.0
    provider.close()


def test_generate_400_raises_invalid_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    provider = _provider(handler)
    with pytest.raises(LLMInvalidRequestError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


def test_generate_402_raises_insufficient_credit_without_retrying() -> None:
    """Bakiye yetersizliği geçici bir hata DEĞİL — tekrar denemek yalnızca gecikme üretir."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(402, json={"error": "Insufficient credits"})

    provider = _provider(handler)
    with pytest.raises(LLMInsufficientCreditError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert calls["n"] == 1
    provider.close()


def test_generate_402_does_not_try_fallback_models() -> None:
    """Sorun modelde değil hesapta — sıradaki model de aynı duvara çarpar."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(402, json={"error": "Insufficient credits"})

    provider = _provider(handler)
    request = _request()
    request = request.model_copy(update={"fallback_models": ["openai/gpt-5"]})
    with pytest.raises(LLMInsufficientCreditError):
        provider.generate(request, agent_name="writer", run_id="run-1")
    assert calls["n"] == 1
    provider.close()


def test_generate_404_raises_invalid_request_error() -> None:
    """Var olmayan bir model adı — retry/fallback değil, net bir yapılandırma hatası."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "No endpoints found for model"})

    provider = _provider(handler)
    with pytest.raises(LLMInvalidRequestError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


def test_generate_500_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "internal"})
        return _success_response()

    provider = _provider(handler, retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0))
    response = provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert response.content == "merhaba!"
    assert calls["n"] == 2
    provider.close()


def test_generate_persistent_500_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal"})

    provider = _provider(handler, retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0))
    with pytest.raises(LLMProviderUnavailableError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


def test_generate_timeout_raises_llm_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("zaman aşımı", request=request)

    provider = _provider(handler, retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0.0))
    with pytest.raises(LLMTimeoutError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


def test_generate_connect_error_raises_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("bağlanılamadı", request=request)

    provider = _provider(handler, retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0.0))
    with pytest.raises(LLMProviderUnavailableError):
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    provider.close()


# ----------------------------------------------------------------------------- stream()


def test_stream_yields_chunks_and_stops_at_done() -> None:
    sse_body = (
        b'data: {"choices":[{"delta":{"content":"Merhaba"},"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" dunya"},"finish_reason":"stop"}]}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})

    provider = _provider(handler)
    chunks = list(provider.stream(_request(), agent_name="writer", run_id="run-1"))

    assert [c.delta for c in chunks] == ["Merhaba", " dunya"]
    assert chunks[-1].finish_reason == "stop"
    provider.close()


def test_stream_error_status_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b'{"error": "bad key"}')

    provider = _provider(handler)
    with pytest.raises(LLMAuthenticationError):
        list(provider.stream(_request(), agent_name="writer", run_id="run-1"))
    provider.close()


# ------------------------------------------------------------------------ health_check()


def test_health_check_true_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json={"data": []})

    provider = _provider(handler)
    assert provider.health_check() is True
    provider.close()


def test_health_check_false_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    provider = _provider(handler)
    assert provider.health_check() is False
    provider.close()


def test_health_check_false_without_api_key_no_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("API anahtarı yokken health_check ağ çağrısı yapmamalı")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenRouterProvider(api_key=None, client=client)
    provider._api_key = None  # noqa: SLF001
    assert provider.health_check() is False
    provider.close()


def test_health_check_never_raises_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("koptu", request=request)

    provider = _provider(handler)
    assert provider.health_check() is False
    provider.close()
