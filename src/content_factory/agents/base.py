"""Tüm agent'ların türediği ortak taban — bkz. ARCHITECTURE.md §4, §9 (DI).

Agent'lar birbirini asla import etmez; ihtiyaç duydukları her şey (config, logger,
provider'lar) `AgentContext` üzerinden Orchestrator tarafından enjekte edilir.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from content_factory.domain.exceptions import AgentConfigurationError, AgentValidationError
from content_factory.knowledge.loader import BrandKnowledge
from content_factory.prompts.loader import PromptLoader, PromptSet
from content_factory.providers.git import GitProvider
from content_factory.providers.image import ImageProvider
from content_factory.providers.llm import BaseLLMProvider, LLMMessage, LLMRequest
from content_factory.settings.loader import Settings
from content_factory.settings.schemas import AgentModelConfig
from content_factory.state.store import StateStore
from content_factory.utils.logging import get_logger

__all__ = ["AgentConfigurationError", "AgentContext", "AgentValidationError", "BaseAgent"]


@dataclass
class AgentContext:
    """Bir pipeline run'ı için ortak bağlam. Orchestrator, her agent'ı bu context ile
    kurar (constructor injection) — agent'lar `Settings`/provider'ları/knowledge base'i
    başka hiçbir yerden edinemez, bu da onları test edilebilir ve birbirinden bağımsız
    kılar."""

    brand: str
    run_id: str
    settings: Settings
    knowledge: BrandKnowledge | None = None
    prompts: PromptLoader | None = None
    llm: BaseLLMProvider | None = None
    image: ImageProvider | None = None
    git: GitProvider | None = None
    state: StateStore | None = None


class BaseAgent[TIn, TOut](ABC):
    """Her agent'ın uyduğu ortak arayüz: `load_config()`, `validate()`, `run()`.

    Alt sınıflar yalnızca `name` ve `run()`'ı tanımlar. `__call__`, `validate -> run`
    sırasını ve standart start/done loglamasını sağlar; agent'lar bunu tekrar yazmaz.
    """

    name: str

    # `render_user(**kwargs)`'a geçirilen anahtarların tam kümesi — `prompts/{name}/user.md`
    # içindeki $değişkenlerle birebir eşleşmeli. Prompt kullanmayan agent'lar (ör. Linker,
    # Publisher) bunu boş bırakır; tests/test_prompts.py bu sözleşmeyi tüm agent'lar için
    # doğrular (bkz. ARCHITECTURE.md — prompt/kod uyuşmazlığı artık `Template.substitute`
    # ile sessiz kalmıyor, KeyError fırlatıyor).
    prompt_vars: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, context: AgentContext) -> None:
        self.context = context
        self.logger: logging.Logger = get_logger(f"agents.{self.name}")
        self._config: AgentModelConfig | None = None
        self._prompts: PromptSet | None = None

    def load_config(self) -> AgentModelConfig:
        """`config/models.yaml` (+ varsa marka override'ı) içinden bu agent'a ait
        model/parametre bölümünü döndürür — bkz. ARCHITECTURE.md §14."""
        if self._config is None:
            self._config = self.context.settings.models.for_agent(self.name)
        return self._config

    def load_prompts(self) -> PromptSet:
        """`prompts/{self.name}/` altındaki system/user/examples dosyalarını döndürür
        (bkz. `content_factory.prompts.loader`). Yalnızca LLM çağıran agent'lar kullanır;
        `AgentContext.prompts` enjekte edilmemişse (ör. LLM kullanmayan bir agent'ın
        testinde) `AgentConfigurationError` fırlatır."""
        if self._prompts is None:
            if self.context.prompts is None:
                raise AgentConfigurationError(
                    f"{type(self).__name__}: AgentContext.prompts enjekte edilmemiş"
                )
            self._prompts = self.context.prompts.load(self.name)
        return self._prompts

    # ------------------------------------------------------ ortak bağımlılık kontrolleri
    # Birden çok agent'ın tekrar tekrar yazacağı "bağımlılık enjekte edilmiş mi" kontrolü
    # tek bir yerde — hangi agent'ın hangi bağımlılığı eksik olduğu net bir hatayla söylenir.

    def require_knowledge(self) -> BrandKnowledge:
        if self.context.knowledge is None:
            raise AgentConfigurationError(
                f"{type(self).__name__}: AgentContext.knowledge enjekte edilmemiş"
            )
        return self.context.knowledge

    def require_prompts(self) -> PromptLoader:
        """`load_prompts()` bu agent'ın KENDİ prompt setini döndürür; bu metod ise
        loader'ın kendisini döndürür — başka bir bileşenin (ör. `ScopeGuard.post_check`)
        prompt'unu yüklemesi gerektiğinde kullanılır."""
        if self.context.prompts is None:
            raise AgentConfigurationError(
                f"{type(self).__name__}: AgentContext.prompts enjekte edilmemiş"
            )
        return self.context.prompts

    def require_llm(self) -> BaseLLMProvider:
        if self.context.llm is None:
            raise AgentConfigurationError(
                f"{type(self).__name__}: AgentContext.llm enjekte edilmemiş"
            )
        return self.context.llm

    def require_state(self) -> StateStore:
        if self.context.state is None:
            raise AgentConfigurationError(
                f"{type(self).__name__}: AgentContext.state enjekte edilmemiş"
            )
        return self.context.state

    def require_image_provider(self) -> ImageProvider:
        if self.context.image is None:
            raise AgentConfigurationError(
                f"{type(self).__name__}: AgentContext.image enjekte edilmemiş — henüz somut "
                "bir ImageProvider yapılandırılmadı (bkz. ROADMAP.md)"
            )
        return self.context.image

    def require_git_provider(self) -> GitProvider:
        if self.context.git is None:
            raise AgentConfigurationError(
                f"{type(self).__name__}: AgentContext.git enjekte edilmemiş"
            )
        return self.context.git

    def build_llm_request(
        self,
        *,
        system_prompt: str,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMRequest:
        """`load_config()`'ten model/temperature/max_tokens/fallback_models'ı okuyup
        bir `LLMRequest` inşa eder — her agent'ın kendi başına tekrarlamaması için."""
        config = self.load_config()
        if not config.model:
            raise AgentConfigurationError(
                f"{type(self).__name__}: config/models.yaml içinde model tanımlı değil"
            )
        return LLMRequest(
            system_prompt=system_prompt,
            messages=messages,
            model=config.model,
            temperature=temperature if temperature is not None else (config.temperature or 0.7),
            max_tokens=max_tokens if max_tokens is not None else (config.max_tokens or 2000),
            fallback_models=config.fallback_models,
        )

    def call_llm(self, *, system_prompt: str, user_message: str, **kwargs: object) -> str:
        """`build_llm_request` + `generate()` + loglama zaten yapılmış ham `content` string'i
        döndüren en sık kullanılan kısayol. JSON bekleyen agent'lar bunun üzerine
        `content_factory.utils.json_llm.parse_llm_json` uygular."""
        llm = self.require_llm()
        request = self.build_llm_request(
            system_prompt=system_prompt,
            messages=[LLMMessage(role="user", content=user_message)],
            **kwargs,  # type: ignore[arg-type]
        )
        response = llm.generate(request, agent_name=self.name, run_id=self.context.run_id)
        return response.content

    def validate(self, input_data: TIn) -> None:
        """Girdi doğrulaması için genişletme noktası. Varsayılan: no-op — alan bazlı
        doğrulama zaten pydantic modelleri tarafından yapılır; alt sınıflar burada yalnızca
        *iş kuralı* doğrulaması ekler (ör. "brief.target_word_count marka sınırları içinde
        mi"). Şu an hiçbir alt sınıf override etmiyor — agent'lar girdi ön koşullarını
        `run()` başında `AgentValidationError` ile kontrol ediyor."""
        return None

    @abstractmethod
    def run(self, input_data: TIn) -> TOut:
        """Agent'ın gerçek işini yaptığı tek yer. Her alt sınıf bunu tanımlamak
        *zorundadır* (ABC)."""

    def __call__(self, input_data: TIn) -> TOut:
        self.validate(input_data)
        self.logger.info(f"start run_id={self.context.run_id}")
        try:
            result = self.run(input_data)
        except Exception as exc:
            # AgentError, LLMError vb. — tüm agent'lar için TEK loglama noktası.
            # Yakalanan hata burada yutulmaz, yalnızca loglanıp yeniden yükseltilir.
            self.logger.error(f"failed run_id={self.context.run_id} error={exc!r}")
            raise
        self.logger.info(f"done run_id={self.context.run_id}")
        return result
