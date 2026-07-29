from __future__ import annotations

import pytest

from content_factory.providers.llm.exceptions import UnknownProviderError
from content_factory.providers.llm.factory import (
    available_providers,
    create_default_llm_provider,
    create_llm_provider,
    create_llm_provider_for_agent,
    register_provider,
)
from content_factory.providers.llm.openrouter import OpenRouterProvider
from content_factory.settings.loader import Settings


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
    assert isinstance(provider, OpenRouterProvider)  # config/models.yaml: default_provider
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
