from __future__ import annotations

import pytest

from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import ScopeDecision
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.prompts.loader import PromptLoader
from content_factory.settings.loader import Settings

from .support.stub_llm import StubLLMProvider


@pytest.fixture
def scope_guard(settings: Settings) -> ScopeGuard:
    return ScopeGuard(settings.scope)


@pytest.mark.parametrize(
    "title,keywords",
    [
        ("Zeytinyağı Donar mı?", ["zeytinyağı", "saklama"]),
        ("Erken Hasat Nedir?", ["erken hasat"]),
        ("Zeytin Ağacı Kesme Tahtası Nasıl Bakılır?", ["zeytin ağacı bakım rehberleri"]),
        ("Sele Zeytini Rehberi", ["zeytin çeşitleri"]),
    ],
)
def test_pre_check_accepts_in_scope_topics(
    scope_guard: ScopeGuard, title: str, keywords: list[str]
) -> None:
    result = scope_guard.pre_check(title=title, seed_keywords=keywords)
    assert result.decision is ScopeDecision.IN_SCOPE
    assert result.matched_group in {"olive_and_oil", "wooden_products"}


@pytest.mark.parametrize(
    "title,keywords",
    [
        ("Ayçiçek Yağı ile Kek Tarifi", ["ayçiçek yağı"]),
        ("Yaz Tatili İçin 10 Öneri", ["seyahat", "tatil"]),
        ("Kilo Vermek İçin Genel Diyet Tavsiyeleri", ["diyet"]),
    ],
)
def test_pre_check_rejects_out_of_scope_topics(
    scope_guard: ScopeGuard, title: str, keywords: list[str]
) -> None:
    result = scope_guard.pre_check(title=title, seed_keywords=keywords)
    assert result.decision is ScopeDecision.OUT_OF_SCOPE


def test_post_check_in_scope(scope_guard: ScopeGuard, prompt_loader: PromptLoader) -> None:
    llm = StubLLMProvider(
        responses=['{"group_id": "olive_and_oil", "reason": "zeytinyağı hakkında"}']
    )
    result = scope_guard.post_check(
        article_body="Zeytinyağı saklama koşulları...",
        llm=llm,
        prompt_loader=prompt_loader,
        model="test-model",
        run_id="run-1",
    )
    assert result.decision is ScopeDecision.IN_SCOPE
    assert result.matched_group == "olive_and_oil"
    assert len(llm.requests) == 1


def test_post_check_out_of_scope(scope_guard: ScopeGuard, prompt_loader: PromptLoader) -> None:
    llm = StubLLMProvider(
        responses=['{"group_id": "out_of_scope", "reason": "genel diyet tavsiyesi"}']
    )
    result = scope_guard.post_check(
        article_body="Kilo vermek için genel tavsiyeler...",
        llm=llm,
        prompt_loader=prompt_loader,
        model="test-model",
        run_id="run-1",
    )
    assert result.decision is ScopeDecision.OUT_OF_SCOPE


def test_post_check_unknown_group_id_treated_as_out_of_scope(
    scope_guard: ScopeGuard, prompt_loader: PromptLoader
) -> None:
    llm = StubLLMProvider(responses=['{"group_id": "not-a-real-group", "reason": "x"}'])
    result = scope_guard.post_check(
        article_body="...", llm=llm, prompt_loader=prompt_loader, model="test-model", run_id="run-1"
    )
    assert result.decision is ScopeDecision.OUT_OF_SCOPE


def test_post_check_invalid_json_raises_parsing_error(
    scope_guard: ScopeGuard, prompt_loader: PromptLoader
) -> None:
    llm = StubLLMProvider(responses=["bu json değil"])
    with pytest.raises(AgentOutputParsingError):
        scope_guard.post_check(
            article_body="...",
            llm=llm,
            prompt_loader=prompt_loader,
            model="test-model",
            run_id="run-1",
        )


def test_post_check_missing_group_id_raises_parsing_error(
    scope_guard: ScopeGuard, prompt_loader: PromptLoader
) -> None:
    llm = StubLLMProvider(responses=['{"reason": "eksik alan"}'])
    with pytest.raises(AgentOutputParsingError):
        scope_guard.post_check(
            article_body="...",
            llm=llm,
            prompt_loader=prompt_loader,
            model="test-model",
            run_id="run-1",
        )
