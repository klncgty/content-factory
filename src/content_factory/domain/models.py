"""Pipeline boyunca agent'lar arasında akan pydantic modelleri.

Agent'lar birbirine asla dict geçirmez — her adımın girdi/çıktısı burada tanımlı bir
model'dir (bkz. ARCHITECTURE.md §4, §5). Bu dosya saf veri tanımıdır, iş mantığı içermez.

Not: sınıflar kasıtlı olarak bağımlılık sırasına göre tanımlanmıştır (ör. Article,
EditorInput'tan önce gelir) — pydantic v2 + `from __future__ import annotations`
ileri referansları yalnızca tanım anında modül namespace'inde bulunabiliyorsa çözer.
"""

from __future__ import annotations

from datetime import date as dt_date
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------------- enum'lar


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    """Editor gate'i içeriği (max retry sonunda) onaylamadı — insan incelemesi gerekiyor."""
    FAILED = "failed"


class ScopeDecision(StrEnum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"


class QADecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ArticleStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    PUBLISHED = "published"


class PublishStrategy(StrEnum):
    DIRECT_PUSH = "direct-push"
    PR_THEN_AUTOMERGE = "pr-then-automerge"


# ------------------------------------------------------------------------------- 1) Topic


class Topic(DomainModel):
    """TopicScoutAgent çıktısı — bir aday konu."""

    id: int | None = None
    brand: str
    title: str
    category: str | None = None
    """scope.yaml groups[].id — ScopeGuard.pre_check onayladıktan sonra Strategist tarafından
    doldurulur/kesinleştirilir."""
    seed_keywords: list[str] = Field(default_factory=list)
    score: float = 0.0
    status: str = "pending"
    created_run_id: str | None = None


# ---------------------------------------------------------------------- 2) ResearchNotes


class ResearchNotes(DomainModel):
    """ResearchAgent çıktısı — `Topic` hakkında yapılandırılmış, doğrulanabilir araştırma.

    WriterAgent'ın faktüel dayanağıdır; kaynaksız/uydurma bilgi riskini azaltmak için
    `key_facts`'in her biri mümkünse `sources_used`'daki bir knowledge dosyasına
    dayanmalıdır (bkz. brands/oleart/knowledge sources.md)."""

    topic: Topic
    key_facts: list[str] = Field(default_factory=list)
    suggested_angle: str = ""
    """Makalenin ele alacağı özgün bakış açısı (ör. "yaygın yanlış bilgiyi düzeltme")."""
    sources_used: list[str] = Field(default_factory=list)
    """Referans alınan knowledge dosyası adları (ör. "olive_oil.md")."""


# ------------------------------------------------------------------------------- 3) Brief


class OutlineSection(DomainModel):
    heading: str
    summary: str
    """Bu bölümde neyin anlatılacağının kısa özeti — WriterAgent bunu genişletir."""


class Brief(DomainModel):
    """StrategistAgent çıktısı — makalenin outline'ı, başlık yapısı ve içerik stratejisi;
    WriterAgent'ın uyacağı plandır."""

    topic: Topic
    title: str
    target_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    audience: str | None = None
    tone: str | None = None
    target_word_count: int = 1000
    suggested_internal_links: list[str] = Field(default_factory=list)
    outline: list[OutlineSection] = Field(default_factory=list)


class StrategistInput(DomainModel):
    topic: Topic
    research: ResearchNotes


class WriterInput(DomainModel):
    brief: Brief
    research: ResearchNotes
    feedback: str | None = None
    """EditorAgent'ın reddettiği bir önceki denemeden gelen geri bildirim (retry döngüsü)."""


# ---------------------------------------------------------------------------- 4) SEOData


class SEOData(DomainModel):
    """SEOOptimizerAgent çıktısı."""

    meta_title: str
    meta_description: str
    slug: str
    target_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- 5) ImageData


class ImageData(DomainModel):
    """ImageGeneratorAgent çıktısı — bkz. ARCHITECTURE.md §7 (1 temel görsel + 3 türev)."""

    base_image_path: str | None = None
    cover_path: str | None = None
    thumbnail_path: str | None = None
    og_image_path: str | None = None
    alt_text: str | None = None


# ---------------------------------------------------------------------------- 6) LinkPlan


class BodyLink(DomainModel):
    anchor: str
    target_slug: str


class RelatedArticleUpdate(DomainModel):
    target_slug: str
    add_related: str


class LinkPlan(DomainModel):
    """LinkerAgent çıktısı — bkz. ARCHITECTURE.md §5 (prose değil, frontmatter güncellemesi)."""

    new_article_body_links: list[BodyLink] = Field(default_factory=list)
    related_articles_updates: list[RelatedArticleUpdate] = Field(default_factory=list)


# ---------------------------------------------------------------------------- 7) Article


class Article(DomainModel):
    """Writer'dan başlayıp Publisher'a kadar pipeline boyunca zenginleşen tek makale nesnesi.
    Aynı zamanda StateStore'un kalıcılaştırdığı/okuduğu kayıttır (bkz. ARCHITECTURE.md §12)."""

    id: int | None = None
    brand: str
    slug: str | None = None
    title: str
    description: str = ""
    category: str | None = None
    target_keyword: str | None = None
    secondary_keywords: list[str] = Field(default_factory=list)
    body_markdown: str = ""
    date: dt_date | None = None
    updated: dt_date | None = None
    status: ArticleStatus = ArticleStatus.DRAFT
    seo: SEOData | None = None
    image: ImageData | None = None
    tags: list[str] = Field(default_factory=list)
    reading_time_minutes: int | None = None
    related_articles: list[str] = Field(default_factory=list)
    commit_sha: str | None = None
    file_path: str | None = None
    word_count: int | None = None


# --------------------------------------------------------------------------- 8) QAReport


class QAReport(DomainModel):
    """EditorAgent çıktısı — zorunlu geçit kararı."""

    decision: QADecision
    scope_decision: ScopeDecision
    reasons: list[str] = Field(default_factory=list)
    retry_count: int = 0


class EditorInput(DomainModel):
    article: Article
    link_plan: LinkPlan | None = None
    retry_count: int = 0
    """Kaçıncı Writer denemesinin incelendiği — Orchestrator'ın retry döngüsü doldurur.
    EditorAgent bunu yalnızca `QAReport.retry_count`'a geçirir, karara etki etmez."""


class PublisherInput(DomainModel):
    article: Article
    link_plan: LinkPlan | None = None


class PublisherOutput(DomainModel):
    """PublisherAgent çıktısı — yalnızca diske yazılan dosya yolları; git bilgisi içermez
    (Publisher/GitAgent ayrımı için bkz. ARCHITECTURE.md §8)."""

    article: Article
    written_paths: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- 9) PublishResult


class PublishResult(DomainModel):
    """GitAgent çıktısı."""

    article_slug: str
    file_path: str
    commit_sha: str | None = None
    pr_url: str | None = None
    strategy: PublishStrategy
    published_at: datetime


# ------------------------------------------------------------------------------ 10) RunState


class RunState(DomainModel):
    """Bir pipeline çalıştırmasının uçtan uca durumu — Orchestrator üretir/günceller."""

    run_id: str
    brand: str
    status: RunStatus = RunStatus.PENDING
    topic: Topic | None = None
    research: ResearchNotes | None = None
    brief: Brief | None = None
    article: Article | None = None
    qa_report: QAReport | None = None
    link_plan: LinkPlan | None = None
    publish_result: PublishResult | None = None
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    step_history: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------- StateStore kayıtları
# Pipeline'da bir karşılığı olmayan, yalnızca kalıcı depolama/denetim amaçlı yardımcı modeller.


class InternalLinkRecord(DomainModel):
    id: int | None = None
    brand: str
    source_slug: str
    target_slug: str
    link_type: str = "related_section"
    created_run_id: str


class ScopeRejectionRecord(DomainModel):
    id: int | None = None
    brand: str
    run_id: str
    stage: str
    reason: str
    payload_snippet: str = ""
