"""Replicate LLM provider — `BaseLLMProvider`'ın Replicate'e konuşan alt sınıfı.

Neden var: Writer, run'ın en ağır LLM tüketicisi (ölçüm: prompt 3.4k + max_tokens 4.2k
≈ 7.7k token, Groq'un gpt-oss-120b tavanı 8k). Tek bir writer çağrısı dakikalık kotayı
doldurduğu için editor retry turlarında ikinci çağrı hep 429 alıyordu. Replicate'te
dakikalık token tavanı yok; aynı model (gpt-oss-120b) burada rate limit'e takılmadan
çalışır.

Sözleşme, `integrations/image_client.py::ReplicateImageProvider` ile aynıdır — Replicate
metin ve görsel için tek bir "prediction" mekanizması kullanır:
    sürüm  : GET  /models/{owner}/{name}  -> latest_version.id  (instance içinde cache'lenir)
    üretim : POST /predictions            gövde: {"version": ..., "input": {...}}
             `Prefer: wait` çoğu çağrıda sonucu tek turda getirir; getirmezse yoklanır.
    çıktı  : output -> token parçalarından oluşan liste; birleştirilerek metne çevrilir.

Replicate'in metin modellerinde ayrı bir `system` rolü yok (şemada yalnızca `prompt`
var), bu yüzden sistem promptu kullanıcı mesajının başına eklenir.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator

import httpx

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMInsufficientCreditError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
)
from content_factory.providers.llm.models import LLMRequest, LLMResponse, LLMStreamChunk, TokenUsage

DEFAULT_BASE_URL = "https://api.replicate.com/v1"
_TERMINAL_STATUSES = ("succeeded", "failed", "canceled")


class ReplicateProvider(BaseLLMProvider):
    name = "replicate"
    default_api_key_env = "REPLICATE_API_KEY"
    fallback_api_key_env = "REPLICATE_API_TOKEN"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 2.0,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        **kwargs: object,
    ) -> None:
        super().__init__(sleep_fn=sleep_fn, **kwargs)  # type: ignore[arg-type]
        self._api_key = (
            api_key
            if api_key is not None
            else (
                os.environ.get(self.default_api_key_env)
                or os.environ.get(self.fallback_api_key_env)
            )
        )
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._client = client or httpx.Client(
            base_url=base_url, timeout=timeout_seconds, headers=headers
        )
        self._timeout_seconds = timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._versions: dict[str, str] = {}

    def close(self) -> None:
        self._client.close()

    # ---------------------------------------------------------------------------- generate

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self._require_api_key()
        prompt = (
            f"{request.system_prompt}\n\n{self._join_messages(request)}"
            if request.system_prompt
            else self._join_messages(request)
        )
        if request.response_format == "json_object":
            # Replicate'in metin modellerinde yapısal çıktı parametresi YOK: prediction
            # input şeması modele aittir ve `response_format` gibi ortak bir alan tanımaz.
            # Sessizce yok saymak yerine loglanır — JSON garantisi burada yalnızca
            # prompt'taki şema talimatı kadardır ve çağıran taraf bunu bilmelidir
            # (bkz. `utils.json_llm.parse_llm_json` kurtarma yolları).
            self._logger.warning(
                f"response_format=json_object Replicate'te desteklenmiyor (model={model}) — "
                "JSON yalnızca prompt seviyesinde garanti edilir"
            )
        payload = {
            "version": self._version_for(model),
            "input": {
                "prompt": prompt,
                "max_tokens": int(request.max_tokens),
                "temperature": float(request.temperature),
            },
        }
        prediction = self._await_completion(
            self._request("POST", "/predictions", model=model, json=payload).json(), model=model
        )

        content = self._join_output(prediction.get("output"))
        if not content.strip():
            # Diğer sağlayıcılarda olduğu gibi boş içerik geçici sayılır: retry/fallback
            # bunu görebilsin, agent'ta ham ayrıştırma hatasına dönüşüp run'ı öldürmesin.
            raise LLMProviderUnavailableError(f"Replicate boş içerik döndürdü (model={model})")

        return LLMResponse(
            content=content,
            model=model,
            provider=self.name,
            usage=self._usage(prediction, prompt=prompt, content=content, model=model),
            finish_reason=str(prediction.get("status")),
        )

    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
        """Replicate SSE akışı destekler ama bu projede hiçbir agent stream kullanmıyor;
        tek parça yanıt tek bir chunk olarak verilir."""
        response = self._do_generate(request, model=request.model)
        yield LLMStreamChunk(delta=response.content, finish_reason=response.finish_reason)

    def health_check(self) -> bool:
        """Asla exception fırlatmaz. `/account` ücretsizdir."""
        if not self._api_key:
            self._logger.warning(f"health_check: {self.default_api_key_env} tanımlı değil")
            return False
        try:
            return self._client.get("/account").status_code == 200
        except httpx.HTTPError as exc:
            self._logger.warning(f"health_check başarısız: {exc}")
            return False

    # ------------------------------------------------------------------------------ dahili

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise LLMAuthenticationError(
                f"{self.default_api_key_env} tanımlı değil — Replicate'e istek gönderilemez"
            )

    @staticmethod
    def _join_messages(request: LLMRequest) -> str:
        return "\n\n".join(message.content for message in request.messages)

    @staticmethod
    def _join_output(output: object) -> str:
        """Replicate metin modelleri çıktıyı token parçaları listesi olarak döndürür."""
        if isinstance(output, str):
            return output
        if isinstance(output, list):
            return "".join(part for part in output if isinstance(part, str))
        return ""

    def _usage(
        self, prediction: dict[str, object], *, prompt: str, content: str, model: str
    ) -> TokenUsage:
        """Replicate token sayısı döndürmez (yalnızca süre), bu yüzden loglardaki
        karşılaştırılabilirlik için heuristik sayaçla tahmin edilir."""
        prompt_tokens = self.count_tokens(prompt, model=model)
        completion_tokens = self.count_tokens(content, model=model)
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    def _version_for(self, model: str) -> str:
        """Sürüm kimliği config'de tutulmaz; ilk kullanımda API'den okunup instance
        ömrü boyunca cache'lenir (run başına bir kez ek istek)."""
        cached = self._versions.get(model)
        if cached:
            return cached
        response = self._request("GET", f"/models/{model}", model=model)
        version = ((response.json().get("latest_version") or {}).get("id")) or ""
        if not version:
            raise LLMInvalidRequestError(
                f"Modelin güncel sürümü okunamadı (model={model}) — `latest_version.id` yok"
            )
        self._versions[model] = str(version)
        return str(version)

    def _await_completion(self, prediction: dict[str, object], *, model: str) -> dict[str, object]:
        deadline = time.monotonic() + self._timeout_seconds
        while str(prediction.get("status")) not in _TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                raise LLMProviderUnavailableError(
                    f"Replicate zaman aşımına uğradı (model={model}, "
                    f"status={prediction.get('status')})"
                )
            self._sleep_fn(self._poll_interval)
            get_url = (prediction.get("urls") or {}).get("get")  # type: ignore[union-attr]
            path = str(get_url) if get_url else f"/predictions/{prediction.get('id')}"
            prediction = self._request("GET", path, model=model).json()

        status = str(prediction.get("status"))
        if status != "succeeded":
            raise LLMProviderUnavailableError(
                f"Replicate tahmini başarısız (model={model}, status={status}): "
                f"{prediction.get('error')}"
            )
        return prediction

    def _request(
        self, method: str, path: str, *, model: str, json: dict[str, object] | None = None
    ) -> httpx.Response:
        headers = {"Prefer": "wait"} if method == "POST" else None
        try:
            response = self._client.request(method, path, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMProviderUnavailableError(
                f"Replicate isteği zaman aşımına uğradı (model={model})"
            ) from exc
        except httpx.ConnectError as exc:
            raise LLMProviderUnavailableError(f"Replicate'e bağlanılamadı: {exc}") from exc
        _raise_for_status(response, model=model)
        return response


def _raise_for_status(response: httpx.Response, *, model: str) -> None:
    status = response.status_code
    if status < 400:
        return
    detail = response.text[:400]
    if status in (401, 403):
        raise LLMAuthenticationError(f"Replicate kimlik doğrulama hatası ({status}): {detail}")
    if status == 402:
        raise LLMInsufficientCreditError(
            f"Replicate bakiyesi yetersiz (model={model}): {detail}"
        )
    if status == 429:
        raise LLMRateLimitError(f"Replicate rate limit (model={model}): {detail}")
    if status in (400, 404, 422):
        raise LLMInvalidRequestError(
            f"Geçersiz istek ({status}, model={model}): {detail}. Model adı `sahip/model` "
            f"biçiminde mi ve bu parametreleri destekliyor mu?"
        )
    raise LLMProviderUnavailableError(f"Replicate sunucu hatası ({status}, model={model})")
