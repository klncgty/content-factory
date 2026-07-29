from __future__ import annotations

from pathlib import Path

import pytest

from content_factory.knowledge.loader import (
    KNOWLEDGE_FILES,
    BrandKnowledge,
    KnowledgeLoader,
)
from content_factory.settings.loader import Settings

EXPECTED_FILENAMES = {
    "brand.md",
    "products.md",
    "olive_oil.md",
    "olive_tree.md",
    "kitchen_products.md",
    "faq.md",
    "writing_rules.md",
    "seo_rules.md",
    "content_scope.md",
    "internal_linking.md",
    "legal_rules.md",
    "forbidden_claims.md",
    "target_audience.md",
    "tone.md",
    "style_guide.md",
    "sources.md",
}


@pytest.fixture
def loader(settings: Settings) -> KnowledgeLoader:
    return KnowledgeLoader(settings.root)


# --------------------------------------------------------------------------- registry


def test_registry_has_all_sixteen_expected_files() -> None:
    filenames = {spec.filename for spec in KNOWLEDGE_FILES}
    assert filenames == EXPECTED_FILENAMES
    assert len(KNOWLEDGE_FILES) == 16


def test_brand_knowledge_fields_match_registry() -> None:
    from dataclasses import fields

    field_names = {f.name for f in fields(BrandKnowledge)} - {"brand"}
    registry_fields = {spec.field for spec in KNOWLEDGE_FILES}
    assert field_names == registry_fields


# --------------------------------------------------------------------------- loading


def test_load_returns_populated_brand_knowledge(loader: KnowledgeLoader) -> None:
    knowledge = loader.load("oleart")
    assert knowledge.brand == "oleart"
    for spec in KNOWLEDGE_FILES:
        content = getattr(knowledge, spec.field)
        assert content, f"{spec.filename} boş okundu"


def test_typed_getters_match_underlying_fields(loader: KnowledgeLoader) -> None:
    knowledge = loader.load("oleart")
    assert knowledge.get_brand() == knowledge.brand_overview
    assert knowledge.get_products() == knowledge.products
    assert knowledge.get_olive_oil() == knowledge.olive_oil
    assert knowledge.get_olive_tree() == knowledge.olive_tree
    assert knowledge.get_kitchen_products() == knowledge.kitchen_products
    assert knowledge.get_faq() == knowledge.faq
    assert knowledge.get_writing_rules() == knowledge.writing_rules
    assert knowledge.get_seo_rules() == knowledge.seo_rules
    assert knowledge.get_content_scope() == knowledge.content_scope
    assert knowledge.get_internal_linking() == knowledge.internal_linking
    assert knowledge.get_legal_rules() == knowledge.legal_rules
    assert knowledge.get_forbidden_claims() == knowledge.forbidden_claims
    assert knowledge.get_target_audience() == knowledge.target_audience
    assert knowledge.get_tone() == knowledge.tone
    assert knowledge.get_style_guide() == knowledge.style_guide
    assert knowledge.get_sources() == knowledge.sources


def test_missing_file_yields_empty_string_not_error(tmp_path: Path) -> None:
    brand_dir = tmp_path / "knowledge" / "brands" / "ghost"
    brand_dir.mkdir(parents=True)
    (brand_dir / "brand.md").write_text("Sadece bu dosya var.", encoding="utf-8")

    loader = KnowledgeLoader(tmp_path)
    knowledge = loader.load("ghost")

    assert knowledge.brand_overview == "Sadece bu dosya var."
    assert knowledge.products == ""


# --------------------------------------------------------------------------- cache


def test_second_load_returns_cached_instance(loader: KnowledgeLoader) -> None:
    first = loader.load("oleart")
    second = loader.load("oleart")
    assert first is second


def test_force_reload_bypasses_cache(loader: KnowledgeLoader) -> None:
    first = loader.load("oleart")
    second = loader.load("oleart", force_reload=True)
    assert first is not second
    assert first == second  # içerik aynı, yalnızca kimlik farklı


def test_invalidate_specific_brand(loader: KnowledgeLoader) -> None:
    first = loader.load("oleart")
    loader.invalidate("oleart")
    second = loader.load("oleart")
    assert first is not second


def test_invalidate_all(loader: KnowledgeLoader) -> None:
    loader.load("oleart")
    loader.invalidate()
    assert loader._cache == {}  # noqa: SLF001 - iç durumu doğrulayan beyaz kutu test


# --------------------------------------------------------------------------- validation


def test_validate_oleart_reports_no_missing_or_empty_files(loader: KnowledgeLoader) -> None:
    report = loader.validate("oleart")
    assert report.is_valid, report.issues


def test_validate_oleart_has_no_remaining_placeholders(loader: KnowledgeLoader) -> None:
    """Faz 0 tamamlandı: 16 knowledge dosyasının hepsi gerçek marka/alan bilgisiyle
    dolduruldu. Bu test bir regresyon bekçisidir — yeni bir marka/dosya eklenirken
    iskelet şablon (`Faz 0 çıktısı` işaretçili) commit edilirse burada yakalanır."""
    report = loader.validate("oleart")
    assert not report.has_placeholders, report.issues


def test_validate_unknown_brand_reports_missing_directory(loader: KnowledgeLoader) -> None:
    report = loader.validate("does-not-exist")
    assert not report.is_valid
    assert report.issues[0].kind == "missing"


# --------------------------------------------------------------------------- compose()


def test_compose_joins_requested_sections_with_headers(loader: KnowledgeLoader) -> None:
    knowledge = loader.load("oleart")
    combined = knowledge.compose("tone", "writing_rules")
    assert knowledge.tone.strip() in combined
    assert knowledge.writing_rules.strip() in combined
    assert combined.index(knowledge.tone.strip()) < combined.index(knowledge.writing_rules.strip())


def test_compose_skips_empty_sections(loader: KnowledgeLoader) -> None:
    knowledge = BrandKnowledge(brand="x", tone="", writing_rules="dolu içerik")
    combined = knowledge.compose("tone", "writing_rules")
    assert "dolu içerik" in combined
    assert combined.count("---") == 0  # tek bölüm olduğu için ayırıcı yok


def test_compose_rejects_unknown_field(loader: KnowledgeLoader) -> None:
    knowledge = loader.load("oleart")
    with pytest.raises(KeyError):
        knowledge.compose("this_field_does_not_exist")


# ------------------------------------------------------- scope.yaml / brand.yaml tutarlılığı


def _normalize_tr(text: str) -> str:
    """Türkçe büyük İ/I harflerini ASCII `.lower()`'ın bozduğu (İ -> 'i̇', I -> 'i')
    durumlardan bağımsız, karşılaştırılabilir hale getirir."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def test_content_scope_matches_scope_yaml(loader: KnowledgeLoader, settings: Settings) -> None:
    """content_scope.md, ScopeGuard'ın gerçekten uyguladığı scope.yaml ile senkron
    olmalı — aksi halde WriterAgent'a verilen bağlam, gerçek enforcement'tan farklı
    bir kapsam anlatır."""
    knowledge = loader.load("oleart")
    content_scope_normalized = _normalize_tr(knowledge.content_scope)

    for group in settings.scope.groups:
        for topic in group.topics:
            assert _normalize_tr(topic) in content_scope_normalized, (
                f"scope.yaml'daki '{topic}' content_scope.md'de bulunamadı"
            )


def test_forbidden_claims_matches_brand_yaml(loader: KnowledgeLoader, settings: Settings) -> None:
    knowledge = loader.load("oleart")
    forbidden_claims_normalized = _normalize_tr(knowledge.forbidden_claims)

    for claim in settings.brand.forbidden_claims:
        assert _normalize_tr(claim) in forbidden_claims_normalized, (
            f"brand.yaml'daki yasaklı iddia '{claim}' forbidden_claims.md'de bulunamadı"
        )
