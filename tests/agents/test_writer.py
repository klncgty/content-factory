from __future__ import annotations

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.writer import WriterAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import (
    ArticleStatus,
    Brief,
    OutlineSection,
    ResearchNotes,
    Topic,
    WriterInput,
)

from ..support.stub_llm import StubLLMProvider

_SAMPLE_MARKDOWN = "# Zeytinyağı Donar mı?\n\nİçerik burada birkaç kelime.\n\n## Sonuç\n\nÖzet."


def _writer_input(feedback: str | None = None) -> WriterInput:
    topic = Topic(brand="oleart", title="Zeytinyağı Donar mı?", category="olive_and_oil")
    brief = Brief(
        topic=topic,
        title="Zeytinyağı Donar mı?",
        target_keyword="zeytinyağı donar mı",
        secondary_keywords=["zeytinyağı saklama"],
        target_word_count=900,
        outline=[OutlineSection(heading="Neden Donar?", summary="bilimsel açıklama")],
    )
    research = ResearchNotes(topic=topic, key_facts=["6-8°C altında katılaşır"])
    return WriterInput(brief=brief, research=research, feedback=feedback)


def test_returns_draft_article(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent = WriterAgent(agent_context)

    article = agent(_writer_input())

    assert article.body_markdown == _SAMPLE_MARKDOWN
    assert article.title == "Zeytinyağı Donar mı?"
    assert article.target_keyword == "zeytinyağı donar mı"
    assert article.category == "olive_and_oil"
    assert article.status is ArticleStatus.DRAFT
    assert article.word_count == len(_SAMPLE_MARKDOWN.split())
    assert article.brand == "oleart"


def test_tags_deduplicated_and_ordered(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent = WriterAgent(agent_context)

    article = agent(_writer_input())
    assert article.tags == ["zeytinyağı donar mı", "zeytinyağı saklama"]


def test_empty_response_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=["   "])
    agent = WriterAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_writer_input())


def test_feedback_included_in_prompt_when_present(agent_context: AgentContext) -> None:
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input(feedback="2. paragrafta X iddiası kaynaksız, kaldır."))

    prompt = stub.requests[0].messages[0].content
    assert "2. paragrafta X iddiası kaynaksız" in prompt


def test_forbidden_words_included_in_prompt(agent_context: AgentContext) -> None:
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input())

    prompt = stub.requests[0].messages[0].content
    assert "mucize" in prompt  # brand.yaml: forbidden_words
