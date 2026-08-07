"""Groq LLM provider.

Groq'un OpenAI uyumlu Chat Completions API'sini kullanır. Writer ajanı bu
sağlayıcıyı `brands/oleart/models.yaml` içinde `provider: groq` olarak
seçtiğinde devreye girer.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import httpx

from content_factory.providers.llm.base import BaseLLMProvider
from content_factory.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMInsufficientCreditError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMRequestTooLargeError,
    LLMTimeoutError,
)
from content_factory.providers.llm.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from content_factory.providers.llm.rate_limit import parse_groq_duration, parse_retry_after

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
                "User-Agent": "content-factory/1.0",
                "X-Title": app_title,
            }
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, headers=headers)

    def close(self) -> None:
        self._client.close()

    MIN_USABLE_MAX_TOKENS = 512
    """Daraltma sonrası anlamlı bir yanıt için gereken asgari bütçe. Bunun altına düşmek
    gerekiyorsa istek zaten model için fazla büyüktür; operatöre net hata verilir."""

    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        self._require_api_key()
        payload = self._build_payload(request, model=model)
        # İstek en fazla iki kez düzeltilip yeniden denenir. Düzeltmelerin hepsi
        # `LLMInvalidRequestError` ailesinde olduğu için tek yerde ayrıştırılır; birden
        # fazla tur gerekmesinin sebebi, bir modelin hem `reasoning_format`'ı hem
        # `response_format`'ı reddedebilmesi (Groq 400'de yalnızca ilk sorunu bildirir).
        for _ in range(2):
            try:
                response = self._post(payload)
                break
            except LLMInvalidRequestError as exc:
                payload = self._correct_payload(payload, exc, model=model)
        else:
            response = self._post(payload)
        data = response.json()
        content = self._extract_output_text(data)
        usage_data = data.get("usage", {}) or {}

        finish_reason = "stop"
        choices = data.get("choices", [])
        if choices and isinstance(choices, list) and len(choices) > 0:
            finish_reason = choices[0].get("finish_reason") or "stop"

        if not content.strip():
            # 200 OK + boş içerik: gpt-oss gibi reasoning modelleri max_tokens'ı düşünme
            # adımında tüketirse olur. Boş string'i agent'a vermek orada ham bir
            # AgentOutputParsingError'a dönüşüp pipeline'ı öldürüyordu; geçici sayıp
            # retry/fallback'in görebileceği bir hataya çeviriyoruz (openrouter.py ile aynı).
            hint = (
                " — model token bütçesini yanıt üretmeden tüketti; bu agent için "
                "max_tokens'ı artırın veya reasoning yapmayan bir model seçin"
                if finish_reason == "length"
                else ""
            )
            raise LLMProviderUnavailableError(
                f"Groq boş içerik döndürdü (model={model}, finish_reason={finish_reason}){hint}"
            )

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

    def _correct_payload(
        self, payload: dict[str, object], exc: LLMInvalidRequestError, *, model: str
    ) -> dict[str, object]:
        """400 alan bir payload'ı, hatanın söylediğine göre düzeltip döndürür.
        Düzeltilemeyen bir 400'de orijinal hata yükseltilir."""
        if isinstance(exc, LLMRequestTooLargeError):
            # Aynı agent'ın prompt'u çalışma anında büyüyebiliyor (ör. Writer'ın
            # revizyon turunda önceki taslak da prompt'a giriyor) ve statik bir
            # max_tokens değeri her iki durumu birden karşılayamıyor. Groq aşımın
            # miktarını bildirdiği için istek o kadar daraltılır: yarısı üretilmiş
            # bir makaleyi çöpe atmaktansa biraz daha kısa bir yanıt yeğdir.
            return self._shrink_max_tokens(payload, exc, model=model)
        for parameter in ("reasoning_format", "response_format"):
            # Model ailesi tahmini yanlıştı: bu model parametreyi desteklemiyor.
            # `response_format` düşürüldüğünde JSON garantisi prompt seviyesine iner —
            # çağıran taraf (`utils.json_llm.parse_llm_json`) bunu zaten kaldırabiliyor.
            if parameter in payload and parameter in str(exc):
                self._logger.warning(
                    f"{parameter} desteklenmiyor model={model} — parametresiz denenecek"
                )
                return {key: value for key, value in payload.items() if key != parameter}
        raise exc

    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
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

    INLINE_REASONING_MODEL_PREFIXES = ("qwen/", "deepseek-")
    """Düşünme metnini `content` içine `<think>...</think>` olarak gömen model aileleri.

    Bu modellerde JSON isteyen agent'lar (Editor, ScopeGuard, SEO) bozuk yanıt alıyor;
    yanıt max_tokens'a takılırsa geriye kapanmamış bir düşünme bloğundan başka bir şey
    kalmıyor. Groq'un `reasoning_format: "parsed"` parametresi düşünmeyi ayrı bir alana
    taşıyıp `content`'i temiz bırakır. Parametre yalnızca reasoning modellerinde geçerli
    (llama gibi modeller 400 döndürür), bu yüzden aileye göre gönderilir; yine de yanlış
    tahmine karşı `_post` 400'de parametresiz bir kez daha dener."""

    def _build_payload(self, request: LLMRequest, *, model: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model,
            "messages": self._build_messages(request.system_prompt, request.messages),
            "temperature": float(request.temperature),
            "max_tokens": int(request.max_tokens),
        }
        if model.startswith(self.INLINE_REASONING_MODEL_PREFIXES):
            payload["reasoning_format"] = "parsed"
        if request.response_format == "json_object":
            # Yapısal çıktı: model JSON üretmeye gramer seviyesinde zorlanır. Groq bu
            # kipte prompt'un "JSON" sözcüğünü içermesini şart koşar — JSON isteyen
            # agent'ların prompt'ları zaten şemayı yazdığı için bu sağlanmış durumda.
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Groq isteği zaman aşımına uğradı (model={payload.get('model')})"
            ) from exc
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
            # Gövde ve rate-limit başlıkları mesaja KATILIR: sınırın hangisi olduğu
            # (dakikalık token / günlük istek), limitin ve kullanımın ne olduğu yalnızca
            # orada yazıyor. Bunlar olmadan uzak bir ortamdaki (CI) 429'u teşhis etmek
            # imkânsızdı — yalnızca "rate limit" görünüyordu.
            limits = " ".join(
                f"{key}={value}"
                for key, value in response.headers.items()
                if key.lower().startswith("x-ratelimit")
            )
            raise LLMRateLimitError(
                f"Groq rate limit (status={status}): {response.text[:400]} [{limits}]",
                retry_after=self._retry_after_seconds(response),
            )
        if status == 413:
            # "Request too large": prompt + max_tokens, modelin dakikalık token tavanını
            # (TPM) tek bir istekte aşıyor. Beklemek çözmez, istek küçülmeli.
            limit, requested = self._parse_token_overshoot(response.text)
            raise LLMRequestTooLargeError(
                f"Groq isteği modelin token tavanını aşıyor ({status}) — bu agent için "
                f"max_tokens'ı düşürün veya daha yüksek limitli bir model seçin: "
                f"{response.text}",
                limit=limit,
                requested=requested,
            )
        if status in (400, 404):
            raise LLMInvalidRequestError(
                f"Groq geçersiz istek ({status}): {response.text}"
            )
        if status >= 500:
            raise LLMProviderUnavailableError(f"Groq sunucu hatası ({status})")
        if status >= 400:
            raise LLMProviderUnavailableError(f"Groq beklenmeyen hata ({status})")

    _TPM_OVERSHOOT = re.compile(r"Limit\s+(\d+),\s*Requested\s+(\d+)", re.IGNORECASE)

    @classmethod
    def _parse_token_overshoot(cls, body: str) -> tuple[int | None, int | None]:
        """413 gövdesindeki "... Limit 8000, Requested 8684 ..." değerlerini çıkarır."""
        match = cls._TPM_OVERSHOOT.search(body or "")
        if match is None:
            return None, None
        return int(match.group(1)), int(match.group(2))

    def _shrink_max_tokens(
        self, payload: dict[str, object], exc: LLMRequestTooLargeError, *, model: str
    ) -> dict[str, object]:
        """413'ten sonra `max_tokens`'ı aşım kadar (+ küçük bir pay) daraltılmış yeni bir
        payload döndürür. Daraltma mümkün değilse orijinal hatayı yükseltir."""
        if exc.limit is None or exc.requested is None:
            raise exc
        overshoot = exc.requested - exc.limit
        current = int(payload.get("max_tokens", 0))
        reduced = current - overshoot - 64  # pay: token sayımı tahminî
        if reduced < self.MIN_USABLE_MAX_TOKENS:
            raise exc
        self._logger.warning(
            f"request_too_large model={model} max_tokens {current} -> {reduced} "
            f"(limit={exc.limit}, requested={exc.requested})"
        )
        return {**payload, "max_tokens": reduced}

    MAX_TRUSTED_RETRY_AFTER_SECONDS = 60.0
    """`x-ratelimit-reset-tokens`, kovanın TAMAMEN dolacağı anı bildirir — isteği
    karşılayacak kadar token'ın birikeceği anı değil. Bu yüzden değer sistematik olarak
    karamsardır (ölçüm: tek bir büyük istekten sonra 1265s). Olduğu gibi kullanmak modeli
    tüm run boyunca devre dışı bırakıyordu; bu tavandan sonra yeniden denemek daha ucuz:
    hâlâ doluysa yalnızca bir 429 daha alırız."""

    @classmethod
    def _retry_after_seconds(cls, response: httpx.Response) -> float | None:
        """429'da ne kadar beklenmesi gerektiğini çıkarır.

        Groq standart `retry-after` başlığını her zaman göndermiyor; sınır model başına
        dakikalık token (TPM) olduğu için asıl bilgi `x-ratelimit-reset-tokens`
        başlığında ("18.285s", "4m19.2s" biçiminde) geliyor. Bu değer olmadan
        `BaseLLMProvider` ne kadar bekleyeceğini bilemez ve rate limit'i bekleyip
        atlatamaz."""
        explicit = parse_retry_after(response.headers.get("retry-after"))
        if explicit is not None:
            return explicit
        reset = parse_groq_duration(response.headers.get("x-ratelimit-reset-tokens"))
        if reset is None:
            return None
        return min(reset, cls.MAX_TRUSTED_RETRY_AFTER_SECONDS)

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