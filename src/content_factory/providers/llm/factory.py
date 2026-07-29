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
from collections.abc import Iterator

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.cache import LLMCache
from content_factory.providers.llm.exceptions import UnknownProviderError
from content_factory.providers.llm.groq import GroqProvider
from content_factory.providers.llm.models import LLMRequest, LLMResponse, LLMStreamChunk
from content_factory.providers.llm.openrouter import OpenRouterProvider
from content_factory.providers.llm.replicate import ReplicateProvider
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
    max_rate_limit_wait_seconds: float = 0.0,
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
        max_rate_limit_wait_seconds=max_rate_limit_wait_seconds,
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
        max_rate_limit_wait_seconds=float(settings.engine.retries.rate_limit_max_wait_seconds),
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
        max_rate_limit_wait_seconds=float(settings.engine.retries.rate_limit_max_wait_seconds),
    )


class AgentScopedLLMProvider(BaseLLMProvider):
    name = "agent_scoped"
    default_api_key_env = "OPENROUTER_API_KEY"

    def __init__(
        self,
        providers: dict[str, BaseLLMProvider],
        default_provider: BaseLLMProvider,
    ) -> None:
        super().__init__()
        self._providers = providers
        self._default_provider = default_provider

    def generate(self, request: LLMRequest, *, agent_name: str, run_id: str) -> LLMResponse:
        provider = self._providers.get(agent_name, self._default_provider)
        return provider.generate(request, agent_name=agent_name, run_id=run_id)

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        raise NotImplementedError("AgentScopedLLMProvider does not implement _do_generate")

    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
        provider = self._providers.get(agent_name, self._default_provider)
        yield from provider.stream(request, agent_name=agent_name, run_id=run_id)

    def health_check(self) -> bool:
        return all(provider.health_check() for provider in self._providers.values())

    def close(self) -> None:
        closed = set()
        for provider in self._providers.values():
            if provider not in closed:
                provider.close()
                closed.add(provider)
        if self._default_provider not in closed:
            self._default_provider.close()

    def provider_for(self, agent_name: str) -> BaseLLMProvider:
        return self._providers.get(agent_name, self._default_provider)


def create_agent_scoped_llm_provider(
    settings: Settings, *, cache: LLMCache | None = None
) -> BaseLLMProvider:
    """Agent başına uygun sağlayıcıyı seçip tek bir wrapper provider içinde paketler."""
    provider_instances: dict[str, BaseLLMProvider] = {}
    agent_providers: dict[str, BaseLLMProvider] = {}

    # `image_generator` için konfigürasyon LLM provider yerine özel bir ImageProvider kullanır.
    non_llm_agents = {"image_generator"}

    for agent_name in settings.models.agents:
        if agent_name in non_llm_agents:
            continue

        agent_cfg = settings.models.for_agent(agent_name)
        provider_name = agent_cfg.provider or settings.models.default_provider
        if provider_name not in provider_instances:
            provider_instances[provider_name] = _build_from_settings(
                provider_name,
                timeout_seconds=float(settings.engine.timeouts.llm_call_seconds),
                max_retries=settings.engine.retries.llm_call_max_retries,
                cache=cache,
                max_rate_limit_wait_seconds=float(
                    settings.engine.retries.rate_limit_max_wait_seconds
                ),
            )
        agent_providers[agent_name] = provider_instances[provider_name]

    default_provider = provider_instances.get(
        settings.models.default_provider,
        _build_from_settings(
            settings.models.default_provider,
            timeout_seconds=float(settings.engine.timeouts.llm_call_seconds),
            max_retries=settings.engine.retries.llm_call_max_retries,
            cache=cache,
            max_rate_limit_wait_seconds=float(
                settings.engine.retries.rate_limit_max_wait_seconds
            ),
        ),
    )
    return AgentScopedLLMProvider(agent_providers, default_provider)


register_provider("openrouter", OpenRouterProvider)
register_provider("groq", GroqProvider)
register_provider("replicate", ReplicateProvider)
