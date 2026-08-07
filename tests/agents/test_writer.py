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


def _writer_input(
    feedback: str | None = None,
    previous_draft: str | None = None,
    *,
    content_type: str | None = None,
) -> WriterInput:
    topic = Topic(brand="oleart", title="Zeytinyağı Donar mı?", category="olive_and_oil")
    brief = Brief(
        topic=topic,
        title="Zeytinyağı Donar mı?",
        target_keyword="zeytinyağı donar mı",
        content_type=content_type,
        secondary_keywords=["zeytinyağı saklama"],
        target_word_count=900,
        outline=[OutlineSection(heading="Neden Donar?", summary="bilimsel açıklama")],
    )
    research = ResearchNotes(topic=topic, key_facts=["6-8°C altında katılaşır"])
    return WriterInput(
        brief=brief, research=research, feedback=feedback, previous_draft=previous_draft
    )


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


def test_previous_draft_included_in_prompt_on_retry(agent_context: AgentContext) -> None:
    """Retry'da önceki taslak prompt'a girmezse Writer sıfırdan yazar ve bir önceki
    denemede sağlanmış kısıtları (ör. asgari uzunluk) kaybeder."""
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input(feedback="- Çok kısa", previous_draft="# Eski Taslak\n\nGövde."))

    prompt = stub.requests[0].messages[0].content
    assert "# Eski Taslak" in prompt


def test_word_count_bounds_included_in_prompt(agent_context: AgentContext) -> None:
    """Editor kelime sınırlarını deterministik olarak denetlediği için Writer da aynı
    sınırları görmelidir (aksi halde gereksiz reddet-yeniden yaz turu doğuyor)."""
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input())

    prompt = stub.requests[0].messages[0].content
    bounds = agent_context.settings.brand.content_bounds
    assert str(bounds.min_word_count) in prompt
    assert str(bounds.max_word_count) in prompt


def _long_markdown(word_count: int) -> str:
    """`word_count` kelimelik sahte bir taslak — genişletme tabanı testleri için."""
    return "# Başlık\n\n" + " ".join(["kelime"] * (word_count - 2))


def test_short_draft_triggers_expansion_with_previous_draft(
    agent_context: AgentContext,
) -> None:
    """İlk taslak tabanın (= Editor'ün alt sınırı) altındaysa Writer, Editor'ü beklemeden
    kendi genişletme turunu döndürür ve bu turda taslağı SIFIRDAN yazdırmak yerine
    `previous_draft` olarak verir."""
    long_draft = _long_markdown(950)
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN, long_draft])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    article = agent(_writer_input())

    assert article.body_markdown == long_draft
    assert article.word_count == len(long_draft.split())
    assert len(stub.requests) == 2
    expansion_prompt = stub.requests[1].messages[0].content
    assert _SAMPLE_MARKDOWN in expansion_prompt  # önceki taslak revizyon için verildi
    assert "çok kısa" in expansion_prompt  # eksik uzunluk somut geri bildirim olarak verildi


def test_expansion_never_replaces_draft_with_shorter_output(
    agent_context: AgentContext,
) -> None:
    """Genişletme turu daha kısa/boş bir yanıt döndürürse eldeki en uzun taslak korunur —
    kötü bir genişletme iyi bir taslağı ezmemeli. Tur sayısı da sınırlıdır (sonsuz döngü yok)."""
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN, "", "# Kısa\n\nTek cümle."])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    article = agent(_writer_input())

    assert article.body_markdown == _SAMPLE_MARKDOWN
    # ilk üretim + en fazla _MAX_EXPANSION_PASSES genişletme çağrısı
    assert len(stub.requests) == 1 + WriterAgent._MAX_EXPANSION_PASSES


def test_no_expansion_when_draft_meets_floor(agent_context: AgentContext) -> None:
    bounds = agent_context.settings.brand.content_bounds
    long_draft = _long_markdown(bounds.min_word_count + 150)
    stub = StubLLMProvider(responses=[long_draft])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    article = agent(_writer_input())

    assert article.body_markdown == long_draft
    assert len(stub.requests) == 1


def test_forbidden_words_included_in_prompt(agent_context: AgentContext) -> None:
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input())

    prompt = stub.requests[0].messages[0].content
    assert "mucize" in prompt  # brand.yaml: forbidden_words


def test_expansion_feedback_forbids_labeling_added_text(agent_context: AgentContext) -> None:
    """Genişletme turunun geri bildirimi, eklenen metnin ETİKETLENMEMESİNİ açıkça
    söylemeli. Gerçek vaka (04.08.2026): bu söylenmediğinde model eklediği paragrafların
    başına '**Yeni paragraf:**' yazdı ve makale o hâliyle yayınlandı."""
    stub = StubLLMProvider(responses=[_SAMPLE_MARKDOWN, _long_markdown(900)])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input())

    expansion_prompt = stub.requests[1].messages[0].content
    assert "ETİKETLEME" in expansion_prompt
    assert "Yeni paragraf:" in expansion_prompt  # neyin yazılmayacağı örneklenmiş


def test_target_length_is_not_inflated_above_brief(agent_context: AgentContext) -> None:
    """Hedef, Strategist'in belirlediği değerdir — alt sınırın %50 üstüne şişirilmez.
    Şişirilmiş hedef modeli bölüm sonlarına dolgu paragraf eklemeye zorluyordu."""
    stub = StubLLMProvider(responses=[_long_markdown(900)])
    agent_context.llm = stub
    agent = WriterAgent(agent_context)

    agent(_writer_input())

    prompt = stub.requests[0].messages[0].content
    assert "yaklaşık 900 kelime" in prompt  # brief.target_word_count = 900


def test_content_type_is_carried_to_the_article(agent_context: AgentContext) -> None:
    """Editor'ün brief'e erişimi yok; uzunluk sınırlarını `article.content_type`
    üzerinden çözüyor. Alan taşınmazsa iki taraf sessizce farklı bant kullanır."""
    agent_context.llm = StubLLMProvider(responses=[_SAMPLE_MARKDOWN])

    article = WriterAgent(agent_context)(_writer_input(content_type="recipe"))

    assert article.content_type == "recipe"


def test_expansion_floor_follows_the_content_type(agent_context: AgentContext) -> None:
    """500 kelimelik bir tarif taban 450'yi zaten geçtiği için genişletme turu HİÇ
    tetiklenmez — tek LLM çağrısı yeterlidir. Bu, 07.08.2026'da her tarifte iki
    gereksiz tur döndüren davranışın regresyon testi."""
    draft = "# Tarif\n\n" + " ".join(["zeytinyağı"] * 500)
    stub = StubLLMProvider(responses=[draft])
    agent_context.llm = stub

    article = WriterAgent(agent_context)(_writer_input(content_type="recipe"))

    assert len(stub.requests) == 1
    assert article.body_markdown == draft


def test_same_draft_triggers_expansion_for_a_guide(agent_context: AgentContext) -> None:
    """Aynı 500 kelimelik taslak rehber tipinde taban 700'ün altında kalır ve
    genişletme turları çalışır."""
    draft = "# Rehber\n\n" + " ".join(["zeytinyağı"] * 500)
    stub = StubLLMProvider(responses=[draft, draft, draft])
    agent_context.llm = stub

    WriterAgent(agent_context)(_writer_input(content_type="guide"))

    assert len(stub.requests) > 1


def test_recipe_bounds_are_sent_to_the_prompt(agent_context: AgentContext) -> None:
    stub = StubLLMProvider(responses=["# T\n\n" + " ".join(["kelime"] * 500)])
    agent_context.llm = stub

    WriterAgent(agent_context)(_writer_input(content_type="recipe"))

    prompt = stub.requests[0].messages[0].content
    assert "450" in prompt
    assert "900" in prompt
