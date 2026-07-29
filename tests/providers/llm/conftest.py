from __future__ import annotations

from collections.abc import Iterator

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.models import LLMRequest, LLMResponse, LLMStreamChunk


class FakeLLMProvider(BaseLLMProvider):
    """`BaseLLMProvider.generate()`'in template-method mantığını (retry/fallback/
    rate-limit/cache) gerçek ağ olmadan test etmek için sahte bir implementasyon.

    `side_effects={"model-a": [TimeoutError(...), <LLMResponse>]}` gibi bir sözlükle
    her modelin ardışık çağrılarda ne döndüreceği/fırlatacağı kontrol edilir.
    """

    name = "fake"
    default_api_key_env = "FAKE_API_KEY"

    def __init__(
        self, *, side_effects: dict[str, list[object]] | None = None, **kwargs: object
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.calls: list[str] = []
        self._side_effects = {k: list(v) for k, v in (side_effects or {}).items()}

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self.calls.append(model)
        queue = self._side_effects.get(model)
        if not queue:
            return LLMResponse(content=f"ok:{model}", model=model, provider=self.name)
        effect = queue.pop(0)
        if isinstance(effect, Exception):
            raise effect
        assert isinstance(effect, LLMResponse)
        return effect

    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
        yield LLMStreamChunk(delta="fake-chunk")

    def health_check(self) -> bool:
        return True
