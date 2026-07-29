"""LLM provider katmanının veri modelleri — saf veri, iş mantığı içermez.

`LLMRequest`, tek bir çağrının tüm parametrelerini taşır; hem `BaseLLMProvider.generate()`'e
geçirilir hem de `cache.make_cache_key()` tarafından deterministik bir cache anahtarı
üretmek için kullanılır (bkz. `cache.py`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """Bir `generate()`/`stream()` çağrısının tüm girdisi. Agent kodu bunu inşa eder;
    provider bunun dışında hiçbir örtük durum (ör. konuşma geçmişi) tutmaz — her çağrı
    kendi içinde tam bağımsızdır (stateless), bu da cache/retry/test edilebilirliği basitleştirir.
    """

    model_config = ConfigDict(frozen=True)

    system_prompt: str
    messages: list[LLMMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = 2000
    fallback_models: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    content: str
    model: str
    """Yanıtı fiilen üreten model — `request.model` başarısız olup bir `fallback_models`
    girdisi kullanıldıysa `request.model`'den farklı olabilir."""
    provider: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str | None = None


class LLMStreamChunk(BaseModel):
    delta: str
    finish_reason: str | None = None
