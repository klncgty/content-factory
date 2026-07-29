from __future__ import annotations

import json

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.seo_optimizer import SEOOptimizerAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Article

from ..support.stub_llm import StubLLMProvider

_VALID_RESPONSE = json.dumps(
    {
        "meta_title": "Zeytinyağı Donar mı? Doğru Saklama Rehberi | Oleart",
        "meta_description": (
            "Zeytinyağı soğukta neden bulanıklaşır? Doğru saklama koşullarını öğrenin."
        ),
        "secondary_keywords": ["zeytinyağı saklama koşulları"],
    }
)


def _article() -> Article:
    return Article(
        brand="oleart",
        title="Zeytinyağı Donar mı? Doğru Saklama Rehberi",
        target_keyword="zeytinyağı donar mı",
        secondary_keywords=["zeytinyağı saklama"],
        body_markdown="# Başlık\n\nİçerik...",
    )


def test_sets_seo_and_slug(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = SEOOptimizerAgent(agent_context)

    result = agent(_article())

    assert result.seo is not None
    assert result.seo.meta_title.startswith("Zeytinyağı Donar mı?")
    assert result.slug == "zeytinyagi-donar-mi-dogru-saklama-rehberi"
    assert result.seo.slug == result.slug
    assert result.seo.target_keyword == "zeytinyağı donar mı"


def test_slug_is_deterministic_not_llm_generated(agent_context: AgentContext) -> None:
    """Aynı başlık her zaman aynı slug'ı üretmeli — LLM'in çıktısına bağlı olmamalı."""
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE, _VALID_RESPONSE])
    agent = SEOOptimizerAgent(agent_context)

    first = agent(_article())
    second = agent(_article())
    assert first.slug == second.slug


def test_missing_target_keyword_raises(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = SEOOptimizerAgent(agent_context)
    article = _article().model_copy(update={"target_keyword": None})
    with pytest.raises(AgentOutputParsingError):
        agent(article)


def test_missing_meta_fields_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=['{"meta_title": "x"}'])
    agent = SEOOptimizerAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_article())


def test_falls_back_to_original_secondary_keywords_when_llm_omits_them(
    agent_context: AgentContext,
) -> None:
    response = json.dumps({"meta_title": "T", "meta_description": "D"})
    agent_context.llm = StubLLMProvider(responses=[response])
    agent = SEOOptimizerAgent(agent_context)

    result = agent(_article())
    assert result.seo.secondary_keywords == ["zeytinyağı saklama"]
