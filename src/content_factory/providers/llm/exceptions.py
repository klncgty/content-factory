"""LLM provider hata hiyerarşisi.

`BaseLLMProvider.generate()` bu türlere göre farklı davranır (bkz. `base.py`):
- `LLMTimeoutError` / `LLMProviderUnavailableError` → geçici, aynı model için retry edilir.
- `LLMRateLimitError` → aynı model için retry edilmez; rate limit süresi kaydedilir ve
  bir sonraki `fallback_models` girdisine geçilir.
- `LLMAuthenticationError` / `LLMInvalidRequestError` / `LLMInsufficientCreditError` →
  sistemsel hata, retry veya fallback denemenin faydası yoktur, hemen yükseltilir (re-raise).
"""

from __future__ import annotations


class LLMError(Exception):
    """Tüm LLM provider hatalarının temel sınıfı."""


class LLMAuthenticationError(LLMError):
    """API anahtarı eksik/geçersiz (401/403). Retry/fallback faydasız."""


class LLMInvalidRequestError(LLMError):
    """400/404/422 — istek sağlayıcı tarafından reddedildi (bozuk gövde veya var olmayan
    model). Retry/fallback faydasız."""


class LLMInsufficientCreditError(LLMError):
    """402 — sağlayıcı hesabında bu model için yeterli bakiye yok.

    Retry EDİLMEZ: bakiye saniyeler içinde kendiliğinden artmaz, tekrar denemek yalnızca
    hatayı geciktirir. Fallback da denenmez — sorun modelde değil hesapta olduğu için
    sıradaki model de aynı duvara çarpar (ucuz bir fallback tanımlıysa şansı olabilir,
    ama bunu maliyet/gecikme pahasına denemek yerine operatöre net hata vermek yeğdir)."""


class LLMTimeoutError(LLMError):
    """İstek, yapılandırılan süre içinde yanıtlanmadı. Geçici — retry edilebilir."""


class LLMProviderUnavailableError(LLMError):
    """5xx veya bağlantı hatası. Geçici — retry edilebilir."""


class LLMRateLimitError(LLMError):
    """429 — istek sınırına takıldı."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMAllModelsExhaustedError(LLMError):
    """`request.model` + tüm `fallback_models` denendi, hiçbiri başarılı olmadı.

    Yalnızca birden fazla model denendiğinde (`fallback_models` doluyken) fırlatılır;
    `fallback_models` boşsa `generate()` doğrudan asıl hatayı (ör. `LLMRateLimitError`)
    yükseltir — bkz. `base.py::BaseLLMProvider.generate`."""


class UnknownProviderError(LLMError):
    """`factory.create_llm_provider()`'a kayıtlı olmayan bir provider adı verildi."""
