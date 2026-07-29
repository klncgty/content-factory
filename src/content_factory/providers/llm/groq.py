"""Groq LLM provider.

Groq'un OpenAI uyumlu Chat Completions API'sini kullanır. Writer ajanı bu
sağlayıcıyı `brands/oleart/models.yaml` içinde `provider: groq` olarak
seçtiğinde devreye girer.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import httpx

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMInsufficientCreditError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from content_factory.providers.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMStreamChunk, TokenUsage


DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(BaseLLMProvider):
    name = "groq"
    default_api_key_env = "GROQ_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 120.0,
        retry_policy=None,
        cache=None,
        token_counter=None,
        client: httpx.Client | None = None,
        app_title: str = "Content Factory",
        **kwargs: object,
    ) -> None:
        super().__init__(
            retry_policy=retry_policy,
            cache=cache,
            token_counter=token_counter,
            **kwargs,
        )
        self._api_key = api_key if api_key is not None else os.environ.get(self.default_api_key_env)
        if client is not None:
            self._client = client
        else:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"content-factory/1.0",
                "X-Title": app_title,
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, headers=headers)

    def close(self) -> None:
        self._client.close()

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self._require_api_key()
        payload = self._build_payload(request, model=model)
        response = self._post(payload)
        data = response.json()
        content = self._extract_output_text(data)
        usage_data = data.get("usage", {}) or {}
        
        finish_reason = "stop"
        choices = data.get("choices", [])
        if choices and isinstance(choices, list) and len(choices) > 0:
            finish_reason = choices[0].get("finish_reason") or "stop"

        return LLMResponse(
            content=content,
            model=str(data.get("model", model)),
            provider=self.name,
            usage=TokenUsage(
                prompt_tokens=int(usage_data.get("prompt_tokens", 0)),
                completion_tokens=int(usage_data.get("completion_tokens", 0)),
                total_tokens=int(usage_data.get("total_tokens", 0)),
            ),
            finish_reason=finish_reason,
        )

    def stream(self, request: LLMRequest, *, agent_name: str, run_id: str) -> Iterator[LLMStreamChunk]:
        response = self._do_generate(request, model=request.model)
        yield LLMStreamChunk(delta=response.content, finish_reason=response.finish_reason)

    def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            response = self._client.get("/models")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise LLMAuthenticationError(
                f"{self.default_api_key_env} tanımlı değil — Groq API isteği gönderilemez"
            )

    @staticmethod
    def _build_messages(system_prompt: str, messages: list[LLMMessage]) -> list[dict[str, str]]:
        formatted_messages: list[dict[str, str]] = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for message in messages:
            formatted_messages.append({
                "role": message.role.lower(),
                "content": message.content
            })
        return formatted_messages

    def _build_payload(self, request: LLMRequest, *, model: str) -> dict[str, object]:
        return {
            "model": model,
            "messages": self._build_messages(request.system_prompt, request.messages),
            "temperature": float(request.temperature),
            "max_tokens": int(request.max_tokens),
        }

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Groq isteği zaman aşımına uğradı (model={payload.get('model')})") from exc
        except httpx.ConnectError as exc:
            raise LLMProviderUnavailableError(f"Groq'a bağlanılamadı: {exc}") from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status in (401, 403):
            raise LLMAuthenticationError(f"Groq kimlik doğrulama hatası ({status})")
        if status == 402:
            raise LLMInsufficientCreditError(
                f"Groq bakiyesi veya izinleri yetersiz (status={status})"
            )
        if status == 429:
            raise LLMRateLimitError(f"Groq rate limit (status={status})")
        if status in (400, 404):
            raise LLMInvalidRequestError(
                f"Groq geçersiz istek ({status}): {response.text}"
            )
        if status >= 500:
            raise LLMProviderUnavailableError(f"Groq sunucu hatası ({status})")
        if status >= 400:
            raise LLMProviderUnavailableError(f"Groq beklenmeyen hata ({status})")

    @staticmethod
    def _extract_output_text(data: dict[str, object]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
        return ""