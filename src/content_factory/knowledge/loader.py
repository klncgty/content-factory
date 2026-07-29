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
from dataclasses import dataclass, fields
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


# Tek kaynak: hangi dosya hangi `BrandKnowledge` alanına gider ve ne işe yarar.
# `BrandKnowledge` alanları, `KnowledgeLoader._read_from_disk` ve `validate()` hepsi
# bu listeden türetilir — yeni bir knowledge dosyası eklemek tek satırlık bir değişikliktir.
KNOWLEDGE_FILES: tuple[KnowledgeFileSpec, ...] = (
    KnowledgeFileSpec("brand.md", "brand_overview", "Marka kimliği: kim, misyon, vizyon, değerler"),
    KnowledgeFileSpec("products.md", "products", "Satılan tüm ürün kategorileri"),
    KnowledgeFileSpec("olive_oil.md", "olive_oil", "Zeytinyağı hakkında doğrulanmış bilgi tabanı"),
    KnowledgeFileSpec("olive_tree.md", "olive_tree", "Zeytin ağacı hakkında bilgi tabanı"),
    KnowledgeFileSpec(
        "kitchen_products.md", "kitchen_products", "Zeytin ağacından üretilen mutfak ürünleri"
    ),
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
    KnowledgeFileSpec("tone.md", "tone", "Oleart'ın marka sesi"),
    KnowledgeFileSpec("style_guide.md", "style_guide", "Biçimsel/stilistik tercihler"),
    KnowledgeFileSpec("sources.md", "sources", "Güvenilir kaynak politikası"),
)

_FILES_BY_FIELD: dict[str, KnowledgeFileSpec] = {spec.field: spec for spec in KNOWLEDGE_FILES}


@dataclass(frozen=True)
class BrandKnowledge:
    """Bir markanın tüm bilgi tabanının bellekteki, tip güvenli görünümü.

    Her alan ham markdown içeriğidir (agent'lar bunu doğrudan prompt bağlamına
    ekler). Dosya `KNOWLEDGE_FILES`'ta yoksa/boşsa değer `""` olur — eksik bir
    knowledge dosyası pipeline'ı çökertmez (bkz. `validate()` ile ayrı bir denetim)."""

    brand: str

    brand_overview: str = ""
    products: str = ""
    olive_oil: str = ""
    olive_tree: str = ""
    kitchen_products: str = ""
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

    # -- tip güvenli okuma API'si (agent'ların çağıracağı arayüz) --------------------
    def get_brand(self) -> str:
        return self.brand_overview

    def get_products(self) -> str:
        return self.products

    def get_olive_oil(self) -> str:
        return self.olive_oil

    def get_olive_tree(self) -> str:
        return self.olive_tree

    def get_kitchen_products(self) -> str:
        return self.kitchen_products

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

    def compose(self, *field_names: str) -> str:
        """Birden çok alanı, aralarında başlıklarla tek bir prompt-hazır metinde
        birleştirir. Ör: ``knowledge.compose("tone", "writing_rules", "olive_oil")``
        — WriterAgent'ın sistem promptuna doğrudan eklenebilir."""
        sections: list[str] = []
        for name in field_names:
            if name not in _FILES_BY_FIELD:
                raise KeyError(f"Bilinmeyen knowledge alanı: {name!r}")
            content = getattr(self, name)
            if content:
                sections.append(f"## {_FILES_BY_FIELD[name].description}\n\n{content.strip()}")
        return "\n\n---\n\n".join(sections)


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

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or project_root()
        self._cache: dict[str, BrandKnowledge] = {}
        self._lock = threading.Lock()

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

        for spec in KNOWLEDGE_FILES:
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
        values: dict[str, str] = {}
        for spec in KNOWLEDGE_FILES:
            path = brand_dir / spec.filename
            if not path.exists():
                _logger.warning(f"knowledge dosyası eksik brand={brand} file={spec.filename}")
                values[spec.field] = ""
                continue
            values[spec.field] = path.read_text(encoding="utf-8")
        return BrandKnowledge(brand=brand, **values)


def _known_fields() -> frozenset[str]:
    return frozenset(f.name for f in fields(BrandKnowledge)) - {"brand"}


assert _known_fields() == {spec.field for spec in KNOWLEDGE_FILES}, (
    "BrandKnowledge alanları ile KNOWLEDGE_FILES kayıtları senkron değil"
)
