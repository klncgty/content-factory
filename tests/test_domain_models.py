from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from content_factory.domain.models import (
    Article,
    ArticleStatus,
    Brief,
    QADecision,
    QAReport,
    RunState,
    RunStatus,
    ScopeDecision,
    Topic,
)


def test_topic_requires_brand_and_title() -> None:
    topic = Topic(brand="oleart", title="Zeytinyağı donar mı?", seed_keywords=["zeytinyağı"])
    assert topic.status == "pending"
    assert topic.score == 0.0


def test_domain_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Topic(brand="oleart", title="x", unexpected_field="nope")  # type: ignore[call-arg]


def test_article_defaults_to_draft_status() -> None:
    article = Article(brand="oleart", title="Zeytin Çeşitleri")
    assert article.status is ArticleStatus.DRAFT
    assert article.tags == []


def test_run_state_round_trip() -> None:
    topic = Topic(brand="oleart", title="Sele zeytini nedir?")
    brief = Brief(topic=topic, title="Sele Zeytini", target_keyword="sele zeytini")
    qa = QAReport(decision=QADecision.APPROVED, scope_decision=ScopeDecision.IN_SCOPE)

    state = RunState(
        run_id="run-1",
        brand="oleart",
        status=RunStatus.RUNNING,
        brief=brief,
        qa_report=qa,
        started_at=datetime.now(),
        step_history=["topic_scout", "strategist"],
    )

    dumped = state.model_dump_json()
    restored = RunState.model_validate_json(dumped)
    assert restored.brief.title == "Sele Zeytini"
    assert restored.qa_report.decision is QADecision.APPROVED
    assert restored.step_history == ["topic_scout", "strategist"]
