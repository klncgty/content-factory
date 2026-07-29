"""Tüm LLM sağlayıcılarının ortak tabanı.

`generate()` bir **template method**'tur: cache kontrolü, model+fallback döngüsü,
rate-limit kısa devresi, retry ve (prompt/cevap İÇERMEYEN) yapılandırılmış loglama
burada, TEK bir yerde yazılıdır. Somut sağlayıcılar (`openrouter.py` gibi) yalnızca
`_do_generate()` — tek bir modele karşı ham HTTP çağrısı — implemente eder. Bu sayede
yeni bir sağlayıcı eklemek retry/rate-limit/log mantığını tekrar yazmayı gerektirmez.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator

from content_factory.providers.llm.cache import LLMCache, make_cache_key
from content_factory.providers.llm.exceptions import (
    LLMAllModelsExhaustedError,
    LLMAuthenticationError,
    LLMError,
    LLMInsufficientCreditError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from content_factory.providers.llm.models import LLMRequest, LLMResponse, LLMStreamChunk
from content_factory.providers.llm.rate_limit import RateLimitState
from content_factory.providers.llm.retry import RetryPolicy, retry_call
from content_factory.providers.llm.token_counter import HeuristicTokenCounter, TokenCounter
from content_factory.utils.logging import get_logger


class BaseLLMProvider(ABC):
    name: str
    """Sağlayıcı kısa adı (ör. "openrouter") — `factory.py`'deki kayıt anahtarıyla ve
    loglardaki `provider=` alanıyla eşleşir."""

    default_api_key_env: str
    """Bu sağlayıcının API anahtarını okuyacağı varsayılan ortam değişkeni adı
    (ör. "OPENROUTER_API_KEY") — `factory.create_llm_provider_for_agent` tarafından kullanılır."""

    def __init__(
        self,
        *,
        retry_policy: RetryPolicy | None = None,
        cache: LLMCache | None = None,
        token_counter: TokenCounter | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        log_prompts: bool = False,
    ) -> None:
        self._retry_policy = retry_policy or RetryPolicy()
        self._cache = cache
        self._token_counter = token_counter or HeuristicTokenCounter()
        self._sleep_fn = sleep_fn
        self._log_prompts = log_prompts
        self._rate_limits = RateLimitState()
        self._logger = get_logger(f"providers.llm.{self.name}")

    # ------------------------------------------------------------------ ortak API (final)

    def generate(self, request: LLMRequest, *, agent_name: str, run_id: str) -> LLMResponse:
        """Cache kontrolü + model/fallback döngüsü + retry + loglama. Alt sınıflar bunu
        override ETMEZ; yalnızca `_do_generate()`'i implemente eder.

        `fallback_models` boşsa ve tek model başarısız olursa asıl hata (ör.
        `LLMRateLimitError`) doğrudan yükselir; birden fazla model denenip hepsi
        başarısız olursa `LLMAllModelsExhaustedError` fırlatılır (bkz. `exceptions.py`)."""
        cache_key: str | None = None
        if self._cache is not None:
            cache_key = make_cache_key(request)
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._logger.info(
                    f"cache_hit agent={agent_name} run_id={run_id} model={request.model}"
                )
                return cached

        models_to_try = [request.model, *request.fallback_models]
        last_error: Exception | None = None

        for model in models_to_try:
            blocked, remaining = self._rate_limits.is_blocked(model)
            if blocked:
                self._logger.warning(
                    f"rate_limit_skip agent={agent_name} run_id={run_id} model={model} "
                    f"remaining_s={remaining:.1f}"
                )
                last_error = LLMRateLimitError(
                    f"{model} hâlâ rate limit altında", retry_after=remaining
                )
                continue

            started = time.monotonic()
            try:
                response = retry_call(
                    lambda m=model: self._do_generate(request, model=m),
                    policy=self._retry_policy,
                    retryable=(LLMTimeoutError, LLMProviderUnavailableError),
                    sleep_fn=self._sleep_fn,
                    on_retry=lambda attempt, exc, delay, m=model: self._logger.warning(
                        f"retry agent={agent_name} run_id={run_id} model={m} attempt={attempt} "
                        f"error={exc} delay_s={delay:.1f}"
                    ),
                )
            except LLMRateLimitError as exc:
                if exc.retry_after is not None:
                    self._rate_limits.mark_rate_limited(model, exc.retry_after)
                last_error = exc
                self._logger.warning(
                    f"rate_limited agent={agent_name} run_id={run_id} model={model} "
                    f"retry_after={exc.retry_after}"
                )
                continue
            except (LLMAuthenticationError, LLMInvalidRequestError, LLMInsufficientCreditError):
                # Sistemsel hata — başka bir model/fallback denemenin faydası yok.
                raise
            except LLMError as exc:
                last_error = exc
                self._logger.error(
                    f"llm_call_failed agent={agent_name} run_id={run_id} model={model} error={exc}"
                )
                continue

            duration = time.monotonic() - started
            self._logger.info(
                f"llm_call agent={agent_name} run_id={run_id} provider={self.name} model={model} "
                f"prompt_tokens={response.usage.prompt_tokens} "
                f"completion_tokens={response.usage.completion_tokens} duration_s={duration:.2f}"
            )
            if self._log_prompts:
                self._logger.debug(f"prompt={request.messages!r} response={response.content!r}")

            if self._cache is not None and cache_key is not None:
                self._cache.set(cache_key, response)
            return response

        if len(models_to_try) == 1 and last_error is not None:
            # `fallback_models` tanımlı değildi — tek bir model denendi ve başarısız oldu.
            # Çağırana genel bir "tükendi" hatası yerine, doğrudan yakalayıp ayırt
            # edebileceği asıl hatayı (rate limit / timeout / vb.) veriyoruz.
            raise last_error

        raise LLMAllModelsExhaustedError(
            f"Tüm modeller başarısız oldu: {models_to_try}"
        ) from last_error

    def count_tokens(self, text: str, *, model: str) -> int:
        return self._token_counter.count(text, model=model)

    def close(self) -> None:
        """Alt sınıflar (ör. açık bir HTTP client'ı kapatmak için) override edebilir."""
        return None

    def __enter__(self) -> BaseLLMProvider:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------- alt sınıfların implemente ettiği

    @abstractmethod
    def _do_generate(self, request: LLMRequest, *, model: str) -> LLMResponse:
        """TEK bir modele karşı ham çağrıyı yapar. Retry/fallback/rate-limit/cache
        mantığını `generate()` zaten sağladığı için burada tekrarlanmaz — yalnızca
        HTTP isteği + hata eşleme (`LLMError` alt sınıflarına) yapılır."""

    @abstractmethod
    def stream(
        self, request: LLMRequest, *, agent_name: str, run_id: str
    ) -> Iterator[LLMStreamChunk]:
        """Token token yayınlayan (streaming) tamamlama. Retry burada uygulanmaz —
        akış başladıktan sonra kısmi çıktıyı tekrarlamadan retry etmek güvenli değildir;
        bağlantı akış başlamadan önce koparsa hata çağırana yükselir."""

    @abstractmethod
    def health_check(self) -> bool:
        """Sağlayıcıya hafif bir bağlantı/kimlik doğrulama kontrolü yapar. Hiçbir zaman
        exception fırlatmaz — başarısızlık `False` olarak döner (çağıran taraf bunu bir
        pipeline-durduran hata değil, bir gözlemlenebilirlik sinyali olarak kullanır)."""
