from __future__ import annotations

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.linker import LinkerAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Article


def _seed_related_article(agent_context: AgentContext, *, slug: str, keyword: str) -> None:
    agent_context.state.record_article(
        Article(
            brand="oleart",
            slug=slug,
            title=f"{keyword} hakkında",
            category="olive_and_oil",
            target_keyword=keyword,
            body_markdown="...",
        )
    )


def _new_article(body: str) -> Article:
    return Article(
        brand="oleart",
        slug="zeytinyagi-donar-mi",
        title="Zeytinyağı Donar mı?",
        category="olive_and_oil",
        target_keyword="zeytinyağı donar mı",
        secondary_keywords=["erken hasat"],
        body_markdown=body,
    )


def test_inserts_body_link_when_keyword_present(agent_context: AgentContext) -> None:
    _seed_related_article(agent_context, slug="erken-hasat-nedir", keyword="erken hasat")
    agent = LinkerAgent(agent_context)

    output = agent(_new_article("Bu makalede erken hasat zeytinyağından bahsediyoruz."))

    assert "[erken hasat](/blog/erken-hasat-nedir/)" in output.article.body_markdown
    assert output.link_plan.new_article_body_links[0].target_slug == "erken-hasat-nedir"


def test_skips_body_link_when_keyword_not_present_in_text(agent_context: AgentContext) -> None:
    _seed_related_article(agent_context, slug="baska-makale", keyword="alakasız kelime öbeği")
    agent = LinkerAgent(agent_context)

    output = agent(_new_article("Bu metinde o kelime hiç geçmiyor."))

    assert output.link_plan.new_article_body_links == []
    # Ama related_articles_updates yine de eklenmeli — body-link olmasa da geri bağlantı verilir.
    assert output.link_plan.related_articles_updates[0].target_slug == "baska-makale"


def test_sets_related_articles_on_new_article(agent_context: AgentContext) -> None:
    _seed_related_article(agent_context, slug="erken-hasat-nedir", keyword="erken hasat")
    agent = LinkerAgent(agent_context)

    output = agent(_new_article("erken hasat ile ilgili bir makale."))
    assert "erken-hasat-nedir" in output.article.related_articles


def test_related_articles_updates_target_old_articles(agent_context: AgentContext) -> None:
    _seed_related_article(agent_context, slug="erken-hasat-nedir", keyword="erken hasat")
    agent = LinkerAgent(agent_context)

    output = agent(_new_article("erken hasat konusu."))
    update = output.link_plan.related_articles_updates[0]
    assert update.target_slug == "erken-hasat-nedir"
    assert update.add_related == "zeytinyagi-donar-mi"


def test_excludes_the_article_itself_from_candidates(agent_context: AgentContext) -> None:
    agent_context.state.record_article(_new_article("mevcut hali"))
    agent = LinkerAgent(agent_context)

    output = agent(_new_article("zeytinyağı donar mı hakkında yeni bir yazı."))
    assert output.article.related_articles == []


def test_missing_slug_raises(agent_context: AgentContext) -> None:
    article = _new_article("...").model_copy(update={"slug": None})
    agent = LinkerAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(article)


def test_no_candidates_returns_empty_link_plan(agent_context: AgentContext) -> None:
    agent = LinkerAgent(agent_context)
    output = agent(_new_article("hiç ilgili makale yok."))
    assert output.link_plan.new_article_body_links == []
    assert output.link_plan.related_articles_updates == []
