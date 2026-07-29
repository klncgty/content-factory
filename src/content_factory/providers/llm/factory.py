"""LLM provider'ları isme göre inşa eden merkezi factory.

Agent kodu asla `OpenRouterProvider(...)` gibi somut bir sınıfı doğrudan import etmez —
her zaman `create_llm_provider_for_agent(settings, agent_role)` çağırır. Hangi sağlayıcının
kullanılacağı tamamen `config/models.yaml` / `brands/{brand}/models.yaml`'dandır.

Yeni bir sağlayıcı eklemek (ör. doğrudan OpenAI, Ollama): `BaseLLMProvider`'ı implemente
eden bir sınıf yaz, `register_provider("openai", OpenAIProvider)` ile kaydet. Var olan hiçbir
agent kodu değişmez (bkz. `providers/llm/README.md`).
"""

from __future__ import annotations

import os

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.cache import LLMCache
from content_factory.providers.llm.exceptions import UnknownProviderError
from content_factory.providers.llm.openrouter import OpenRouterProvider
from content_factory.providers.llm.retry import RetryPolicy
from content_factory.settings.loader import Settings

_REGISTRY: dict[str, type[BaseLLMProvider]] = {}


def register_provider(name: str, provider_cls: type[BaseLLMProvider]) -> None:
    """Yeni bir sağlayıcıyı factory'ye kaydeder. `create_llm_provider(name, ...)` bundan
    sonra bu sınıfı inşa edebilir."""
    _REGISTRY[name] = provider_cls


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def create_llm_provider(provider_name: str, **kwargs: object) -> BaseLLMProvider:
    """Düşük seviye: `provider_name` + sağlayıcıya özgü kwargs ile doğrudan inşa eder.
    Testlerde ve `create_llm_provider_for_agent`'ın içinde kullanılır."""
    provider_cls = _REGISTRY.get(provider_name)
    if provider_cls is None:
        raise UnknownProviderError(
            f"Bilinmeyen LLM provider: {provider_name!r} (kayıtlı: {available_providers()})"
        )
    return provider_cls(**kwargs)  # type: ignore[arg-type]


def _build_from_settings(
    provider_name: str,
    *,
    timeout_seconds: float,
    max_retries: int,
    cache: LLMCache | None,
) -> BaseLLMProvider:
    provider_cls = _REGISTRY.get(provider_name)
    if provider_cls is None:
        raise UnknownProviderError(
            f"Bilinmeyen LLM provider: {provider_name!r} (kayıtlı: {available_providers()})"
        )
    api_key = os.environ.get(provider_cls.default_api_key_env)
    retry_policy = RetryPolicy(max_attempts=max_retries)
    return provider_cls(
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        retry_policy=retry_policy,
        cache=cache,
    )


def create_llm_provider_for_agent(
    settings: Settings, agent_role: str, *, cache: LLMCache | None = None
) -> BaseLLMProvider:
    """`config/models.yaml`'daki (+ marka override'ı) `agent_role` için tanımlı
    provider'ı inşa eder — model seçimi burada değil, her `generate()` çağrısında
    `LLMRequest.model` ile yapılır (bkz. `base.py`)."""
    agent_cfg = settings.models.for_agent(agent_role)
    provider_name = agent_cfg.provider or settings.models.default_provider
    return _build_from_settings(
        provider_name,
        timeout_seconds=float(settings.engine.timeouts.llm_call_seconds),
        max_retries=settings.engine.retries.llm_call_max_retries,
        cache=cache,
    )


def create_default_llm_provider(
    settings: Settings, *, cache: LLMCache | None = None
) -> BaseLLMProvider:
    """Marka config'indeki `models.yaml: default_provider`'ı inşa eder. Bugün tüm text
    agent'ları aynı sağlayıcıyı (openrouter) paylaştığı için CLI/Orchestrator bu tek
    instance'ı tüm agent'lara enjekte eder — bkz. `AgentContext.llm`."""
    return _build_from_settings(
        settings.models.default_provider,
        timeout_seconds=float(settings.engine.timeouts.llm_call_seconds),
        max_retries=settings.engine.retries.llm_call_max_retries,
        cache=cache,
    )


register_provider("openrouter", OpenRouterProvider)
