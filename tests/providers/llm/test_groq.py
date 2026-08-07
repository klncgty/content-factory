from __future__ import annotations

import httpx
import pytest

from content_factory.providers.llm.exceptions import (
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMRequestTooLargeError,
)
from content_factory.providers.llm.groq import GroqProvider
from content_factory.providers.llm.models import LLMMessage, LLMRequest
from content_factory.providers.llm.retry import RetryPolicy


def _request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "system_prompt": "sen yardımcı bir asistansın",
        "messages": [LLMMessage(role="user", content="merhaba")],
        "model": "openai/gpt-oss-120b",
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


def _provider(handler, *, retry_policy: RetryPolicy | None = None) -> GroqProvider:
    client = httpx.Client(
        base_url="https://api.groq.com/openai/v1", transport=httpx.MockTransport(handler)
    )
    return GroqProvider(
        api_key="test-key",
        client=client,
        retry_policy=retry_policy or RetryPolicy(max_attempts=1, base_delay_seconds=0.0),
        sleep_fn=lambda _: None,
    )


def _completion(content: str | None, *, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-120b",
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def test_generate_parses_content() -> None:
    provider = _provider(lambda request: _completion("merhaba!"))
    response = provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert response.content == "merhaba!"
    provider.close()


def test_empty_content_raises_provider_unavailable() -> None:
    """Reasoning modelleri max_tokens'ı düşünmede tüketirse 200 OK + boş content döner.

    Boş string'i agent'a vermek orada ham bir ayrıştırma hatasına dönüşüp pipeline'ı
    öldürüyordu; geçici sayılıp retry/fallback'e bırakılır."""
    provider = _provider(lambda request: _completion("", finish_reason="length"))
    with pytest.raises(LLMProviderUnavailableError, match="boş içerik"):
        provider.generate(_request(), agent_name="seo_optimizer", run_id="run-1")
    provider.close()


def test_413_raises_invalid_request_not_retryable() -> None:
    """413 = prompt + max_tokens modelin dakikalık token tavanını tek istekte aşıyor;
    beklemek çözmez, istek küçülmeli."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(413, text="Request too large for model")

    provider = _provider(handler, retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0))
    with pytest.raises(LLMInvalidRequestError, match="token tavanını"):
        provider.generate(_request(), agent_name="research", run_id="run-1")
    assert len(calls) == 1
    provider.close()


def test_429_reads_retry_after_from_reset_tokens_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, text="rate limited", headers={"x-ratelimit-reset-tokens": "18.285s"}
        )

    provider = _provider(handler)
    with pytest.raises(LLMRateLimitError) as excinfo:
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert excinfo.value.retry_after == pytest.approx(18.285)
    provider.close()


def test_429_retry_after_is_capped() -> None:
    """Reset başlığı kovanın TAMAMEN dolma süresini bildirdiği için karamsardır;
    olduğu gibi kullanmak modeli tüm run boyunca devre dışı bırakıyordu."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, text="rate limited", headers={"x-ratelimit-reset-tokens": "21m5s"}
        )

    provider = _provider(handler)
    with pytest.raises(LLMRateLimitError) as excinfo:
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert excinfo.value.retry_after == GroqProvider.MAX_TRUSTED_RETRY_AFTER_SECONDS
    provider.close()


def test_explicit_retry_after_header_wins() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            text="rate limited",
            headers={"retry-after": "7", "x-ratelimit-reset-tokens": "18.285s"},
        )

    provider = _provider(handler)
    with pytest.raises(LLMRateLimitError) as excinfo:
        provider.generate(_request(), agent_name="writer", run_id="run-1")
    assert excinfo.value.retry_after == 7.0
    provider.close()


def test_413_with_reported_overshoot_retries_with_smaller_budget() -> None:
    """Writer'ın revizyon turunda prompt büyüyünce (önceki taslak da ekleniyor) statik
    max_tokens tavanı aşıyordu; Groq aşımın miktarını bildirdiği için istek daraltılıp
    bir kez daha denenir."""
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        seen.append(body["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(
                413,
                text=(
                    "Request too large for model `openai/gpt-oss-120b` on tokens per "
                    "minute (TPM): Limit 8000, Requested 8684, please reduce"
                ),
            )
        return _completion("revize edilmiş metin")

    provider = _provider(handler)
    response = provider.generate(
        _request(max_tokens=4200), agent_name="writer", run_id="run-1"
    )

    assert response.content == "revize edilmiş metin"
    assert seen == [4200, 4200 - 684 - 64]


def test_413_raises_when_budget_cannot_be_shrunk_enough() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413,
            text="on tokens per minute (TPM): Limit 8000, Requested 20000, please reduce",
        )

    provider = _provider(handler)
    with pytest.raises(LLMRequestTooLargeError):
        provider.generate(_request(max_tokens=1000), agent_name="writer", run_id="run-1")
    provider.close()


def test_reasoning_format_sent_only_to_inline_reasoning_models() -> None:
    """qwen düşünmeyi `content` içine gömüyor; `reasoning_format: parsed` onu ayırır."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        bodies.append(_json.loads(request.content))
        return _completion('{"decision":"approved"}')

    provider = _provider(handler)
    provider.generate(_request(model="qwen/qwen3.6-27b"), agent_name="editor", run_id="r")
    provider.generate(_request(model="llama-3.3-70b-versatile"), agent_name="editor", run_id="r")

    assert bodies[0]["reasoning_format"] == "parsed"
    assert "reasoning_format" not in bodies[1]
    provider.close()


def test_unsupported_reasoning_format_is_retried_without_the_parameter() -> None:
    """Model ailesi tahmini yanlışsa istek parametresiz tekrarlanır, run ölmez."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        bodies.append(body)
        if "reasoning_format" in body:
            return httpx.Response(
                400,
                json={"error": {"message": "`reasoning_format` is not supported with this model"}},
            )
        return _completion("tamam")

    provider = _provider(handler)
    response = provider.generate(
        _request(model="qwen/yeni-model"), agent_name="editor", run_id="r"
    )

    assert response.content == "tamam"
    assert len(bodies) == 2
    provider.close()


def test_json_object_response_format_is_sent() -> None:
    """Yapısal çıktı: model gramer seviyesinde JSON dışına çıkamaz. 06.08.2026'da
    editor modeli JSON yerine markdown döndürüp yayın turunu düşürmüştü."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        bodies.append(_json.loads(request.content))
        return _completion('{"decision":"approved"}')

    provider = _provider(handler)
    provider.generate(
        _request(model="llama-3.3-70b-versatile", response_format="json_object"),
        agent_name="editor",
        run_id="r",
    )
    provider.generate(_request(model="llama-3.3-70b-versatile"), agent_name="writer", run_id="r")

    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in bodies[1]
    provider.close()


def test_unsupported_response_format_is_retried_without_the_parameter() -> None:
    """Yapısal çıktıyı desteklemeyen bir modelde istek parametresiz tekrarlanır: JSON
    garantisi prompt seviyesine iner ama run ölmez."""
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(
                400,
                json={"error": {"message": "`response_format` is not supported with this model"}},
            )
        return _completion('{"decision":"approved"}')

    provider = _provider(handler)
    response = provider.generate(
        _request(model="llama-eski", response_format="json_object"),
        agent_name="editor",
        run_id="r",
    )

    assert response.content == '{"decision":"approved"}'
    assert len(bodies) == 2
    provider.close()


def test_two_unsupported_parameters_are_both_dropped() -> None:
    """Groq 400'de yalnızca ilk sorunu bildirir; hem `reasoning_format` hem
    `response_format` reddedilirse istek iki kez düzeltilir."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        body = _json.loads(request.content)
        if "reasoning_format" in body:
            return httpx.Response(
                400, json={"error": {"message": "`reasoning_format` is not supported"}}
            )
        if "response_format" in body:
            return httpx.Response(
                400, json={"error": {"message": "`response_format` is not supported"}}
            )
        return _completion("tamam")

    provider = _provider(handler)
    response = provider.generate(
        _request(model="qwen/eski", response_format="json_object"),
        agent_name="editor",
        run_id="r",
    )

    assert response.content == "tamam"
    provider.close()


def test_undiagnosable_400_is_not_swallowed() -> None:
    """Düzeltilemeyen bir 400 yükselir — sessizce yutulup boş yanıta dönüşmemeli."""
    provider = _provider(
        lambda request: httpx.Response(400, json={"error": {"message": "model bulunamadı"}})
    )

    with pytest.raises(LLMInvalidRequestError):
        provider.generate(_request(), agent_name="editor", run_id="r")
    provider.close()
