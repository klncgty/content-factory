"""Uçtan uca duman testi — GERÇEK agent'larla.

`test_orchestrator.py` sahte agent'lar kullanır (orada test edilen şey sıralama/retry
mantığıdır). Burada ise tüm gerçek agent'lar bir araya getirilir ve yalnızca dış dünya
(LLM, git) sahtelenir: prompt render'ı, JSON ayrıştırma, model config okuma ve
agent'lar arası model uyumu ancak böyle birlikte doğrulanabilir.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.editor import EditorAgent
from content_factory.agents.git_agent import GitAgent
from content_factory.agents.image_generator import ImageGeneratorAgent
from content_factory.agents.linker import LinkerAgent
from content_factory.agents.publisher import PublisherAgent
from content_factory.agents.research import ResearchAgent
from content_factory.agents.seo_optimizer import SEOOptimizerAgent
from content_factory.agents.strategist import StrategistAgent
from content_factory.agents.topic_scout import TopicScoutAgent
from content_factory.agents.writer import WriterAgent
from content_factory.domain.models import RunStatus
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.orchestrator import PipelineAgents, PipelineOrchestrator
from content_factory.utils import frontmatter

from .support.stub_git import StubGitProvider
from .support.stub_llm import StubLLMProvider

_TITLE = "Zeytinyağı Nasıl Saklanır?"
# brands/oleart/brand.yaml: content_bounds 800-1500 kelime — Editor bu sınırı uyguluyor,
# bu yüzden taslak gerçekten o aralıkta olmalı (180 x 5 kelime = 900).
_BODY = "## Giriş\n\n" + " ".join(["zeytinyağı saklama koşulları hakkında bilgi"] * 180)

# LLM çağrıları pipeline'da gerçekleşme SIRASINA göre — bu sıranın kendisi de test
# edilen şeyin bir parçası (bir agent fazladan/eksik çağrı yaparsa test bozulur).
_LLM_RESPONSES = [
    # 1) topic_scout
    json.dumps(
        [
            {"title": _TITLE, "seed_keywords": ["zeytinyağı", "saklama"], "score": 0.9},
            {"title": "Ayçiçek Yağı Rehberi", "seed_keywords": ["ayçiçek yağı"], "score": 0.95},
        ]
    ),
    # 2) research
    json.dumps(
        {
            "key_facts": ["Zeytinyağı ışıktan uzakta saklanmalıdır."],
            "suggested_angle": "yaygın yanlış bilgiyi düzeltme",
            "sources_used": ["olive_oil.md"],
        }
    ),
    # 3) strategist
    json.dumps(
        {
            "title": _TITLE,
            "target_keyword": "zeytinyağı saklama",
            "secondary_keywords": ["zeytinyağı saklama koşulları"],
            "target_word_count": 1000,
            "outline": [{"heading": "Giriş", "summary": "Neden önemli"}],
        }
    ),
    # 4) writer (markdown, JSON değil)
    _BODY,
    # 5) seo_optimizer
    json.dumps(
        {
            "meta_title": "Zeytinyağı Nasıl Saklanır? | Oleart",
            "meta_description": "Zeytinyağını doğru saklamanın koşulları.",
            "secondary_keywords": ["zeytinyağı saklama koşulları"],
        }
    ),
    # 6) editor -> ScopeGuard.post_check
    json.dumps({"group_id": "olive_and_oil", "reason": "zeytinyağı saklama hakkında"}),
    # 7) editor -> kalite incelemesi
    json.dumps({"decision": "approved", "reasons": []}),
]


@pytest.fixture
def pipeline(agent_context: AgentContext, tmp_path: Path):
    repo_root = tmp_path / "site"
    repo_root.mkdir()
    settings = agent_context.settings
    agent_context.settings = dataclasses.replace(
        settings,
        publish=settings.publish.model_copy(
            update={
                "target_repo_path": str(repo_root),
                # Strateji burada sabitlenir: test "yayın, yapılandırılan stratejiyle git
                # provider'ına gidiyor mu" sorusunu doğrular — marka dosyası bugün
                # direct-push'ta olsa da bu senaryo PR yolunu kapsamalı.
                "git": settings.publish.git.model_copy(
                    update={"publish_strategy": "pr-then-automerge"}
                ),
            }
        ),
    )
    agent_context.llm = StubLLMProvider(responses=list(_LLM_RESPONSES))
    agent_context.git = StubGitProvider()
    # context.image bilinçli olarak None: somut bir ImageProvider henüz yok (ROADMAP.md).

    agents = PipelineAgents(
        topic_scout=TopicScoutAgent(agent_context),
        research=ResearchAgent(agent_context),
        strategist=StrategistAgent(agent_context),
        writer=WriterAgent(agent_context),
        seo_optimizer=SEOOptimizerAgent(agent_context),
        linker=LinkerAgent(agent_context),
        image_generator=ImageGeneratorAgent(agent_context),
        editor=EditorAgent(agent_context),
        publisher=PublisherAgent(agent_context),
        git_agent=GitAgent(agent_context),
    )
    orchestrator = PipelineOrchestrator(
        context=agent_context,
        agents=agents,
        scope_guard=ScopeGuard(agent_context.settings.scope),
    )
    return orchestrator, repo_root


def test_pipeline_publishes_an_article_end_to_end(pipeline) -> None:
    orchestrator, repo_root = pipeline

    state = orchestrator.run()

    assert state.status is RunStatus.COMPLETED, state.error
    assert state.publish_result is not None
    assert state.publish_result.article_slug == "zeytinyagi-nasil-saklanir"

    published = list((repo_root / "content/blog").glob("*.md"))
    assert len(published) == 1

    fields, body = frontmatter.split(published[0].read_text("utf-8"))
    assert fields["slug"] == "zeytinyagi-nasil-saklanir"
    assert fields["category"] == "olive_and_oil"
    assert fields["target_keyword"] == "zeytinyağı saklama"
    assert fields["description"] == "Zeytinyağını doğru saklamanın koşulları."
    assert fields["status"] == "published"
    assert body.startswith("## Giriş")


def test_pipeline_consumes_expected_llm_calls(pipeline, agent_context: AgentContext) -> None:
    """Fazladan bir LLM çağrısı = beklenmeyen maliyet; eksik çağrı = atlanan bir adım."""
    orchestrator, _ = pipeline

    orchestrator.run()

    assert len(agent_context.llm.requests) == len(_LLM_RESPONSES)


def test_pipeline_survives_missing_image_provider(pipeline) -> None:
    """Somut bir ImageProvider yokken makale görselsiz yayınlanır, pipeline durmaz."""
    orchestrator, repo_root = pipeline

    state = orchestrator.run()

    assert state.status is RunStatus.COMPLETED
    assert "image_generator" in state.step_history
    assert not (repo_root / "public").exists()

    fields, _ = frontmatter.split(
        next((repo_root / "content/blog").glob("*.md")).read_text("utf-8")
    )
    assert "cover_image" not in fields


def test_out_of_scope_candidate_never_reaches_research(
    pipeline, agent_context: AgentContext
) -> None:
    """Daha yüksek skorlu "Ayçiçek Yağı" adayı ScopeGuard tarafından elenmiş olmalı —
    aksi halde araştırma/yazım o konu üzerinde yapılırdı."""
    orchestrator, _ = pipeline

    state = orchestrator.run()

    assert state.topic is not None
    assert state.topic.title == _TITLE


def test_publication_is_committed_via_git_provider(
    pipeline, agent_context: AgentContext
) -> None:
    orchestrator, _ = pipeline

    orchestrator.run()

    call = agent_context.git.calls[0]
    assert call["strategy"] == "pr-then-automerge"
    assert call["files"] == [f"content/blog/{date.today():%Y-%m-%d}-zeytinyagi-nasil-saklanir.md"]
    assert "zeytinyagi-nasil-saklanir" in call["message"]
