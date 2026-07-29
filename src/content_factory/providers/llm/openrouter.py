"""OpenRouter implementasyonu — `BaseLLMProvider`'ın somut, gerçek HTTP çağrısı yapan alt sınıfı.

OpenRouter, `"anthropic/claude-sonnet-5"`, `"google/gemini-2.5-flash"`,
`"openai/gpt-5"` gibi `provider/model` string'leriyle tek bir OpenAI-uyumlu API
üzerinden çoklu sağlayıcı sunar — bu yüzden v1'de tek bu implementasyon, tam
provider bağımsızlığı sağlar (bkz. ARCHITECTURE.md §9).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

import httpx

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.cache import LLMCache
from content_factory.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMInsufficientCreditError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from content_factory.providers.llm.models import LLMRequest, LLMResponse, LLMStreamChunk, TokenUsage
from content_factory.providers.llm.rate_limit import parse_retry_after
from content_factory.providers.llm.retry import RetryPolicy
from content_factory.providers.llm.token_counter import TokenCounter

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
"""Tek yerden yönetilen varsayılan endpoint — kodun başka hiçbir yerinde bu URL
hardcode edilmez; testlerde/self-hosted proxy'lerde `base_url` parametresiyle değiştirilir."""


class OpenRouterProvider(BaseLLMProvider):
    name = "openrouter"
    default_api_key_env = "OPENROUTER_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 120.0,
        retry_policy: RetryPolicy | None = None,
        cache: LLMCache | None = None,
        token_counter: TokenCounter | None = None,
        client: httpx.Client | None = None,
        app_title: str = "Content Factory",
        **kwargs: object,
    ) -> None:
        super().__init__(
            retry_policy=retry_policy, cache=cache, token_counter=token_counter, **kwargs
        )
        self._api_key = (
            api_key if api_key is not None else os.environ.get(self.default_api_key_env)
        )

        if client is not None:
            self._client = client
        else:
            headers = {"Content-Type": "application/json", "X-Title": app_title}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, headers=headers)

    def close(self) -> None:
        self._client.close()

    # ---------------------------------------------------------------------------- generate

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self._require_api_key()
        payload = self._build_payload(request, model=model, stream=False)

        response = self._post(payload)
        data = response.json()
        choice = data["choices"][0]
        usage_data = data.get("usage") or {}

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", model),
            provider=self.name,
            usage=TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
            finish_reason=choice.get("finish_reason"),
        )

    # ------------------------------------------------------------------------------ stream

    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
        self._require_api_key()
        payload = self._build_payload(request, model=request.model, stream=True)

        self._logger.info(
            f"llm_stream_start agent={agent_name} run_id={run_id} model={request.model}"
        )
        try:
            with self._client.stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    response.read()  # gövdeyi hata mesajı için oku (stream henüz tüketilmedi)
                    self._raise_for_status(response, model=request.model)
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[len("data: ") :].strip()
                    if data_str == "[DONE]":
                        break
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    finish_reason = chunk["choices"][0].get("finish_reason")
                    yield LLMStreamChunk(
                        delta=delta.get("content", ""), finish_reason=finish_reason
                    )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"OpenRouter stream zaman aşımına uğradı (model={request.model})"
            ) from exc
        except httpx.ConnectError as exc:
            raise LLMProviderUnavailableError(f"OpenRouter'a bağlanılamadı: {exc}") from exc

    # ------------------------------------------------------------------------ health_check

    def health_check(self) -> bool:
        """Asla exception fırlatmaz — başarısızlık `False` olarak döner."""
        if not self._api_key:
            self._logger.warning("health_check: OPENROUTER_API_KEY tanımlı değil")
            return False
        try:
            response = self._client.get("/models")
            return response.status_code == 200
        except httpx.HTTPError as exc:
            self._logger.warning(f"health_check başarısız: {exc}")
            return False

    # ------------------------------------------------------------------------------ dahili

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise LLMAuthenticationError(
                f"{self.default_api_key_env} tanımlı değil — OpenRouter'a istek gönderilemez"
            )

    @staticmethod
    def _build_payload(request: LLMRequest, *, model: str, stream: bool) -> dict[str, object]:
        messages = [{"role": "system", "content": request.system_prompt}]
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)
        return {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        model = str(payload["model"])
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"OpenRouter isteği zaman aşımına uğradı (model={model})"
            ) from exc
        except httpx.ConnectError as exc:
            raise LLMProviderUnavailableError(f"OpenRouter'a bağlanılamadı: {exc}") from exc
        self._raise_for_status(response, model=model)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response, *, model: str) -> None:
        status = response.status_code
        if status in (401, 403):
            raise LLMAuthenticationError(
                f"OpenRouter kimlik doğrulama hatası ({status}, model={model})"
            )
        if status == 402:
            # Bakiye yetersiz. Retry edilebilir bir hata gibi görünmemeli — aksi halde
            # her agent çağrısı boşuna 3 kez denenip yalnızca gecikme üretir.
            raise LLMInsufficientCreditError(
                f"OpenRouter bakiyesi bu model için yetersiz (model={model}). "
                f"openrouter.ai/credits üzerinden bakiye ekleyin veya config/models.yaml "
                f"içinde daha ucuz bir model seçin. Sağlayıcı yanıtı: {response.text}"
            )
        if status == 429:
            retry_after = parse_retry_after(response.headers.get("retry-after"))
            raise LLMRateLimitError(
                f"OpenRouter rate limit (model={model})", retry_after=retry_after
            )
        if status in (400, 404, 422):
            raise LLMInvalidRequestError(
                f"Geçersiz istek ({status}, model={model}): {response.text}"
            )
        if status >= 500:
            raise LLMProviderUnavailableError(
                f"OpenRouter sunucu hatası ({status}, model={model})"
            )
        if status >= 400:
            raise LLMProviderUnavailableError(
                f"OpenRouter beklenmeyen hata ({status}, model={model})"
            )
