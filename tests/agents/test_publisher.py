from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.publisher import PublisherAgent
from content_factory.domain.exceptions import AgentValidationError
from content_factory.domain.models import (
    Article,
    ArticleStatus,
    ImageData,
    LinkPlan,
    PublisherInput,
    RelatedArticleUpdate,
    SEOData,
)
from content_factory.utils import frontmatter


@pytest.fixture
def target_repo(tmp_path: Path, agent_context: AgentContext) -> Path:
    """`agent_context`'i geçici bir hedef repoya yönlendirir — gerçek oleart.co
    çalışma kopyasına yazmadan Publisher'ın dosya çıktısını diff'lemek için.

    `public_root` de burada sabitlenir: aşağıdaki testler URL türetmenin *davranışını*
    doğrular, markanın o gün hangi değerde olduğunu değil (bkz. `_static_url_base`;
    brands/oleart bugün `.` kullanıyor çünkü site repo kökünden servis ediliyor)."""
    repo_root = tmp_path / "site"
    repo_root.mkdir()
    settings = agent_context.settings
    agent_context.settings = dataclasses.replace(
        settings,
        publish=settings.publish.model_copy(
            update={"target_repo_path": str(repo_root), "public_root": "public"}
        ),
    )
    return repo_root


def _article(**overrides: object) -> Article:
    defaults: dict[str, object] = {
        "brand": "oleart",
        "slug": "zeytinyagi-donar-mi",
        "title": "Zeytinyağı Donar mı?",
        "category": "olive_and_oil",
        "target_keyword": "zeytinyağı donar mı",
        "secondary_keywords": ["zeytinyağı saklama"],
        "body_markdown": "## Giriş\n\nZeytinyağı soğukta bulanıklaşır.",
        "date": date(2026, 7, 30),
        "seo": SEOData(
            meta_title="Zeytinyağı Donar mı? | Oleart",
            meta_description="Zeytinyağı soğukta neden bulanıklaşır?",
            slug="zeytinyagi-donar-mi",
            target_keyword="zeytinyağı donar mı",
        ),
    }
    return Article(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_writes_article_to_contract_path(
    agent_context: AgentContext, target_repo: Path
) -> None:
    output = PublisherAgent(agent_context)(PublisherInput(article=_article()))

    expected = target_repo / "content/blog/2026-07-30-zeytinyagi-donar-mi.md"
    assert expected.exists()
    assert output.written_paths == ["content/blog/2026-07-30-zeytinyagi-donar-mi.md"]
    assert output.article.file_path == "content/blog/2026-07-30-zeytinyagi-donar-mi.md"


def test_frontmatter_follows_publish_contract(
    agent_context: AgentContext, target_repo: Path
) -> None:
    PublisherAgent(agent_context)(PublisherInput(article=_article()))

    written = (target_repo / "content/blog/2026-07-30-zeytinyagi-donar-mi.md").read_text("utf-8")
    fields, body = frontmatter.split(written)

    assert fields["schema_version"] == 1
    assert fields["title"] == "Zeytinyağı Donar mı?"
    assert fields["meta_title"] == "Zeytinyağı Donar mı? | Oleart"
    assert fields["slug"] == "zeytinyagi-donar-mi"
    assert fields["date"] == date(2026, 7, 30)
    assert fields["category"] == "olive_and_oil"
    assert fields["description"] == "Zeytinyağı soğukta neden bulanıklaşır?"
    assert fields["status"] == "published"
    assert fields["reading_time_minutes"] >= 1
    assert body.startswith("## Giriş")


def test_optional_empty_fields_are_omitted(
    agent_context: AgentContext, target_repo: Path
) -> None:
    """Boş alanlar frontmatter'a `null` olarak yazılmamalı."""
    article = _article(category=None, secondary_keywords=[], related_articles=[])
    PublisherAgent(agent_context)(PublisherInput(article=article))

    fields, _ = frontmatter.split(
        (target_repo / "content/blog/2026-07-30-zeytinyagi-donar-mi.md").read_text("utf-8")
    )
    assert "category" not in fields
    assert "secondary_keywords" not in fields
    assert "related_articles" not in fields


def test_marks_article_published(agent_context: AgentContext, target_repo: Path) -> None:
    output = PublisherAgent(agent_context)(PublisherInput(article=_article()))

    assert output.article.status is ArticleStatus.PUBLISHED
    assert output.article.description == "Zeytinyağı soğukta neden bulanıklaşır?"


def test_defaults_to_today_when_article_has_no_date(
    agent_context: AgentContext, target_repo: Path
) -> None:
    output = PublisherAgent(agent_context)(PublisherInput(article=_article(date=None)))

    assert output.article.date == date.today()
    assert output.written_paths[0].endswith(f"{date.today():%Y-%m-%d}-zeytinyagi-donar-mi.md")


def test_copies_images_and_writes_public_urls(
    agent_context: AgentContext, target_repo: Path, tmp_path: Path
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    for name in ("cover.webp", "thumbnail.webp", "og_image.webp"):
        (staging / name).write_bytes(b"fake-image")

    article = _article(
        image=ImageData(
            cover_path=str(staging / "cover.webp"),
            thumbnail_path=str(staging / "thumbnail.webp"),
            og_image_path=str(staging / "og_image.webp"),
            alt_text="Zeytinyağı şişesi",
        )
    )
    output = PublisherAgent(agent_context)(PublisherInput(article=article))

    images_dir = target_repo / "public/blog/images/zeytinyagi-donar-mi"
    # Staging'deki `og_image.webp`, sözleşmedeki `og-image.webp` adıyla yayınlanır.
    assert sorted(p.name for p in images_dir.iterdir()) == [
        "cover.webp",
        "og-image.webp",
        "thumbnail.webp",
    ]
    assert "public/blog/images/zeytinyagi-donar-mi/og-image.webp" in output.written_paths

    fields, _ = frontmatter.split(
        (target_repo / "content/blog/2026-07-30-zeytinyagi-donar-mi.md").read_text("utf-8")
    )
    assert fields["cover_image"] == "/blog/images/zeytinyagi-donar-mi/cover.webp"
    assert fields["og_image"] == "/blog/images/zeytinyagi-donar-mi/og-image.webp"


def test_public_root_dot_keeps_full_image_path(
    agent_context: AgentContext, target_repo: Path, tmp_path: Path
) -> None:
    """oleart.co bir statik site jeneratörü DEĞİL, repo kökünü olduğu gibi servis ediyor —
    yani `public/` URL'in gerçek bir parçası. `public_root: "."` bu durumu ifade eder ve
    hiçbir şey kırpılmamalıdır (bkz. brands/oleart/publish.yaml; yanlış değerle üretilen
    görsel URL'leri canlıda 404 veriyordu)."""
    settings = agent_context.settings
    agent_context.settings = dataclasses.replace(
        settings, publish=settings.publish.model_copy(update={"public_root": "."})
    )

    staging = tmp_path / "staging-public-root"
    staging.mkdir()
    for name in ("cover.webp", "thumbnail.webp", "og_image.webp"):
        (staging / name).write_bytes(b"fake-image")

    article = _article(
        image=ImageData(
            cover_path=str(staging / "cover.webp"),
            thumbnail_path=str(staging / "thumbnail.webp"),
            og_image_path=str(staging / "og_image.webp"),
            alt_text="Zeytinyağı şişesi",
        )
    )
    PublisherAgent(agent_context)(PublisherInput(article=article))

    fields, _ = frontmatter.split(
        (target_repo / "content/blog/2026-07-30-zeytinyagi-donar-mi.md").read_text("utf-8")
    )
    assert fields["cover_image"] == "/public/blog/images/zeytinyagi-donar-mi/cover.webp"
    assert fields["og_image"] == "/public/blog/images/zeytinyagi-donar-mi/og-image.webp"


def test_publishes_without_images(agent_context: AgentContext, target_repo: Path) -> None:
    """Henüz somut bir ImageProvider yapılandırılmamışken de yayın akmalı."""
    output = PublisherAgent(agent_context)(PublisherInput(article=_article(image=None)))

    fields, _ = frontmatter.split(
        (target_repo / "content/blog/2026-07-30-zeytinyagi-donar-mi.md").read_text("utf-8")
    )
    assert "cover_image" not in fields
    assert len(output.written_paths) == 1


def test_missing_image_file_is_skipped_not_fatal(
    agent_context: AgentContext, target_repo: Path, tmp_path: Path
) -> None:
    article = _article(
        image=ImageData(cover_path=str(tmp_path / "yok.webp"), alt_text="x")
    )
    output = PublisherAgent(agent_context)(PublisherInput(article=article))

    assert len(output.written_paths) == 1


def _seed_existing_article(target_repo: Path, slug: str, related: list[str]) -> Path:
    path = target_repo / "content/blog" / f"2026-01-01-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        frontmatter.render(
            {"schema_version": 1, "title": "Eski", "slug": slug, "related_articles": related},
            "## Eski makale\n\nGövde metni.",
        ),
        encoding="utf-8",
    )
    return path


def test_updates_related_articles_of_existing_article(
    agent_context: AgentContext, target_repo: Path
) -> None:
    existing = _seed_existing_article(target_repo, "erken-hasat-nedir", [])
    link_plan = LinkPlan(
        related_articles_updates=[
            RelatedArticleUpdate(
                target_slug="erken-hasat-nedir", add_related="zeytinyagi-donar-mi"
            )
        ]
    )

    output = PublisherAgent(agent_context)(
        PublisherInput(article=_article(), link_plan=link_plan)
    )

    fields, body = frontmatter.split(existing.read_text("utf-8"))
    assert fields["related_articles"] == ["zeytinyagi-donar-mi"]
    # Prose'a dokunulmamalı — yalnızca yapılandırılmış alan güncellenir (ARCHITECTURE.md §5).
    assert body.strip() == "## Eski makale\n\nGövde metni."
    assert "content/blog/2026-01-01-erken-hasat-nedir.md" in output.written_paths


def test_related_articles_update_is_idempotent(
    agent_context: AgentContext, target_repo: Path
) -> None:
    existing = _seed_existing_article(target_repo, "erken-hasat-nedir", ["zeytinyagi-donar-mi"])
    link_plan = LinkPlan(
        related_articles_updates=[
            RelatedArticleUpdate(
                target_slug="erken-hasat-nedir", add_related="zeytinyagi-donar-mi"
            )
        ]
    )

    output = PublisherAgent(agent_context)(
        PublisherInput(article=_article(), link_plan=link_plan)
    )

    fields, _ = frontmatter.split(existing.read_text("utf-8"))
    assert fields["related_articles"] == ["zeytinyagi-donar-mi"]
    # Değişiklik yoksa dosya `written_paths`'e (dolayısıyla commit'e) girmemeli.
    assert "content/blog/2026-01-01-erken-hasat-nedir.md" not in output.written_paths


def test_missing_related_target_file_is_skipped(
    agent_context: AgentContext, target_repo: Path
) -> None:
    """StateStore'da kayıtlı ama repoda bulunmayan bir makale yayını durdurmamalı."""
    link_plan = LinkPlan(
        related_articles_updates=[
            RelatedArticleUpdate(target_slug="hic-yok", add_related="zeytinyagi-donar-mi")
        ]
    )

    output = PublisherAgent(agent_context)(
        PublisherInput(article=_article(), link_plan=link_plan)
    )

    assert len(output.written_paths) == 1


def test_missing_slug_raises(agent_context: AgentContext, target_repo: Path) -> None:
    with pytest.raises(AgentValidationError):
        PublisherAgent(agent_context)(PublisherInput(article=_article(slug=None)))
