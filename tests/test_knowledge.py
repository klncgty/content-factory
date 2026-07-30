from __future__ import annotations

from pathlib import Path

import pytest

from content_factory.cli import _topic_file_specs
from content_factory.knowledge.loader import (
    CORE_FILES,
    BrandKnowledge,
    KnowledgeFileSpec,
    KnowledgeLoader,
)
from content_factory.settings.loader import Settings
from content_factory.settings.schemas import KnowledgeConfig

# Motor-seviyesi dosyalar: her markada bulunur, `CORE_FILES`'ta sabittir. Markanın
# konusuna özgü dosyalar (oleart için olive_oil.md vb.) burada DEĞİL,
# `brands/{marka}/knowledge.yaml: topic_files`'tan gelir.
EXPECTED_CORE_FILENAMES = {
    "brand.md",
    "products.md",
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
    return KnowledgeLoader(settings.root, topic_files=_topic_file_specs(settings))


# --------------------------------------------------------------------------- registry


def test_core_registry_has_expected_files() -> None:
    assert {spec.filename for spec in CORE_FILES} == EXPECTED_CORE_FILENAMES


def test_brand_knowledge_fields_match_core_registry() -> None:
    from dataclasses import fields

    field_names = {f.name for f in fields(BrandKnowledge)} - {"brand", "topics", "_topic_specs"}
    assert field_names == {spec.field for spec in CORE_FILES}


def test_brand_topic_files_come_from_config(settings: Settings, loader: KnowledgeLoader) -> None:
    """Marka-özel dosyalar Python'da değil, brands/{marka}/knowledge.yaml'da tanımlı."""
    knowledge = loader.load("oleart")
    configured = {spec.field for spec in settings.knowledge.topic_files}

    assert configured == {"olive_oil", "olive_tree", "kitchen_products"}
    assert set(knowledge.topics) == configured
    assert knowledge.get_topic("olive_oil"), "konu dosyası boş okundu"


# --------------------------------------------------------------------------- loading


def test_load_returns_populated_brand_knowledge(loader: KnowledgeLoader) -> None:
    knowledge = loader.load("oleart")
    assert knowledge.brand == "oleart"
    for spec in CORE_FILES:
        assert getattr(knowledge, spec.field), f"{spec.filename} boş okundu"


def test_typed_getters_match_underlying_fields(loader: KnowledgeLoader) -> None:
    knowledge = loader.load("oleart")
    assert knowledge.get_brand() == knowledge.brand_overview
    assert knowledge.get_products() == knowledge.products
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


# ------------------------------------------------- ikinci marka (Adım 7 kabul kriteri)


def test_second_brand_works_without_touching_python(tmp_path: Path) -> None:
    """Adım 7'nin asıl iddiası: bambaşka bir konudaki marka, `content_factory` paketinde
    HİÇBİR değişiklik yapmadan eklenebilmeli — yalnızca knowledge.yaml + .md dosyaları.

    Bu test bilinçli olarak zeytine dair hiçbir isim kullanmaz; geçmesi, motor kodunda
    Oleart'a özgü sabit kalmadığının kanıtıdır."""
    brand_knowledge_dir = tmp_path / "knowledge" / "brands" / "kahve"
    brand_knowledge_dir.mkdir(parents=True)
    (brand_knowledge_dir / "brand.md").write_text("Kahve markası.", encoding="utf-8")
    (brand_knowledge_dir / "roasting.md").write_text(
        "Kavurma sıcaklığı 210°C civarındadır.", encoding="utf-8"
    )

    config = KnowledgeConfig.model_validate(
        {
            "brand": "kahve",
            "topic_files": [
                {
                    "field": "roasting",
                    "filename": "roasting.md",
                    "description": "Kavurma bilgi tabanı",
                }
            ],
            "category_knowledge": {"espresso": ["roasting"]},
            "default_knowledge": ["roasting"],
            "grounding_fields": ["roasting"],
            "image_scenes": {"espresso": "an espresso cup on a marble counter"},
            "default_image_scene": "roasted coffee beans on dark wood",
        }
    )
    loader = KnowledgeLoader(
        tmp_path,
        topic_files=[
            KnowledgeFileSpec(
                filename=spec.filename, field=spec.field, description=spec.description
            )
            for spec in config.topic_files
        ],
    )
    knowledge = loader.load("kahve")

    # Konu dosyası okundu ve prompt'a hazır metne dönüştü.
    assert knowledge.get_topic("roasting").startswith("Kavurma")
    assert "## Kavurma bilgi tabanı" in knowledge.compose("roasting")
    assert knowledge.source_filenames("roasting") == frozenset({"roasting.md"})

    # Agent'ların okuduğu kategori eşlemeleri config'ten geliyor.
    assert config.knowledge_fields_for("espresso") == ["roasting"]
    assert config.knowledge_fields_for("bilinmeyen") == ["roasting"]
    assert config.image_scene_for("espresso") == "an espresso cup on a marble counter"
    assert config.image_scene_for(None) == "roasted coffee beans on dark wood"
