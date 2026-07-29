"""Geçici hatalar için exponential backoff + jitter retry mekanizması.

Provider-bağımsızdır: hangi exception'ların "retryable" sayıldığını çağıran taraf
belirler (bkz. `base.py`'nin `retryable=(LLMTimeoutError, LLMProviderUnavailableError)`
kullanımı) — bu modül LLM'e özgü hiçbir şey bilmez, herhangi bir çağrılabilir için kullanılabilir.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter: bool = True


def compute_backoff(attempt: int, policy: RetryPolicy) -> float:
    """`attempt` 1-tabanlıdır (ilk deneme = 1)."""
    delay = min(policy.base_delay_seconds * (2 ** (attempt - 1)), policy.max_delay_seconds)
    if policy.jitter:
        delay *= 0.5 + random.random()  # noqa: S311 - kriptografik değil, yalnızca jitter
    return delay


def retry_call[T](
    func: Callable[[], T],
    *,
    policy: RetryPolicy,
    retryable: tuple[type[Exception], ...],
    sleep_fn: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """`func`'ı çağırır; `retryable` içindeki bir exception fırlatırsa `policy.max_attempts`'e
    kadar exponential backoff ile yeniden dener. Son denemede de başarısız olursa orijinal
    exception'ı yükseltir. `retryable` dışındaki exception'lar hiç yakalanmaz, direkt yükselir.
    """
    last_exc: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return func()
        except retryable as exc:
            last_exc = exc
            if attempt == policy.max_attempts:
                raise
            delay = compute_backoff(attempt, policy)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep_fn(delay)
    # Buraya asla ulaşılmaz (döngü ya return eder ya da son denemede raise eder);
    # yalnızca tip denetleyiciler için.
    assert last_exc is not None
    raise last_exc
