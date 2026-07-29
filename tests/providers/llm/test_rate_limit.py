from __future__ import annotations

from content_factory.providers.llm.rate_limit import RateLimitState, parse_retry_after


def test_model_not_blocked_by_default() -> None:
    state = RateLimitState()
    blocked, remaining = state.is_blocked("model-a")
    assert blocked is False
    assert remaining == 0.0


def test_mark_rate_limited_blocks_until_expiry() -> None:
    clock = {"t": 0.0}
    state = RateLimitState(clock=lambda: clock["t"])

    state.mark_rate_limited("model-a", 10.0)
    blocked, remaining = state.is_blocked("model-a")
    assert blocked is True
    assert remaining == 10.0

    clock["t"] = 5.0
    blocked, remaining = state.is_blocked("model-a")
    assert blocked is True
    assert remaining == 5.0

    clock["t"] = 11.0
    blocked, remaining = state.is_blocked("model-a")
    assert blocked is False
    assert remaining == 0.0


def test_other_models_unaffected() -> None:
    state = RateLimitState()
    state.mark_rate_limited("model-a", 30.0)
    blocked, _ = state.is_blocked("model-b")
    assert blocked is False


def test_clear_specific_model() -> None:
    state = RateLimitState()
    state.mark_rate_limited("model-a", 30.0)
    state.mark_rate_limited("model-b", 30.0)
    state.clear("model-a")
    assert state.is_blocked("model-a")[0] is False
    assert state.is_blocked("model-b")[0] is True


def test_clear_all_models() -> None:
    state = RateLimitState()
    state.mark_rate_limited("model-a", 30.0)
    state.mark_rate_limited("model-b", 30.0)
    state.clear()
    assert state.is_blocked("model-a")[0] is False
    assert state.is_blocked("model-b")[0] is False


def test_parse_retry_after_none() -> None:
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None


def test_parse_retry_after_seconds_format() -> None:
    assert parse_retry_after("30") == 30.0
    assert parse_retry_after("0") == 0.0


def test_parse_retry_after_http_date_format() -> None:
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    future = datetime.now(UTC) + timedelta(seconds=60)
    header = format_datetime(future, usegmt=True)
    parsed = parse_retry_after(header)
    assert parsed is not None
    assert 55 <= parsed <= 65


def test_parse_retry_after_invalid_value_returns_none() -> None:
    assert parse_retry_after("not-a-valid-value") is None
