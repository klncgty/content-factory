from __future__ import annotations

import json

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.editor import EditorAgent
from content_factory.domain.exceptions import AgentOutputParsingError, AgentValidationError
from content_factory.domain.models import (
    Article,
    BodyLink,
    EditorInput,
    LinkPlan,
    QADecision,
    ScopeDecision,
    ScopeRejectionRecord,
)

from ..support.stub_llm import StubLLMProvider

_IN_SCOPE = json.dumps({"group_id": "olive_and_oil", "reason": "zeytinyağı hakkında"})
_OUT_OF_SCOPE = json.dumps({"group_id": "out_of_scope", "reason": "genel diyet tavsiyesi"})
_APPROVED = json.dumps({"decision": "approved", "reasons": []})
_REJECTED = json.dumps({"decision": "rejected", "reasons": ["2. paragraf tekrar ediyor."]})


def _body(word_count: int = 900) -> str:
    return " ".join(["zeytinyağı"] * word_count)


def _article(**overrides: object) -> Article:
    defaults: dict[str, object] = {
        "brand": "oleart",
        "slug": "zeytinyagi-donar-mi",
        "title": "Zeytinyağı Donar mı?",
        "body_markdown": _body(),
    }
    return Article(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_approves_clean_article(agent_context: AgentContext) -> None:
    # 1. yanıt ScopeGuard.post_check'e, 2. yanıt kalite incelemesine gider.
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.APPROVED
    assert report.scope_decision is ScopeDecision.IN_SCOPE
    assert report.reasons == []


def test_rejects_on_forbidden_word(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} Bu bir mucize üründür.")
    report = agent(EditorInput(article=article))

    assert report.decision is QADecision.REJECTED
    assert any("mucize" in reason for reason in report.reasons)


def test_rejects_on_forbidden_claim(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    article = _article(body_markdown=f"{_body()} Zeytinyağı hastalığı tedavi eder.")
    report = agent(EditorInput(article=article))

    assert report.decision is QADecision.REJECTED
    assert any("hastalığı tedavi eder" in reason for reason in report.reasons)


def test_rejects_when_too_short(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=_body(50))))

    assert report.decision is QADecision.REJECTED
    assert any("çok kısa" in reason for reason in report.reasons)


def test_rejects_when_too_long(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=_body(5000))))

    assert report.decision is QADecision.REJECTED
    assert any("çok uzun" in reason for reason in report.reasons)


def test_deterministic_failure_skips_expensive_quality_call(
    agent_context: AgentContext,
) -> None:
    """Makale zaten reddedilecekse pahalı kalite modeline çağrı yapılmamalı —
    yalnızca ScopeGuard'ın ucuz sınıflandırma çağrısı yapılır."""
    stub = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent_context.llm = stub
    agent = EditorAgent(agent_context)

    agent(EditorInput(article=_article(body_markdown=_body(50))))

    assert len(stub.requests) == 1


def test_scope_post_check_runs_even_when_deterministic_checks_fail(
    agent_context: AgentContext,
) -> None:
    """`QAReport.scope_decision` her zaman gerçek bir ölçümü yansıtmalı."""
    agent_context.llm = StubLLMProvider(responses=[_OUT_OF_SCOPE])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(body_markdown=_body(50))))

    assert report.scope_decision is ScopeDecision.OUT_OF_SCOPE
    assert any("Kapsam dışı" in reason for reason in report.reasons)


def test_out_of_scope_is_logged_to_state_store(
    agent_context: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[ScopeRejectionRecord] = []
    monkeypatch.setattr(agent_context.state, "log_scope_rejection", logged.append)
    agent_context.llm = StubLLMProvider(responses=[_OUT_OF_SCOPE])
    agent = EditorAgent(agent_context)

    agent(EditorInput(article=_article()))

    assert len(logged) == 1
    assert logged[0].stage == "editor"
    assert logged[0].reason == "genel diyet tavsiyesi"


def test_rejects_when_planned_link_missing_from_body(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE])
    agent = EditorAgent(agent_context)

    link_plan = LinkPlan(
        new_article_body_links=[BodyLink(anchor="erken hasat", target_slug="erken-hasat-nedir")]
    )
    report = agent(EditorInput(article=_article(), link_plan=link_plan))

    assert report.decision is QADecision.REJECTED
    assert any("Planlanan iç link" in reason for reason in report.reasons)


def test_accepts_applied_body_link(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    body = f"{_body()} [erken hasat](/blog/erken-hasat-nedir/) hakkında."
    link_plan = LinkPlan(
        new_article_body_links=[BodyLink(anchor="erken hasat", target_slug="erken-hasat-nedir")]
    )
    report = agent(EditorInput(article=_article(body_markdown=body), link_plan=link_plan))

    assert report.decision is QADecision.APPROVED


def test_llm_rejection_reasons_are_propagated(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _REJECTED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.REJECTED
    assert report.reasons == ["2. paragraf tekrar ediyor."]


def test_rejection_without_reasons_still_gives_writer_feedback(
    agent_context: AgentContext,
) -> None:
    agent_context.llm = StubLLMProvider(
        responses=[_IN_SCOPE, json.dumps({"decision": "rejected"})]
    )
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article()))

    assert report.decision is QADecision.REJECTED
    assert report.reasons  # boş kalırsa retry döngüsü aynı taslağı tekrar üretir


def test_invalid_decision_raises_parsing_error(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(
        responses=[_IN_SCOPE, json.dumps({"decision": "belki"})]
    )
    agent = EditorAgent(agent_context)

    with pytest.raises(AgentOutputParsingError):
        agent(EditorInput(article=_article()))


def test_empty_body_raises(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    with pytest.raises(AgentValidationError):
        agent(EditorInput(article=_article(body_markdown="   ")))


def test_retry_count_is_carried_into_report(agent_context: AgentContext) -> None:
    agent_context.llm = StubLLMProvider(responses=[_IN_SCOPE, _APPROVED])
    agent = EditorAgent(agent_context)

    report = agent(EditorInput(article=_article(), retry_count=2))

    assert report.retry_count == 2
