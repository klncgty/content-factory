from __future__ import annotations

import json

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.topic_scout import TopicScoutAgent, TopicScoutRequest
from content_factory.domain.exceptions import AgentConfigurationError, AgentOutputParsingError

from ..support.stub_llm import StubLLMProvider

_VALID_RESPONSE = json.dumps(
    [
        {
            "title": "Zeytinyağı Donar mı?",
            "category": "olive_and_oil",
            "seed_keywords": ["zeytinyağı", "saklama"],
            "score": 0.8,
            "rationale": "x",
        },
        {
            "title": "Zeytin Ağacı Kesme Tahtası Bakımı",
            "category": "wooden_products",
            "seed_keywords": ["kesme tahtası"],
            "score": 0.6,
            "rationale": "y",
        },
    ]
)


def test_returns_topics_sorted_by_score(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = TopicScoutAgent(agent_context)

    topics = agent(TopicScoutRequest(max_candidates=5))

    assert [t.title for t in topics] == [
        "Zeytinyağı Donar mı?",
        "Zeytin Ağacı Kesme Tahtası Bakımı",
    ]
    assert topics[0].score >= topics[1].score
    assert all(t.brand == "oleart" for t in topics)
    assert all(t.created_run_id == "test-run-0001" for t in topics)


def test_respects_max_candidates(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = TopicScoutAgent(agent_context)

    topics = agent(TopicScoutRequest(max_candidates=1))
    assert len(topics) == 1


def test_skips_malformed_candidates_but_keeps_valid_ones(agent_context: AgentContext) -> None:
    response = json.dumps(
        [
            {"title": "Geçerli Konu", "category": "olive_and_oil", "score": 0.5},
            {"category": "olive_and_oil"},  # title eksik
            {"title": "Bozuk Skor", "score": "not-a-number"},
        ]
    )
    agent_context.llm = StubLLMProvider(responses=[response])
    agent = TopicScoutAgent(agent_context)

    topics = agent(TopicScoutRequest())
    assert len(topics) == 1
    assert topics[0].title == "Geçerli Konu"


def test_empty_candidate_list_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=["[]"])
    agent = TopicScoutAgent(agent_context)

    with pytest.raises(AgentOutputParsingError):
        agent(TopicScoutRequest())


def test_non_list_response_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=['{"not": "a list"}'])
    agent = TopicScoutAgent(agent_context)

    with pytest.raises(AgentOutputParsingError):
        agent(TopicScoutRequest())


def test_missing_llm_raises_configuration_error(agent_context: AgentContext) -> None:
    agent = TopicScoutAgent(agent_context)  # agent_context.llm is None by default
    with pytest.raises(AgentConfigurationError):
        agent(TopicScoutRequest())


def test_prompt_includes_used_keywords_to_avoid_duplication(agent_context: AgentContext) -> None:
    from content_factory.domain.models import Article

    agent_context.state.record_article(
        Article(brand="oleart", slug="x", title="X", target_keyword="zeytin çeşitleri")
    )
    stub = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent_context.llm = stub
    agent = TopicScoutAgent(agent_context)

    agent(TopicScoutRequest())

    assert len(stub.requests) == 1
    assert "zeytin çeşitleri" in stub.requests[0].messages[0].content
