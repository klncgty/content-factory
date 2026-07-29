from __future__ import annotations

from content_factory.providers.llm.exceptions import (
    LLMAllModelsExhaustedError,
    LLMAuthenticationError,
    LLMError,
    LLMInvalidRequestError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
    UnknownProviderError,
)


def test_all_llm_errors_derive_from_llm_error() -> None:
    for cls in (
        LLMAuthenticationError,
        LLMInvalidRequestError,
        LLMTimeoutError,
        LLMProviderUnavailableError,
        LLMRateLimitError,
        LLMAllModelsExhaustedError,
        UnknownProviderError,
    ):
        assert issubclass(cls, LLMError)


def test_rate_limit_error_carries_retry_after() -> None:
    exc = LLMRateLimitError("rate limited", retry_after=12.5)
    assert exc.retry_after == 12.5
    assert "rate limited" in str(exc)


def test_rate_limit_error_retry_after_optional() -> None:
    exc = LLMRateLimitError("rate limited")
    assert exc.retry_after is None
