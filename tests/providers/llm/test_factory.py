from __future__ import annotations

import pytest

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    UnknownProviderError,
)
from content_factory.providers.llm.factory import (
    AgentScopedLLMProvider,
    ProviderChain,
    available_providers,
    create_agent_scoped_llm_provider,
    create_default_llm_provider,
    create_llm_provider,
    create_llm_provider_for_agent,
    register_provider,
)
from content_factory.providers.llm.groq import GroqProvider
from content_factory.providers.llm.models import LLMMessage, LLMRequest, LLMResponse
from content_factory.providers.llm.openrouter import OpenRouterProvider
from content_factory.settings.loader import Settings
from content_factory.settings.schemas import FallbackProviderConfig


def test_openrouter_is_registered_by_default() -> None:
    assert "openrouter" in available_providers()


def test_create_llm_provider_builds_registered_provider() -> None:
    provider = create_llm_provider("openrouter", api_key="test-key")
    assert isinstance(provider, OpenRouterProvider)
    provider.close()


def test_create_llm_provider_unknown_name_raises() -> None:
    with pytest.raises(UnknownProviderError):
        create_llm_provider("does-not-exist")


def test_create_llm_provider_for_agent_uses_models_yaml_routing(settings: Settings) -> None:
    provider = create_llm_provider_for_agent(settings, "topic_scout")
    assert isinstance(provider, GroqProvider)
    provider.close()


def test_create_llm_provider_for_agent_reads_timeout_and_retries_from_engine_yaml(
    settings: Settings,
) -> None:
    provider = create_llm_provider_for_agent(settings, "writer")
    assert provider._retry_policy.max_attempts == settings.engine.retries.llm_call_max_retries  # noqa: SLF001
    provider.close()


def test_create_default_llm_provider_uses_models_default_provider(settings: Settings) -> None:
    provider = create_default_llm_provider(settings)
    assert provider.name == settings.models.default_provider
    provider.close()


def test_create_agent_scoped_llm_provider_uses_agent_specific_provider(settings: Settings) -> None:
    provider = create_agent_scoped_llm_provider(settings)
    assert isinstance(provider, AgentScopedLLMProvider)
    # Beklenen sınıflar config'den okunur: hangi ajanın hangi sağlayıcıda çalıştığı bir
    # ayardır (writer, Groq'un dakikalık token tavanı yüzünden Replicate'e taşındı) —
    # sabitlemek testi her ayar değişikliğinde kırıyordu. Doğrulanan davranış
    # "her ajan config'inde yazan sağlayıcıya bağlanıyor" olmalı.
    for agent_name in ("writer", "topic_scout"):
        expected = settings.models.for_agent(agent_name).provider
        assert provider.provider_for(agent_name).name == expected
    # `image_generator` config'i LLM sağlayıcı tarafından kullanılmaz.
    assert "image_generator" not in provider._providers
    provider.close()


def test_register_provider_allows_custom_provider() -> None:
    from content_factory.providers.llm.base import BaseLLMProvider

    class DummyProvider(BaseLLMProvider):
        name = "dummy"
        default_api_key_env = "DUMMY_API_KEY"

        def _do_generate(self, request, *, model):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def stream(self, request, *, agent_name, run_id):  # type: ignore[no-untyped-def]
            yield from ()

        def health_check(self) -> bool:
            return True

    register_provider("dummy", DummyProvider)
    try:
        assert "dummy" in available_providers()
        provider = create_llm_provider("dummy")
        assert isinstance(provider, DummyProvider)
    finally:
        from content_factory.providers.llm import factory as factory_module

        factory_module._REGISTRY.pop("dummy", None)  # noqa: SLF001 - test temizliği


# ------------------------------------------------------------------ ProviderChain


class _FailingProvider(BaseLLMProvider):
    name = "failing"
    default_api_key_env = "FAILING_API_KEY"

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        raise self._error

    def stream(self, request, *, agent_name, run_id):  # pragma: no cover - kullanılmıyor
        raise NotImplementedError

    def health_check(self) -> bool:
        return False


class _RecordingProvider(BaseLLMProvider):
    name = "recording"
    default_api_key_env = "RECORDING_API_KEY"

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[LLMRequest] = []

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content="ok", model=model, provider=self.name)

    def stream(self, request, *, agent_name, run_id):  # pragma: no cover - kullanılmıyor
        raise NotImplementedError

    def health_check(self) -> bool:
        return True


def _chain_config(**overrides: object) -> FallbackProviderConfig:
    defaults: dict[str, object] = {
        "provider": "replicate",
        "model": "meta/meta-llama-3-70b-instruct",
    }
    defaults.update(overrides)
    return FallbackProviderConfig(**defaults)  # type: ignore[arg-type]


def _chain_request(**overrides: object) -> LLMRequest:
    defaults: dict[str, object] = {
        "system_prompt": "sen bir editörsün",
        "messages": [LLMMessage(role="user", content="incele")],
        "model": "llama-3.3-70b-versatile",
        "fallback_models": ["llama-3.1-8b-instant"],
        "max_tokens": 700,
        "response_format": "json_object",
    }
    defaults.update(overrides)
    return LLMRequest(**defaults)  # type: ignore[arg-type]


def test_provider_chain_uses_primary_when_it_succeeds() -> None:
    primary = _RecordingProvider()
    fallback = _RecordingProvider()
    chain = ProviderChain(primary, fallback, _chain_config())

    chain.generate(_chain_request(), agent_name="editor", run_id="r")

    assert len(primary.requests) == 1
    assert fallback.requests == []


def test_provider_chain_falls_over_and_retargets_the_model() -> None:
    """Model adları sağlayıcıya özgüdür: Groq'un `llama-3.3-70b-versatile`'ı Replicate'te
    geçersizdir, bu yüzden istek ikincil sağlayıcının model adıyla yeniden kurulur."""
    fallback = _RecordingProvider()
    chain = ProviderChain(
        _FailingProvider(LLMRateLimitError("kota doldu")), fallback, _chain_config()
    )

    response = chain.generate(_chain_request(), agent_name="editor", run_id="r")

    assert response.content == "ok"
    sent = fallback.requests[0]
    assert sent.model == "meta/meta-llama-3-70b-instruct"
    assert sent.fallback_models == []
    # Prompt ve biçim şartı korunur — yalnızca hedef değişir.
    assert sent.system_prompt == "sen bir editörsün"
    assert sent.response_format == "json_object"


def test_provider_chain_applies_fallback_token_budget() -> None:
    fallback = _RecordingProvider()
    chain = ProviderChain(
        _FailingProvider(LLMRateLimitError("kota doldu")),
        fallback,
        _chain_config(max_tokens=1200),
    )

    chain.generate(_chain_request(max_tokens=700), agent_name="editor", run_id="r")

    assert fallback.requests[0].max_tokens == 1200


def test_provider_chain_keeps_primary_budget_when_fallback_does_not_override() -> None:
    fallback = _RecordingProvider()
    chain = ProviderChain(
        _FailingProvider(LLMRateLimitError("kota doldu")), fallback, _chain_config()
    )

    chain.generate(_chain_request(max_tokens=700), agent_name="editor", run_id="r")

    assert fallback.requests[0].max_tokens == 700


def test_provider_chain_falls_over_on_authentication_error() -> None:
    """API anahtarı eksikse de geçilir: buraya ulaşıldığında birincil sağlayıcının
    elinde başka seçenek kalmamıştır."""
    fallback = _RecordingProvider()
    chain = ProviderChain(
        _FailingProvider(LLMAuthenticationError("anahtar yok")), fallback, _chain_config()
    )

    assert chain.generate(_chain_request(), agent_name="editor", run_id="r").content == "ok"


def test_provider_chain_propagates_fallback_failure() -> None:
    """İkincil sağlayıcı da düşerse hata yükselir — sessizce boş yanıta dönüşmemeli."""
    chain = ProviderChain(
        _FailingProvider(LLMRateLimitError("kota doldu")),
        _FailingProvider(LLMProviderUnavailableError("replicate kapalı")),
        _chain_config(),
    )

    with pytest.raises(LLMProviderUnavailableError):
        chain.generate(_chain_request(), agent_name="editor", run_id="r")
