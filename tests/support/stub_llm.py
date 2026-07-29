from __future__ import annotations

from collections.abc import Iterator

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.models import LLMRequest, LLMResponse, LLMStreamChunk


class StubLLMProvider(BaseLLMProvider):
    """Agent iş mantığı testleri için basit, kontrol edilebilir bir LLM sahtesi.

    `tests/providers/llm/conftest.py::FakeLLMProvider`'dan farkı: o, `BaseLLMProvider`'ın
    retry/fallback/rate-limit makinesini test etmek için tasarlandı (side_effects kuyruğu,
    model bazlı davranış). Bu sınıf ise agent kodunun "LLM'den şu yanıtı aldım, onunla ne
    yapıyorum" mantığını test etmek için — sırayla verilen yanıtları döndürür, hangi
    `LLMRequest`'lerin gönderildiğini `self.requests`'te kaydeder.
    """

    name = "stub"
    default_api_key_env = "STUB_API_KEY"

    def __init__(self, *, responses: list[str] | str | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if isinstance(responses, str):
            responses = [responses]
        self._responses: list[str] = list(responses or [])
        self.requests: list[LLMRequest] = []

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self.requests.append(request)
        content = self._responses.pop(0) if self._responses else ""
        return LLMResponse(content=content, model=model, provider=self.name)

    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
        content = self._responses.pop(0) if self._responses else ""
        yield LLMStreamChunk(delta=content, finish_reason="stop")

    def health_check(self) -> bool:
        return True
