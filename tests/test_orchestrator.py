"""Orchestrator testleri — agent'ların KENDİ iş mantığı burada test edilmez
(bunun için `tests/agents/`), test edilen şey sıralama, kapsam eleme, Editor retry
döngüsü ve yayın sonrası kalıcılaştırmadır. Bu yüzden agent'lar sahte (fake)
implementasyonlarla değiştirilir: gerçek agent'ları LLM yanıtlarıyla sürmek bu
seviyedeki davranışı gizlerdi.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.linker import LinkerOutput
from content_factory.agents.topic_scout import TopicScoutRequest
from content_factory.domain.exceptions import AgentConfigurationError
from content_factory.domain.models import (
    Article,
    ArticleStatus,
    BodyLink,
    Brief,
    EditorInput,
    LinkPlan,
    PublisherInput,
    PublisherOutput,
    PublishResult,
    PublishStrategy,
    QADecision,
    QAReport,
    RelatedArticleUpdate,
    ResearchNotes,
    RunStatus,
    ScopeDecision,
    SEOData,
    StrategistInput,
    Topic,
    WriterInput,
)
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.orchestrator import PipelineAgents, PipelineOrchestrator
from content_factory.providers.image import ImageProviderUnavailableError

# ------------------------------------------------------------------------------- sahteler


class FakeAgent:
    """Çağrıldığını kaydeden, sabit çıktı döndüren minimal agent yerine geçen.

    `outputs` HER ZAMAN bir çağrı-yanıtı listesidir (agent'ın kendisi liste döndürse
    bile — ör. TopicScout: `FakeAgent([[topic1, topic2]])`). Yanıtlar sırayla döndürülür;
    liste tükenince sonuncusunda kalınır — "Editor her seferinde reddetsin" senaryosu
    böylece tek bir rapor vererek kurulur."""

    def __init__(self, outputs: list[object]) -> None:
        self._outputs = outputs
        self.calls: list[object] = []

    def __call__(self, input_data: object) -> object:
        self.calls.append(input_data)
        return self._outputs[min(len(self.calls) - 1, len(self._outputs) - 1)]


def _topic(title: str = "Zeytinyağı Donar mı?", **overrides: object) -> Topic:
    defaults: dict[str, object] = {
        "brand": "oleart",
        "title": title,
        "seed_keywords": ["zeytinyağı"],
        "score": 0.9,
    }
    return Topic(**{**defaults, **overrides})  # type: ignore[arg-type]


def _article(**overrides: object) -> Article:
    defaults: dict[str, object] = {
        "brand": "oleart",
        "slug": "zeytinyagi-donar-mi",
        "title": "Zeytinyağı Donar mı?",
        "target_keyword": "zeytinyağı donar mı",
        "secondary_keywords": ["zeytinyağı saklama"],
        "body_markdown": "## Giriş\n\nMetin.",
        "seo": SEOData(
            meta_title="T",
            meta_description="D",
            slug="zeytinyagi-donar-mi",
            target_keyword="zeytinyağı donar mı",
        ),
    }
    return Article(**{**defaults, **overrides})  # type: ignore[arg-type]


def _build_agents(
    *,
    topics: list[Topic] | None = None,
    qa_reports: list[QAReport] | None = None,
    link_plan: LinkPlan | None = None,
) -> tuple[PipelineAgents, dict[str, FakeAgent]]:
    article = _article()
    plan = link_plan if link_plan is not None else LinkPlan()
    research = ResearchNotes(topic=_topic(), key_facts=["gerçek"], suggested_angle="açı")
    brief = Brief(
        topic=_topic(), title="Zeytinyağı Donar mı?", target_keyword="zeytinyağı donar mı"
    )
    published = article.model_copy(
        update={
            "status": ArticleStatus.PUBLISHED,
            "date": date(2026, 7, 30),
            "file_path": "content/blog/2026-07-30-zeytinyagi-donar-mi.md",
        }
    )

    fakes: dict[str, FakeAgent] = {
        "topic_scout": FakeAgent([topics if topics is not None else [_topic()]]),
        "research": FakeAgent([research]),
        "strategist": FakeAgent([brief]),
        "writer": FakeAgent([article]),
        "seo_optimizer": FakeAgent([article]),
        "linker": FakeAgent([LinkerOutput(article=article, link_plan=plan)]),
        "image_generator": FakeAgent([article]),
        "editor": FakeAgent(
            qa_reports
            or [QAReport(decision=QADecision.APPROVED, scope_decision=ScopeDecision.IN_SCOPE)]
        ),
        "publisher": FakeAgent(
            [
                PublisherOutput(
                    article=published,
                    written_paths=["content/blog/2026-07-30-zeytinyagi-donar-mi.md"],
                )
            ]
        ),
        "git_agent": FakeAgent(
            [
                PublishResult(
                    article_slug="zeytinyagi-donar-mi",
                    file_path="content/blog/2026-07-30-zeytinyagi-donar-mi.md",
                    commit_sha="abc123",
                    strategy=PublishStrategy.PR_THEN_AUTOMERGE,
                    published_at=datetime.now(),
                )
            ]
        ),
    }
    return PipelineAgents(**fakes), fakes  # type: ignore[arg-type]


@pytest.fixture
def orchestrate(agent_context: AgentContext):
    """Sahte agent'larla kurulmuş bir pipeline çalıştırır; `(RunState, sahteler)` döndürür."""

    def _run(*, publish: bool = True, **agent_kwargs: object):
        agents, fakes = _build_agents(**agent_kwargs)  # type: ignore[arg-type]
        orchestrator = PipelineOrchestrator(
            context=agent_context,
            agents=agents,
            scope_guard=ScopeGuard(agent_context.settings.scope),
            publish=publish,
        )
        return orchestrator.run(), fakes

    return _run


# ---------------------------------------------------------------------------------- testler


def test_happy_path_runs_all_steps_in_order(orchestrate) -> None:
    state, _ = orchestrate()

    assert state.status is RunStatus.COMPLETED
    assert state.step_history == [
        "topic_scout",
        "research",
        "strategist",
        "writer",
        "seo_optimizer",
        "linker",
        "image_generator",
        "editor",
        "publisher",
        "git_agent",
    ]
    assert state.publish_result is not None
    assert state.publish_result.commit_sha == "abc123"


def test_research_feeds_both_strategist_and_writer(orchestrate) -> None:
    _, fakes = orchestrate()

    assert isinstance(fakes["topic_scout"].calls[0], TopicScoutRequest)

    strategist_input = fakes["strategist"].calls[0]
    assert isinstance(strategist_input, StrategistInput)
    assert strategist_input.research.key_facts == ["gerçek"]

    # Writer da aynı araştırma notlarını almalı — Brief tek başına faktüel dayanak değil.
    writer_input = fakes["writer"].calls[0]
    assert isinstance(writer_input, WriterInput)
    assert writer_input.research.key_facts == ["gerçek"]


def test_out_of_scope_candidates_are_filtered_out(orchestrate) -> None:
    _, fakes = orchestrate(
        topics=[
            _topic("Ayçiçek Yağı Rehberi", seed_keywords=["ayçiçek yağı"], score=0.99),
            _topic("Zeytinyağı Nasıl Saklanır?", seed_keywords=["zeytinyağı"], score=0.5),
        ]
    )

    assert fakes["research"].calls[0].title == "Zeytinyağı Nasıl Saklanır?"


def test_scope_pre_check_sets_topic_category(orchestrate) -> None:
    """Kategori TopicScout'un tahminine değil, eşleşen scope grubuna göre kesinleşir."""
    _, fakes = orchestrate()
    assert fakes["research"].calls[0].category == "olive_and_oil"


def test_fails_when_no_candidate_passes_scope(orchestrate) -> None:
    state, fakes = orchestrate(topics=[_topic("Seyahat Rehberi", seed_keywords=["gezi"])])

    assert state.status is RunStatus.FAILED
    assert "kapsam onaylı aday" in state.error
    assert fakes["research"].calls == []


def test_scope_rejection_is_audited(
    orchestrate, agent_context: AgentContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list = []
    monkeypatch.setattr(agent_context.state, "log_scope_rejection", logged.append)

    orchestrate(topics=[_topic("Seyahat Rehberi", seed_keywords=["gezi"])])

    assert len(logged) == 1
    assert logged[0].stage == "topic_scout"


def test_editor_rejection_triggers_rewrite_with_feedback(orchestrate) -> None:
    reports = [
        QAReport(
            decision=QADecision.REJECTED,
            scope_decision=ScopeDecision.IN_SCOPE,
            reasons=["3. paragraf kaynaksız."],
        ),
        QAReport(decision=QADecision.APPROVED, scope_decision=ScopeDecision.IN_SCOPE),
    ]
    state, fakes = orchestrate(qa_reports=reports)

    assert state.status is RunStatus.COMPLETED
    assert len(fakes["writer"].calls) == 2
    assert fakes["writer"].calls[0].feedback is None
    assert "3. paragraf kaynaksız." in fakes["writer"].calls[1].feedback
    # Görsel makalenin metnine değil konusuna bağlı — retry'da yeniden üretilmemeli.
    assert len(fakes["image_generator"].calls) == 1


def test_needs_review_after_max_retries(orchestrate, agent_context: AgentContext) -> None:
    rejected = QAReport(
        decision=QADecision.REJECTED,
        scope_decision=ScopeDecision.IN_SCOPE,
        reasons=["hâlâ kötü"],
    )
    state, fakes = orchestrate(qa_reports=[rejected])

    max_retries = agent_context.settings.engine.retries.editor_reject_max_retries
    assert state.status is RunStatus.NEEDS_REVIEW
    assert len(fakes["editor"].calls) == max_retries + 1
    assert fakes["publisher"].calls == []
    assert fakes["git_agent"].calls == []


def test_editor_receives_incrementing_retry_count(orchestrate) -> None:
    rejected = QAReport(
        decision=QADecision.REJECTED, scope_decision=ScopeDecision.IN_SCOPE, reasons=["x"]
    )
    _, fakes = orchestrate(qa_reports=[rejected])

    attempts = [call.retry_count for call in fakes["editor"].calls]
    assert attempts == list(range(len(attempts)))


def test_editor_sees_link_plan(orchestrate) -> None:
    """Editor Linker'dan SONRA çalışır — eklenen iç linkler de onaydan geçmeli."""
    plan = LinkPlan(
        new_article_body_links=[BodyLink(anchor="erken hasat", target_slug="erken-hasat-nedir")]
    )
    _, fakes = orchestrate(link_plan=plan)

    editor_input = fakes["editor"].calls[0]
    assert isinstance(editor_input, EditorInput)
    assert editor_input.link_plan == plan


def test_publisher_receives_link_plan(orchestrate) -> None:
    plan = LinkPlan(
        related_articles_updates=[
            RelatedArticleUpdate(
                target_slug="erken-hasat-nedir", add_related="zeytinyagi-donar-mi"
            )
        ]
    )
    _, fakes = orchestrate(link_plan=plan)

    publisher_input = fakes["publisher"].calls[0]
    assert isinstance(publisher_input, PublisherInput)
    assert publisher_input.link_plan == plan


def test_publication_is_recorded_in_state_store(
    orchestrate, agent_context: AgentContext
) -> None:
    plan = LinkPlan(
        new_article_body_links=[BodyLink(anchor="erken hasat", target_slug="erken-hasat-nedir")],
        related_articles_updates=[
            RelatedArticleUpdate(
                target_slug="erken-hasat-nedir", add_related="zeytinyagi-donar-mi"
            )
        ],
    )
    orchestrate(link_plan=plan)

    store = agent_context.state
    assert store.slug_exists("oleart", "zeytinyagi-donar-mi")
    assert store.is_keyword_used("oleart", "zeytinyağı donar mı")
    assert store.is_keyword_used("oleart", "zeytinyağı saklama")


def test_nothing_is_persisted_when_editor_rejects(
    orchestrate, agent_context: AgentContext
) -> None:
    """Yayınlanmamış bir makale StateStore'u kirletmemeli."""
    rejected = QAReport(
        decision=QADecision.REJECTED, scope_decision=ScopeDecision.IN_SCOPE, reasons=["x"]
    )
    orchestrate(qa_reports=[rejected])

    assert not agent_context.state.slug_exists("oleart", "zeytinyagi-donar-mi")


def test_dry_run_skips_git_and_persistence(orchestrate, agent_context: AgentContext) -> None:
    state, fakes = orchestrate(publish=False)

    assert state.status is RunStatus.COMPLETED
    assert fakes["publisher"].calls  # dosyalar yazılır
    assert fakes["git_agent"].calls == []  # ama commit/push yapılmaz
    assert "git_agent" not in state.step_history
    # Gerçekte push edilmemiş bir makale "yayınlandı" olarak kaydedilmemeli.
    assert not agent_context.state.slug_exists("oleart", "zeytinyagi-donar-mi")


def test_agent_failure_marks_run_failed(agent_context: AgentContext) -> None:
    agents, _ = _build_agents()

    def boom(_: object) -> object:
        raise RuntimeError("LLM patladı")

    agents.writer = boom  # type: ignore[assignment]
    state = PipelineOrchestrator(
        context=agent_context,
        agents=agents,
        scope_guard=ScopeGuard(agent_context.settings.scope),
    ).run()

    assert state.status is RunStatus.FAILED
    assert "LLM patladı" in state.error
    assert state.finished_at is not None


@pytest.mark.parametrize(
    "failure",
    [
        AgentConfigurationError("ImageProvider yapılandırılmadı"),
        ImageProviderUnavailableError("görsel API'si 503 döndü"),
    ],
)
def test_image_failure_does_not_block_publication(
    agent_context: AgentContext, failure: Exception
) -> None:
    """Görsel bir zenginleştirmedir, yayın önkoşulu değil: ne eksik yapılandırma ne de
    sağlayıcı arızası, Editor'den onay almış bir makalenin yayınlanmasını engellemeli."""
    agents, fakes = _build_agents()

    def boom(_: object) -> object:
        raise failure

    agents.image_generator = boom  # type: ignore[assignment]
    state = PipelineOrchestrator(
        context=agent_context,
        agents=agents,
        scope_guard=ScopeGuard(agent_context.settings.scope),
    ).run()

    assert state.status is RunStatus.COMPLETED
    assert fakes["publisher"].calls != []
    assert state.article.image is None


def test_works_without_scope_guard(agent_context: AgentContext) -> None:
    agents, fakes = _build_agents(
        topics=[_topic("Seyahat Rehberi", seed_keywords=["gezi"])]
    )
    state = PipelineOrchestrator(
        context=agent_context, agents=agents, scope_guard=None
    ).run()

    assert state.status is RunStatus.COMPLETED
    assert fakes["research"].calls[0].title == "Seyahat Rehberi"


# --------------------------------------------------------------- topics_backlog (Adım 8)


def test_unselected_candidates_are_saved_to_backlog(orchestrate, agent_context) -> None:
    """Seçilmeyen uygun adaylar bir sonraki run için saklanmalı."""
    topics = [
        _topic("Zeytinyağı Donar mı?", score=0.9),
        _topic("Zeytin Ağacı Kesme Tahtası Bakımı", seed_keywords=["zeytin ağacı"], score=0.8),
    ]
    orchestrate(topics=topics)

    pending = agent_context.state.get_pending_topics("oleart")
    assert [t.title for t in pending] == ["Zeytin Ağacı Kesme Tahtası Bakımı"]


def test_selected_topic_is_not_saved_to_backlog(orchestrate, agent_context) -> None:
    orchestrate(topics=[_topic("Zeytinyağı Donar mı?")])
    assert agent_context.state.get_pending_topics("oleart") == []


def test_backlog_topic_is_used_and_topic_scout_is_skipped(
    orchestrate, agent_context
) -> None:
    """Adım 8'in asıl kazancı: backlog doluysa TopicScout hiç çağrılmaz (LLM tasarrufu)."""
    agent_context.state.add_topic_candidates(
        [_topic("Sele Zeytini Nasıl Yapılır?", seed_keywords=["zeytin"], score=0.7)]
    )

    state, fakes = orchestrate(topics=[_topic("Bu Konu Kullanılmamalı")])

    assert fakes["topic_scout"].calls == []
    assert "topic_scout" not in state.step_history
    assert state.step_history[0] == "topic_backlog"
    assert state.topic.title == "Sele Zeytini Nasıl Yapılır?"


def test_used_backlog_topic_is_not_offered_again(orchestrate, agent_context) -> None:
    agent_context.state.add_topic_candidates(
        [_topic("Sele Zeytini Nasıl Yapılır?", seed_keywords=["zeytin"], score=0.7)]
    )
    orchestrate()
    assert agent_context.state.get_pending_topics("oleart") == []


def test_stale_backlog_topic_is_skipped_and_marked(orchestrate, agent_context) -> None:
    """Kaydedildikten sonra benzeri yayınlanmış bir konu bayattır: kullanılmamalı,
    `stale` işaretlenmeli ve her run'da yeniden değerlendirilmemeli."""
    agent_context.state.record_article(
        _article().model_copy(update={"status": ArticleStatus.PUBLISHED})
    )
    agent_context.state.add_topic_candidates(
        [_topic("Zeytinyağı Donar mı?", seed_keywords=["zeytinyağı"], score=0.7)]
    )

    state, fakes = orchestrate(topics=[_topic("Sele Zeytini Nedir?", seed_keywords=["zeytin"])])

    # Bayat backlog konusu kullanılmadı; TopicScout'a düşüldü.
    assert fakes["topic_scout"].calls != []
    assert state.topic.title == "Sele Zeytini Nedir?"
    assert agent_context.state.get_pending_topics("oleart") == []
