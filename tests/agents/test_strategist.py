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
    # content_type verilmediğinde markanın VARSAYILAN bandı geçerli: 700 * 1.25.
    assert brief.content_type is None
    assert brief.target_word_count == 875
    assert brief.secondary_keywords == []
    assert brief.outline == []


def test_content_type_drives_the_target_word_count(agent_context: AgentContext) -> None:
    """Tarif seçildiğinde hedef, tarif bandının tabanından türetilir (450 * 1.25).

    Bir tarifi rehber tabanına (700) zorlamak, yayınlanan bir makalede malzeme listesinden
    sonra zeytinyağı saklama tavsiyesi yazdırmıştı (07.08.2026)."""
    response = json.dumps({"title": "T", "target_keyword": "k", "content_type": "recipe"})
    agent_context.llm = StubLLMProvider(responses=[response])

    brief = StrategistAgent(agent_context)(_input())

    assert brief.content_type == "recipe"
    assert brief.target_word_count == 562


def test_model_cannot_set_its_own_word_target(agent_context: AgentContext) -> None:
    """Modelin yazdığı `target_word_count` yok sayılır — sayıyı kod koyar, yoksa bir
    makale kendi barajını düşürebilirdi."""
    response = json.dumps({
        "title": "T",
        "target_keyword": "k",
        "content_type": "recipe",
        "target_word_count": 120,
    })
    agent_context.llm = StubLLMProvider(responses=[response])

    brief = StrategistAgent(agent_context)(_input())

    assert brief.target_word_count == 562


def test_unknown_content_type_falls_back_to_brand_defaults(agent_context: AgentContext) -> None:
    """Config'de olmayan bir tip uydurulursa makale üretilmeye devam eder, ama varsayılan
    sınırlara düşer."""
    response = json.dumps({"title": "T", "target_keyword": "k", "content_type": "podcast"})
    agent_context.llm = StubLLMProvider(responses=[response])

    brief = StrategistAgent(agent_context)(_input())

    assert brief.content_type is None
    assert brief.target_word_count == 875


def test_prompt_lists_the_configured_content_types(agent_context: AgentContext) -> None:
    """Tip sözlüğü markaya aittir: ortak prompt hiçbir tip adını bilmez, katalog
    `brand.yaml`'dan gelir."""
    stub = StubLLMProvider(responses=[json.dumps({"title": "T", "target_keyword": "k"})])
    agent_context.llm = stub

    StrategistAgent(agent_context)(_input())

    prompt = stub.requests[0].messages[0].content
    assert "`recipe`" in prompt
    assert "450-900 kelime" in prompt
    assert "4-5 bölüm" in prompt
    assert "`guide`" in prompt
    assert "700-1500 kelime" in prompt
