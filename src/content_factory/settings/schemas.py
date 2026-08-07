"""config/*.yaml ve brands/{brand}/*.yaml dosyalarının pydantic şemaları.

Bu modül yalnızca YAML -> tipli Python nesnesi dönüşümünü tanımlar; iş mantığı içermez.
Tüm modeller `extra="allow"` ile tanımlanır: YAML dosyalarına yeni alanlar eklenmesi
(marka ekibi/SEO ekibi tarafından) kod değişikliği gerektirmeden çalışmaya devam eder.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class YamlModel(BaseModel):
    """Tüm config şemalarının ortak atası — bilinmeyen YAML alanlarını sessizce kabul eder."""

    model_config = ConfigDict(extra="allow", frozen=True)


# --------------------------------------------------------------------------- config/engine.yaml


class RetriesConfig(YamlModel):
    editor_reject_max_retries: int = 2
    scope_reject_max_retries: int = 2
    llm_call_max_retries: int = 3
    rate_limit_max_wait_seconds: int = 0
    """Tüm modeller (asıl + fallback) rate limit'e takıldığında toplam ne kadar beklenip
    yeniden deneneceği. 0 = hiç bekleme. Ücretsiz kademelerde sınır dakikalık olduğu için
    bunu 60-90 yapmak, yarısı üretilmiş bir makalenin çöpe gitmesini engeller
    (bkz. providers/llm/base.py::BaseLLMProvider.generate)."""


class TimeoutsConfig(YamlModel):
    llm_call_seconds: int = 120
    image_generation_seconds: int = 180
    pipeline_run_seconds: int = 1800


class ImageDerivativeSpec(YamlModel):
    size: tuple[int, int]
    format: str = "webp"


class StateStoreConfig(YamlModel):
    backend: str = "sqlite"
    path_template: str = "data/{brand}/content_factory.db"


class RunArtifactsConfig(YamlModel):
    path_template: str = "state/{brand}/runs/{run_id}"
    retention_days: int = 90


class GroundingConfig(YamlModel):
    """`GroundingGuard`'ın (bkz. `guards/grounding_guard.py`) yaptırım modu."""

    enforce: bool = False
    """`False` (varsayılan): zeminsiz sayılar yalnızca loglanır, makale reddedilmez.
    `True`: Editor makaleyi reddeder ve Writer'a düzeltme geri bildirimi gider.

    Varsayılanın kapalı olması bilinçli: guard yeni bir YAYIN GEÇİDİ ve yanlış pozitifi
    bir yayın turunu boşa harcar. Önce bir süre uyarı modunda çalıştırıp gerçek
    makalelerdeki isabetini ölçmek, sonra açmak doğru sıralama."""


class EngineConfig(YamlModel):
    retries: RetriesConfig = Field(default_factory=RetriesConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    image_derivatives: dict[str, ImageDerivativeSpec] = Field(default_factory=dict)
    state_store: StateStoreConfig = Field(default_factory=StateStoreConfig)
    run_artifacts: RunArtifactsConfig = Field(default_factory=RunArtifactsConfig)
    grounding: GroundingConfig = Field(default_factory=GroundingConfig)


# --------------------------------------------------------------------------- config/models.yaml


class FallbackProviderConfig(YamlModel):
    """Bir agent'ın BİRİNCİL sağlayıcısı tümden başarısız olduğunda geçilecek İKİNCİL
    sağlayıcı (bkz. `providers/llm/factory.py::ProviderChain`).

    `fallback_models` neden yetmiyor: o liste AYNI sağlayıcı içinde denenir ve model
    adları sağlayıcıya özgüdür (Groq'ta `llama-3.3-70b-versatile`, Replicate'te
    `meta/meta-llama-3-70b-instruct`). Sağlayıcı değiştiğinde model adının da değişmesi
    gerektiği için ikincil sağlayıcı kendi model bilgisini taşır."""

    provider: str
    model: str
    fallback_models: list[str] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None


class AgentModelConfig(YamlModel):
    model: str | None = None
    provider: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    fallback_models: list[str] = Field(default_factory=list)

    response_format: Literal["text", "json_object"] = "text"
    """`json_object`, sağlayıcının yapısal çıktı kipini açar — JSON bekleyen agent'lar
    (Editor, ScopeGuard, SEO, Research, Strategist, TopicScout) için. Desteklemeyen
    sağlayıcı/modelde sessizce düşer (bkz. `providers/llm/models.py::ResponseFormat`)."""

    fallback_provider: FallbackProviderConfig | None = None

    # Yalnızca image_generator için anlamlı. Hangi alanın desteklendiği modele göre
    # değişir (ör. gemini-2.5-flash-image `aspect_ratio` destekler, `resolution`
    # desteklemez) — bu yüzden ikisi de opsiyoneldir ve yalnızca doluysa gönderilir.
    images_per_article: int | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None


class ModelsConfig(YamlModel):
    default_provider: str = "openrouter"
    agents: dict[str, AgentModelConfig] = Field(default_factory=dict)

    def for_agent(self, agent_name: str) -> AgentModelConfig:
        return self.agents.get(agent_name, AgentModelConfig())


# --------------------------------------------------------------------------- brands/{b}/brand.yaml


class ContentBounds(YamlModel):
    min_word_count: int = 800
    max_word_count: int = 1500


class BrandConfig(YamlModel):
    brand: str
    display_name: str
    website: str
    language: str = "tr"
    content_bounds: ContentBounds = Field(default_factory=ContentBounds)
    forbidden_words: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    scope_file: str = "scope.yaml"


# --------------------------------------------------------------------------- brands/{b}/scope.yaml


class ScopeGroup(YamlModel):
    id: str
    label: str
    topics: list[str] = Field(default_factory=list)


class ScopeCheckSpec(YamlModel):
    stage: str
    method: str
    on_fail: str


class ScopeAuditSpec(YamlModel):
    log_rejections_to: str = "scope_rejections"


class ScopeEnforcement(YamlModel):
    pre_check: ScopeCheckSpec
    post_check: ScopeCheckSpec
    audit: ScopeAuditSpec = Field(default_factory=ScopeAuditSpec)


class ScopeConfig(YamlModel):
    brand: str
    schema_version: int = 1
    groups: list[ScopeGroup] = Field(default_factory=list)
    out_of_scope_examples: list[str] = Field(default_factory=list)
    enforcement: ScopeEnforcement


# ------------------------------------------------------------------------- brands/{b}/publish.yaml


class GitPublishConfig(YamlModel):
    remote: str = "origin"
    branch: str = "main"
    publish_strategy: str = "pr-then-automerge"
    commit_message_template: str = "blog: {slug} eklendi"


class PublishConfig(YamlModel):
    target_repo_path: str
    content_dir: str = "content/blog"
    images_dir: str = "public/blog/images"
    public_root: str = "public"
    """Hedef sitede site kökünden servis edilen statik dizin. `images_dir`'ın public
    URL'e çevrilmesinde kullanılır (`public/blog/images` -> `/blog/images`); farklı bir
    jeneratörde (ör. `static/`) yalnızca bu değer değişir."""
    git: GitPublishConfig = Field(default_factory=GitPublishConfig)


# ----------------------------------------------------------------------------- brands/{b}/seo.yaml


class KeywordCluster(YamlModel):
    group: str
    seed_keywords: list[str] = Field(default_factory=list)


class InternalLinkingConfig(YamlModel):
    min_related_articles: int = 2
    max_related_articles: int = 5
    mechanism: str = "structured_related_articles_frontmatter"


class SeoConfig(YamlModel):
    keyword_clusters: list[KeywordCluster] = Field(default_factory=list)
    competitor_domains: list[str] = Field(default_factory=list)
    internal_linking: InternalLinkingConfig = Field(default_factory=InternalLinkingConfig)
    publish_cadence: str = "weekly"


# ----------------------------------------------------------------------- brands/{b}/knowledge.yaml


class TopicFileSpec(YamlModel):
    """Markanın konusuna özgü bir knowledge dosyası. `field`, agent'ların
    `knowledge.compose("olive_oil", ...)` gibi çağrılarında kullandığı addır."""

    field: str
    filename: str
    description: str = ""


class KnowledgeConfig(YamlModel):
    """Markanın KONUSUNU tanımlayan config — motor kodunda marka-özel sabit kalmaması
    için (bkz. `brands/oleart/knowledge.yaml`). Ton/yazım kuralları gibi her markada
    bulunan dosyalar burada değil, `knowledge/loader.py: CORE_FILES` içindedir."""

    brand: str = ""
    schema_version: int = 1
    topic_files: list[TopicFileSpec] = Field(default_factory=list)
    category_knowledge: dict[str, list[str]] = Field(default_factory=dict)
    default_knowledge: list[str] = Field(default_factory=list)
    grounding_fields: list[str] = Field(default_factory=list)
    image_scenes: dict[str, str] = Field(default_factory=dict)
    default_image_scene: str = ""

    def knowledge_fields_for(self, category: str | None) -> list[str]:
        """ResearchAgent: kategoriye karşılık gelen konu dosyaları."""
        return self.category_knowledge.get(category or "", self.default_knowledge)

    def image_scene_for(self, category: str | None) -> str:
        """ImageGeneratorAgent: kategoriye karşılık gelen görsel sahnesi."""
        return self.image_scenes.get(category or "", self.default_image_scene)


# ------------------------------------------------------------------------ brands/{b}/schedule.yaml


class ScheduleConfig(YamlModel):
    cron: str = "0 7 * * 1"
    timezone: str = "Europe/Istanbul"
    max_publishes_per_run: int = 1
    max_publishes_per_day: int = 1
