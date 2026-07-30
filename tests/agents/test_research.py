from __future__ import annotations

import json

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.research import ResearchAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Topic

from ..support.stub_llm import StubLLMProvider

_VALID_RESPONSE = json.dumps(
    {
        "key_facts": ["fact 1", "fact 2"],
        "suggested_angle": "yaygın yanlışı düzeltme",
        "sources_used": ["olive_oil.md"],
    }
)


def _topic(category: str | None = "olive_and_oil") -> Topic:
    return Topic(
        brand="oleart",
        title="Zeytinyağı Donar mı?",
        category=category,
        seed_keywords=["zeytinyağı", "saklama"],
    )


def test_returns_research_notes_bound_to_topic(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = ResearchAgent(agent_context)

    notes = agent(_topic())

    assert notes.topic.title == "Zeytinyağı Donar mı?"
    assert notes.key_facts == ["fact 1", "fact 2"]
    assert notes.suggested_angle == "yaygın yanlışı düzeltme"
    assert notes.sources_used == ["olive_oil.md"]


def test_fabricated_sources_are_filtered_out(agent_context: AgentContext) -> None:
    response = json.dumps(
        {
            "key_facts": ["fact"],
            "suggested_angle": "açı",
            # olive_oil.md gerçek ve bu çağrıda gösterildi; kitchen_products.md gerçek
            # ama olive_and_oil kategorisinde GÖSTERİLMEDİ; wikipedia.org hiç bir
            # knowledge dosyası değil — ikisi de uydurma sayılıp elenmeli.
            "sources_used": ["olive_oil.md", "kitchen_products.md", "wikipedia.org"],
        }
    )
    agent_context.llm = StubLLMProvider(responses=[response])
    agent = ResearchAgent(agent_context)

    notes = agent(_topic(category="olive_and_oil"))

    assert notes.sources_used == ["olive_oil.md"]


def test_selects_knowledge_fields_by_category(agent_context: AgentContext) -> None:
    stub = StubLLMProvider(responses=[_VALID_RESPONSE, _VALID_RESPONSE])
    agent_context.llm = stub
    agent = ResearchAgent(agent_context)

    agent(_topic(category="wooden_products"))
    agent(_topic(category="olive_and_oil"))

    wooden_prompt = stub.requests[0].messages[0].content
    olive_prompt = stub.requests[1].messages[0].content
    # Her iki kategori de olive_tree.md'yi paylaşır ama wooden_products kitchen_products.md
    # içermeli; iki promptun birebir aynı olmaması, kategoriye göre filtrelemenin
    # çalıştığını dolaylı olarak doğrular.
    assert wooden_prompt != olive_prompt


def test_unknown_category_falls_back_to_default_fields(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_VALID_RESPONSE])
    agent = ResearchAgent(agent_context)
    notes = agent(_topic(category=None))
    assert notes.key_facts  # çökmeden tamamlandı


def test_invalid_json_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=["bu json değil"])
    agent = ResearchAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_topic())


def test_non_object_response_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=["[1, 2, 3]"])
    agent = ResearchAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_topic())
