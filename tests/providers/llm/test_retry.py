from __future__ import annotations

import pytest

from content_factory.providers.llm.retry import RetryPolicy, compute_backoff, retry_call


def test_compute_backoff_grows_exponentially_without_jitter() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=100.0, jitter=False)
    assert compute_backoff(1, policy) == 1.0
    assert compute_backoff(2, policy) == 2.0
    assert compute_backoff(3, policy) == 4.0


def test_compute_backoff_caps_at_max_delay() -> None:
    policy = RetryPolicy(base_delay_seconds=1.0, max_delay_seconds=3.0, jitter=False)
    assert compute_backoff(10, policy) == 3.0


def test_compute_backoff_jitter_stays_within_expected_range() -> None:
    policy = RetryPolicy(base_delay_seconds=2.0, max_delay_seconds=100.0, jitter=True)
    for attempt in range(1, 5):
        delay = compute_backoff(attempt, policy)
        base = min(2.0 * (2 ** (attempt - 1)), 100.0)
        assert 0 <= delay <= base * 1.5


def test_retry_call_returns_immediately_on_success() -> None:
    calls = []

    def func() -> str:
        calls.append(1)
        return "ok"

    result = retry_call(func, policy=RetryPolicy(max_attempts=3), retryable=(ValueError,))
    assert result == "ok"
    assert len(calls) == 1


def test_retry_call_retries_until_success() -> None:
    attempts = {"n": 0}

    def func() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("geçici")
        return "ok"

    sleeps: list[float] = []
    result = retry_call(
        func,
        policy=RetryPolicy(max_attempts=5, base_delay_seconds=0.01, jitter=False),
        retryable=(TimeoutError,),
        sleep_fn=sleeps.append,
    )
    assert result == "ok"
    assert attempts["n"] == 3
    assert len(sleeps) == 2  # 2 başarısız deneme sonrası bekleme


def test_retry_call_raises_after_max_attempts() -> None:
    def func() -> str:
        raise TimeoutError("hep başarısız")

    with pytest.raises(TimeoutError):
        retry_call(
            func,
            policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
            retryable=(TimeoutError,),
            sleep_fn=lambda _: None,
        )


def test_retry_call_does_not_catch_non_retryable_exceptions() -> None:
    def func() -> str:
        raise ValueError("kalıcı hata")

    with pytest.raises(ValueError):
        retry_call(
            func,
            policy=RetryPolicy(max_attempts=3),
            retryable=(TimeoutError,),
        )


def test_retry_call_invokes_on_retry_callback() -> None:
    events: list[tuple[int, float]] = []
    attempts = {"n": 0}

    def func() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise TimeoutError("x")
        return "ok"

    retry_call(
        func,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        retryable=(TimeoutError,),
        sleep_fn=lambda _: None,
        on_retry=lambda attempt, exc, delay: events.append((attempt, delay)),
    )
    assert len(events) == 1
    assert events[0][0] == 1
