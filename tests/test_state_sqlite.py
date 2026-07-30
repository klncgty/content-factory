from __future__ import annotations

from datetime import date

from content_factory.domain.models import (
    Article,
    InternalLinkRecord,
    LLMCallRecord,
    ScopeRejectionRecord,
    SEOData,
    Topic,
)
from content_factory.state.sqlite_store import SQLiteStateStore


def _sample_article(slug: str = "zeytinyagi-donar-mi") -> Article:
    return Article(
        brand="oleart",
        slug=slug,
        title="Zeytinyağı Donar mı?",
        description="Saklama rehberi.",
        category="olive_and_oil",
        target_keyword="zeytinyağı donar mı",
        secondary_keywords=["zeytinyağı saklama"],
        body_markdown="# Zeytinyağı Donar mı?\n\nİçerik burada.",
        date=date(2026, 8, 1),
        tags=["zeytinyağı", "saklama"],
        seo=SEOData(
            meta_title="Zeytinyağı Donar mı?",
            meta_description="Doğru saklama koşulları.",
            slug=slug,
            target_keyword="zeytinyağı donar mı",
        ),
    )


def test_record_and_fetch_article_round_trip(state_store: SQLiteStateStore) -> None:
    article_id = state_store.record_article(_sample_article())
    assert article_id > 0

    recent = state_store.get_recent_articles("oleart", limit=10)
    assert len(recent) == 1
    assert recent[0].slug == "zeytinyagi-donar-mi"
    assert recent[0].seo.meta_title == "Zeytinyağı Donar mı?"


def test_slug_exists(state_store: SQLiteStateStore) -> None:
    assert state_store.slug_exists("oleart", "zeytinyagi-donar-mi") is False
    state_store.record_article(_sample_article())
    assert state_store.slug_exists("oleart", "zeytinyagi-donar-mi") is True


def test_find_related_articles_scores_by_keyword_overlap(state_store: SQLiteStateStore) -> None:
    state_store.record_article(_sample_article("zeytinyagi-donar-mi"))
    other = _sample_article("zeytin-cesitleri")
    other.target_keyword = "zeytin çeşitleri"
    other.secondary_keywords = ["sele zeytini"]
    state_store.record_article(other)

    related = state_store.find_related_articles(
        "oleart", keywords=["zeytinyağı saklama"], exclude_slug="zeytin-cesitleri"
    )
    assert related[0].slug == "zeytinyagi-donar-mi"


def test_keyword_usage_tracking(state_store: SQLiteStateStore) -> None:
    assert state_store.is_keyword_used("oleart", "zeytinyağı donar mı") is False
    state_store.record_keyword_usage("oleart", "zeytinyağı donar mı", "zeytinyagi-donar-mi")
    assert state_store.is_keyword_used("oleart", "zeytinyağı donar mı") is True


def test_topics_backlog_add_and_fetch_pending(state_store: SQLiteStateStore) -> None:
    state_store.add_topic_candidates(
        [
            Topic(brand="oleart", title="Erken Hasat Nedir?", score=0.8),
            Topic(brand="oleart", title="Zeytin Çeşitleri", score=0.5),
        ]
    )
    pending = state_store.get_pending_topics("oleart")
    assert [t.title for t in pending] == ["Erken Hasat Nedir?", "Zeytin Çeşitleri"]

    state_store.mark_topic_status(pending[0].id, "used")
    remaining = state_store.get_pending_topics("oleart")
    assert len(remaining) == 1


def test_internal_link_and_scope_rejection_logging(state_store: SQLiteStateStore) -> None:
    state_store.record_article(_sample_article("zeytinyagi-donar-mi"))
    state_store.record_article(_sample_article("zeytin-cesitleri"))

    state_store.record_internal_link(
        InternalLinkRecord(
            brand="oleart",
            source_slug="zeytin-cesitleri",
            target_slug="zeytinyagi-donar-mi",
            created_run_id="run-1",
        )
    )
    state_store.log_scope_rejection(
        ScopeRejectionRecord(
            brand="oleart", run_id="run-1", stage="topic_scout", reason="kapsam dışı"
        )
    )
    # Sıra bozulmadan devam ediyorsa (exception fırlatılmıyorsa) test geçer.


def test_record_and_fetch_llm_calls(state_store: SQLiteStateStore) -> None:
    state_store.record_llm_call(
        LLMCallRecord(
            run_id="run-1",
            agent_name="writer",
            provider="groq",
            model="openai/gpt-oss-120b",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            duration_ms=1200,
        )
    )
    state_store.record_llm_call(
        LLMCallRecord(
            run_id="run-1",
            agent_name="editor",
            provider="replicate",
            model="meta/meta-llama-3-70b-instruct",
            prompt_tokens=200,
            completion_tokens=20,
            total_tokens=220,
            duration_ms=800,
        )
    )
    state_store.record_llm_call(
        LLMCallRecord(
            run_id="run-other",
            agent_name="writer",
            provider="groq",
            model="openai/gpt-oss-120b",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            duration_ms=100,
        )
    )

    calls = state_store.get_run_llm_calls("run-1")

    assert len(calls) == 2
    assert [c.agent_name for c in calls] == ["writer", "editor"]
    assert calls[0].model == "openai/gpt-oss-120b"
    assert calls[0].total_tokens == 150
    assert calls[0].duration_ms == 1200


def test_run_lifecycle(state_store: SQLiteStateStore) -> None:
    state_store.start_run("run-1", "oleart")
    state_store.finish_run("run-1", "completed")
