from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_factory.providers.llm.models import LLMMessage, LLMRequest, LLMResponse, TokenUsage


def test_llm_message_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role="system-prompt", content="x")  # type: ignore[arg-type]


def test_llm_request_is_frozen() -> None:
    request = LLMRequest(
        system_prompt="s", messages=[LLMMessage(role="user", content="x")], model="model-a"
    )
    with pytest.raises(ValidationError):
        request.model = "model-b"  # type: ignore[misc]


def test_llm_request_defaults() -> None:
    request = LLMRequest(
        system_prompt="s", messages=[LLMMessage(role="user", content="x")], model="model-a"
    )
    assert request.temperature == 0.7
    assert request.max_tokens == 2000
    assert request.fallback_models == []


def test_llm_response_default_usage_is_zero() -> None:
    response = LLMResponse(content="x", model="model-a", provider="fake")
    assert response.usage == TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
