"""Knowledge Base sistemi — tüm agent'ların ortak, tip güvenli bilgi kaynağı.

Hiçbir agent `knowledge/brands/{brand}/*.md` dosyalarını doğrudan okumaz; hepsi
`KnowledgeLoader.load(brand)` çağırıp geri dönen `BrandKnowledge` nesnesinin
`get_*()` metodlarını kullanır. Bu üç şeyi garanti eder:

1. Marka bilgisi hiçbir agent'ın kodunda/prompt string'inde yaşamaz.
2. Dosya adları agent kodunda hardcode edilmez — `get_tone()` gibi tip güvenli bir
   metod çağrısı, `read("tone.md")` gibi stringly-typed bir çağrıdan daha güvenlidir
   (yazım hatası derleme/lint zamanında değil çalışma zamanında patlamaz kuralını
   ortadan kaldırır).
3. Dosyalar yalnızca ilk erişimde okunur; sonraki her `load()` çağrısı bellekten döner.

Konum sözleşmesi: ``knowledge/brands/{brand}/*.md`` — bu, `brands/{brand}/*.yaml`
(yapılandırılmış/deterministik kurallar) ile kasıtlı olarak ayrı bir ağaçtır; bkz.
ARCHITECTURE.md §3 ve `knowledge/README.md`.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path

from content_factory.utils.logging import get_logger
from content_factory.utils.paths import project_root

_logger = get_logger("knowledge.loader")

# İçinde bu işaretçi geçen dosyalar "iskelet placeholder" sayılır — henüz gerçek
# marka bilgisiyle doldurulmamış demektir (bkz. ROADMAP.md Faz 0). `validate()` bunu
# "missing"den ayrı, daha yumuşak bir uyarı türü olarak raporlar.
_PLACEHOLDER_MARKER = "Faz 0 çıktısı"


@dataclass(frozen=True)
class KnowledgeFileSpec:
    filename: str
    field: str
    description: str


# Motor-seviyesi knowledge dosyaları: HER markada bulunan, konudan bağımsız kavramlar
# (ton, yazım kuralları, hedef kitle…). Markanın KONUSUNA özgü dosyalar burada değil,
# `brands/{marka}/knowledge.yaml: topic_files` içinde tanımlanır — böylece ikinci bir
# marka eklemek bu dosyayı düzenlemeyi gerektirmez.
CORE_FILES: tuple[KnowledgeFileSpec, ...] = (
    KnowledgeFileSpec("brand.md", "brand_overview", "Marka kimliği: kim, misyon, vizyon, değerler"),
    KnowledgeFileSpec("products.md", "products", "Satılan tüm ürün kategorileri"),
    KnowledgeFileSpec("faq.md", "faq", "Sık sorulan sorular"),
    KnowledgeFileSpec("writing_rules.md", "writing_rules", "Yazım standartları"),
    KnowledgeFileSpec("seo_rules.md", "seo_rules", "Blog SEO standartları"),
    KnowledgeFileSpec(
        "content_scope.md", "content_scope", "İçerik kapsamı (kanonik kaynak: scope.yaml)"
    ),
    KnowledgeFileSpec("internal_linking.md", "internal_linking", "İç link kuralları"),
    KnowledgeFileSpec("legal_rules.md", "legal_rules", "Yasal/regülasyon kuralları"),
    KnowledgeFileSpec(
        "forbidden_claims.md", "forbidden_claims", "Yasaklı ifadeler (kanonik kaynak: brand.yaml)"
    ),
    KnowledgeFileSpec("target_audience.md", "target_audience", "Hedef müşteri profilleri"),
    KnowledgeFileSpec("tone.md", "tone", "Markanın sesi"),
    KnowledgeFileSpec("style_guide.md", "style_guide", "Biçimsel/stilistik tercihler"),
    KnowledgeFileSpec("sources.md", "sources", "Güvenilir kaynak politikası"),
)

_CORE_BY_FIELD: dict[str, KnowledgeFileSpec] = {spec.field: spec for spec in CORE_FILES}


@dataclass(frozen=True)
class BrandKnowledge:
    """Bir markanın tüm bilgi tabanının bellekteki görünümü.

    Motor-seviyesi dosyalar (`CORE_FILES`) tip güvenli alanlar olarak durur — her
    markada bulundukları için isimleri sabittir. Markanın konusuna özgü dosyalar ise
    `topics` sözlüğünde tutulur; adlarını `brands/{marka}/knowledge.yaml` belirler.

    Her değer ham markdown içeriğidir (agent'lar bunu doğrudan prompt bağlamına ekler).
    Dosya yoksa/boşsa değer `""` olur — eksik bir knowledge dosyası pipeline'ı
    çökertmez (bkz. `validate()` ile ayrı bir denetim)."""

    brand: str

    brand_overview: str = ""
    products: str = ""
    faq: str = ""
    writing_rules: str = ""
    seo_rules: str = ""
    content_scope: str = ""
    internal_linking: str = ""
    legal_rules: str = ""
    forbidden_claims: str = ""
    target_audience: str = ""
    tone: str = ""
    style_guide: str = ""
    sources: str = ""

    topics: dict[str, str] = field(default_factory=dict)
    """Markaya özgü konu dosyaları: `knowledge.yaml: topic_files`'taki `field` -> içerik."""

    _topic_specs: dict[str, KnowledgeFileSpec] = field(default_factory=dict, repr=False)
    """`compose()`'un bölüm başlıklarında kullandığı açıklamalar."""

    # -- tip güvenli okuma API'si (agent'ların çağıracağı arayüz) --------------------
    def get_brand(self) -> str:
        return self.brand_overview

    def get_products(self) -> str:
        return self.products

    def get_topic(self, field_name: str) -> str:
        """Markaya özgü bir konu dosyasının içeriği (`knowledge.yaml: topic_files`).
        Tanımsız bir ad `""` döndürür — eksik knowledge pipeline'ı çökertmez."""
        return self.topics.get(field_name, "")

    def get_faq(self) -> str:
        return self.faq

    def get_writing_rules(self) -> str:
        return self.writing_rules

    def get_seo_rules(self) -> str:
        return self.seo_rules

    def get_content_scope(self) -> str:
        return self.content_scope

    def get_internal_linking(self) -> str:
        return self.internal_linking

    def get_legal_rules(self) -> str:
        return self.legal_rules

    def get_forbidden_claims(self) -> str:
        return self.forbidden_claims

    def get_target_audience(self) -> str:
        return self.target_audience

    def get_tone(self) -> str:
        return self.tone

    def get_style_guide(self) -> str:
        return self.style_guide

    def get_sources(self) -> str:
        return self.sources

    def _spec(self, field_name: str) -> KnowledgeFileSpec:
        """Alan adını dosya tanımına çözer — önce motor dosyaları, sonra markanın konu
        dosyaları. İkisinde de yoksa yazım hatası vardır ve sessizce geçilmemelidir."""
        spec = _CORE_BY_FIELD.get(field_name) or self._topic_specs.get(field_name)
        if spec is None:
            raise KeyError(f"Bilinmeyen knowledge alanı: {field_name!r}")
        return spec

    def _content(self, field_name: str) -> str:
        return self.topics.get(field_name) or getattr(self, field_name, "")

    def compose(self, *field_names: str) -> str:
        """Birden çok alanı, aralarında başlıklarla tek bir prompt-hazır metinde
        birleştirir. Ör: ``knowledge.compose("tone", "writing_rules", "olive_oil")``
        — WriterAgent'ın sistem promptuna doğrudan eklenebilir."""
        sections: list[str] = []
        for name in field_names:
            spec = self._spec(name)
            content = self._content(name)
            if content:
                sections.append(f"## {spec.description}\n\n{content.strip()}")
        return "\n\n---\n\n".join(sections)

    def source_filenames(self, *field_names: str) -> frozenset[str]:
        """`compose(*field_names)`'in fiilen içine koyduğu (yani modele gerçekten
        gösterilen) alanların dosya adlarını döndürür — `compose()`'daki "içerik boşsa
        atla" kuralıyla birebir aynı. ResearchAgent bunu, LLM'in `sources_used`'da
        UYDURDUĞU (bu çağrıda hiç gösterilmemiş) dosya adlarını elemek için kullanır."""
        return frozenset(
            self._spec(name).filename for name in field_names if self._content(name)
        )


@dataclass(frozen=True)
class KnowledgeValidationIssue:
    file: str
    kind: str  # "missing" | "empty" | "placeholder"
    detail: str


@dataclass(frozen=True)
class KnowledgeValidationReport:
    brand: str
    issues: tuple[KnowledgeValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        """Hiç eksik/boş dosya yoksa True. Doldurulmamış placeholder'lar
        `is_valid`'i düşürmez (Faz 0'da beklenen bir durumdur) — ayrıca
        `has_placeholders` ile ayrı takip edilir."""
        return not any(issue.kind in ("missing", "empty") for issue in self.issues)

    @property
    def has_placeholders(self) -> bool:
        return any(issue.kind == "placeholder" for issue in self.issues)


class KnowledgeLoader:
    """Knowledge Base'in merkezi giriş noktası. Marka başına bir kez diskten okur,
    sonra bellekte cache'ler (bkz. modül docstring'i)."""

    def __init__(
        self, root: Path | None = None, *, topic_files: Sequence[KnowledgeFileSpec] = ()
    ) -> None:
        self._root = root or project_root()
        # Markanın konu dosyaları `brands/{marka}/knowledge.yaml`'dan gelir; loader
        # bunları YAML'dan kendisi okumaz (config okuma `settings` katmanının işidir).
        self._topic_files = tuple(topic_files)
        self._cache: dict[str, BrandKnowledge] = {}
        self._lock = threading.Lock()

    def _all_files(self) -> tuple[KnowledgeFileSpec, ...]:
        return (*CORE_FILES, *self._topic_files)

    def brand_dir(self, brand: str) -> Path:
        return self._root / "knowledge" / "brands" / brand

    def load(self, brand: str, *, force_reload: bool = False) -> BrandKnowledge:
        with self._lock:
            if not force_reload and brand in self._cache:
                return self._cache[brand]
            knowledge = self._read_from_disk(brand)
            self._cache[brand] = knowledge
            return knowledge

    def invalidate(self, brand: str | None = None) -> None:
        """`brand` verilirse yalnızca o markanın cache'ini, verilmezse tümünü temizler."""
        with self._lock:
            if brand is None:
                self._cache.clear()
            else:
                self._cache.pop(brand, None)

    def validate(self, brand: str) -> KnowledgeValidationReport:
        """Eksik/boş/doldurulmamış dosyaları raporlar. Diskten okur (cache'i kullanmaz)
        — bir CI/preflight adımı olarak bağımsız çalışabilmesi için."""
        brand_dir = self.brand_dir(brand)
        issues: list[KnowledgeValidationIssue] = []

        if not brand_dir.is_dir():
            issues.append(
                KnowledgeValidationIssue(
                    file=str(brand_dir), kind="missing", detail="marka knowledge dizini yok"
                )
            )
            return KnowledgeValidationReport(brand=brand, issues=tuple(issues))

        for spec in self._all_files():
            path = brand_dir / spec.filename
            if not path.exists():
                issues.append(
                    KnowledgeValidationIssue(file=spec.filename, kind="missing", detail="dosya yok")
                )
                continue
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                issues.append(
                    KnowledgeValidationIssue(file=spec.filename, kind="empty", detail="dosya boş")
                )
            elif _PLACEHOLDER_MARKER in content:
                issues.append(
                    KnowledgeValidationIssue(
                        file=spec.filename,
                        kind="placeholder",
                        detail="henüz gerçek içerikle doldurulmamış",
                    )
                )

        return KnowledgeValidationReport(brand=brand, issues=tuple(issues))

    def _read_from_disk(self, brand: str) -> BrandKnowledge:
        brand_dir = self.brand_dir(brand)

        def read(spec: KnowledgeFileSpec) -> str:
            path = brand_dir / spec.filename
            if not path.exists():
                _logger.warning(f"knowledge dosyası eksik brand={brand} file={spec.filename}")
                return ""
            return path.read_text(encoding="utf-8")

        return BrandKnowledge(
            brand=brand,
            **{spec.field: read(spec) for spec in CORE_FILES},
            topics={spec.field: read(spec) for spec in self._topic_files},
            _topic_specs={spec.field: spec for spec in self._topic_files},
        )


def _core_dataclass_fields() -> frozenset[str]:
    return frozenset(f.name for f in fields(BrandKnowledge)) - {"brand", "topics", "_topic_specs"}


assert _core_dataclass_fields() == {spec.field for spec in CORE_FILES}, (
    "BrandKnowledge alanları ile CORE_FILES kayıtları senkron değil"
)
