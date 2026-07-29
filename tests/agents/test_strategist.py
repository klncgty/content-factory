from __future__ import annotations

import json

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.strategist import StrategistAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import ResearchNotes, StrategistInput, Topic

from ..support.stub_llm import StubLLMProvider

_VALID_RESPONSE = json.dumps(
    {
        "title": "Zeytinyağı Donar mı? Doğru Saklama Rehberi",
        "target_keyword": "zeytinyağı donar mı",
        "secondary_keywords": ["zeytinyağı saklama"],
        "audience": "tüketiciler",
        "tone": "sıcak",
        "target_word_count": 900,
        "outline": [
            {"heading": "Neden Donar?", "summary": "bilimsel açıklama"},
            {"heading": "Sonuç", "summary": "özet"},
        ],
        "suggested_internal_links": ["erken hasat"],
    }
)


def _input() -> StrategistInput:
    topic = Topic(brand="oleart", title="Zeytinyağı Donar mı?", category="olive_and_oil")
    research = ResearchNotes(topic=topic, key_facts=["fact 1"], suggested_angle="x")
    return StrategistInput(topic=topic, research=research)


def test_returns_brief_with_outline(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = StrategistAgent(agent_context)

    brief = agent(_input())

    assert brief.title == "Zeytinyağı Donar mı? Doğru Saklama Rehberi"
    assert brief.target_keyword == "zeytinyağı donar mı"
    assert len(brief.outline) == 2
    assert brief.outline[0].heading == "Neden Donar?"
    assert brief.topic.title == "Zeytinyağı Donar mı?"


def test_missing_required_field_raises_parsing_error(agent_context: AgentContext) -> None:
    response = json.dumps({"target_keyword": "x"})  # title eksik
    agent_context.llm = StubLLMProvider(responses=[response])
    agent = StrategistAgent(agent_context)

    with pytest.raises(AgentOutputParsingError):
        agent(_input())


def test_malformed_outline_entries_are_skipped(agent_context: AgentContext) -> None:
    response = json.dumps(
        {
            "title": "T",
            "target_keyword": "k",
            "outline": [{"heading": "Geçerli", "summary": "s"}, {"summary": "başlıksız"}],
        }
    )
    agent_context.llm = StubLLMProvider(responses=[response])
    agent = StrategistAgent(agent_context)

    brief = agent(_input())
    assert len(brief.outline) == 1
    assert brief.outline[0].heading == "Geçerli"


def test_defaults_applied_when_optional_fields_missing(agent_context: AgentContext) -> None:
    response = json.dumps({"title": "T", "target_keyword": "k"})
    agent_context.llm = StubLLMProvider(responses=[response])
    agent = StrategistAgent(agent_context)

    brief = agent(_input())
    assert brief.target_word_count == 1000
    assert brief.secondary_keywords == []
    assert brief.outline == []
