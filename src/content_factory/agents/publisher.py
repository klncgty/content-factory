"""PublisherAgent — onaylı içeriği yayın sözleşmesine (ARCHITECTURE.md §6) göre
hedef repoya yazar.

Üç şey yapar, hiçbiri git değildir (bkz. ARCHITECTURE.md §8):

1. Makaleyi `{content_dir}/{YYYY-MM-DD}-{slug}.md` olarak frontmatter'lı markdown yazar.
2. ImageGenerator'ın run'a özel staging dizininde ürettiği türevleri
   `{images_dir}/{slug}/` altına kopyalar (sözleşmedeki `og-image.webp` adına çevirerek).
3. LinkerAgent'ın planladığı `related_articles` güncellemelerini ESKİ makalelerin
   frontmatter'ına işler — prose'a dokunmadan (bkz. ARCHITECTURE.md §5).

Diske yazılan her yolu `PublisherOutput.written_paths` içinde **repo köküne göreli**
olarak döndürür; GitAgent bunları doğrudan `git add`'e verir.
"""

from __future__ import annotations

import shutil
from datetime import date as dt_date
from pathlib import Path

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentValidationError
from content_factory.domain.models import (
    Article,
    ArticleStatus,
    ImageData,
    LinkPlan,
    PublisherInput,
    PublisherOutput,
)
from content_factory.utils import frontmatter
from content_factory.utils.text import estimate_reading_time_minutes

FRONTMATTER_SCHEMA_VERSION = 1
"""Sözleşme sürümü — ileride alan eklemek eski makaleleri bozmasın diye (ARCHITECTURE.md §6)."""

_IMAGE_TARGETS: tuple[tuple[str, str, str], ...] = (
    # (ImageData alanı, hedef dosya adı, frontmatter alanı) — staging'de `og_image.webp`
    # olan türev sözleşmede `og-image.webp` adıyla yayınlanır; çeviri yalnızca burada.
    ("cover_path", "cover.webp", "cover_image"),
    ("thumbnail_path", "thumbnail.webp", "thumbnail_image"),
    ("og_image_path", "og-image.webp", "og_image"),
)


class PublisherAgent(BaseAgent[PublisherInput, PublisherOutput]):
    name = "publisher"

    def run(self, input_data: PublisherInput) -> PublisherOutput:
        article = input_data.article
        if not article.slug:
            raise AgentValidationError(
                f"{self.name}: article.slug boş — SEOOptimizerAgent'tan sonra çalıştırılmalı"
            )

        repo_root = self.context.settings.target_repo_path()
        publish_config = self.context.settings.publish
        content_dir = repo_root / publish_config.content_dir
        publish_date = article.date or dt_date.today()

        image_urls, image_paths = self._publish_images(
            article, target_dir=repo_root / publish_config.images_dir / article.slug
        )

        reading_time = estimate_reading_time_minutes(article.body_markdown)
        fields = self._build_frontmatter(
            article, publish_date=publish_date, reading_time=reading_time, image_urls=image_urls
        )
        article_path = content_dir / f"{publish_date:%Y-%m-%d}-{article.slug}.md"
        _write(article_path, frontmatter.render(fields, article.body_markdown))

        written = [article_path, *image_paths]
        written.extend(self._apply_related_updates(input_data.link_plan, content_dir))

        published = article.model_copy(
            update={
                "status": ArticleStatus.PUBLISHED,
                "date": publish_date,
                "updated": publish_date,
                "description": str(fields.get("description", "")),
                "reading_time_minutes": reading_time,
                "file_path": _relative_to(article_path, repo_root),
            }
        )
        return PublisherOutput(
            article=published, written_paths=[_relative_to(p, repo_root) for p in written]
        )

    # --------------------------------------------------------------------- frontmatter

    def _build_frontmatter(
        self,
        article: Article,
        *,
        publish_date: dt_date,
        reading_time: int,
        image_urls: dict[str, str],
    ) -> dict[str, object]:
        seo = article.seo
        fields: dict[str, object] = {
            "schema_version": FRONTMATTER_SCHEMA_VERSION,
            "title": article.title,
            "slug": article.slug,
            "date": publish_date,
            "category": article.category,
            "target_keyword": article.target_keyword,
            "secondary_keywords": list(article.secondary_keywords),
            "description": seo.meta_description if seo else article.description,
            **image_urls,
            "related_articles": list(article.related_articles),
            "reading_time_minutes": reading_time,
            "status": ArticleStatus.PUBLISHED.value,
        }
        if seo is not None:
            # `<title>` etiketi için SEO'ya göre optimize edilmiş başlık; sayfa içi H1
            # başlık (`title`) makalenin kendi başlığı olarak kalır.
            fields["meta_title"] = seo.meta_title

        # Boş/opsiyonel alanlar frontmatter'a `null` olarak yazılmaz — tüketici tarafta
        # "alan var ama değeri yok" ayrımını yapmak zorunda kalmasın.
        return {key: value for key, value in fields.items() if value not in (None, "", [])}

    # -------------------------------------------------------------------------- görseller

    def _publish_images(
        self, article: Article, *, target_dir: Path
    ) -> tuple[dict[str, str], list[Path]]:
        """Staging'deki türevleri hedef repoya kopyalar; `(frontmatter_url'leri, yazılan
        dosyalar)` döndürür.

        Görsel yoksa (henüz somut bir `ImageProvider` yapılandırılmamış olabilir, bkz.
        ROADMAP.md) yayın durmaz: görsel alanları frontmatter'dan düşer, makale yayınlanır."""
        image: ImageData | None = article.image
        if image is None:
            self.logger.info(f"görsel yok, görselsiz yayınlanıyor slug={article.slug}")
            return {}, []

        publish_config = self.context.settings.publish
        url_base = _static_url_base(publish_config.images_dir, publish_config.public_root)

        urls: dict[str, str] = {}
        written: list[Path] = []
        for field_name, target_name, frontmatter_key in _IMAGE_TARGETS:
            source = getattr(image, field_name)
            if not source or not Path(source).exists():
                self.logger.warning(
                    f"görsel türevi bulunamadı, atlanıyor slug={article.slug} alan={field_name}"
                )
                continue
            destination = target_dir / target_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            written.append(destination)
            urls[frontmatter_key] = f"{url_base}/{article.slug}/{target_name}"
        return urls, written

    # ------------------------------------------------------ eski makale frontmatter'ı

    def _apply_related_updates(self, link_plan: LinkPlan | None, content_dir: Path) -> list[Path]:
        """Her `RelatedArticleUpdate` için hedef makalenin `related_articles` listesine
        yeni slug'ı ekler. Yalnızca yapılandırılmış alan güncellenir, gövdeye dokunulmaz."""
        if link_plan is None:
            return []

        updated: list[Path] = []
        for update in link_plan.related_articles_updates:
            path = _find_article_file(content_dir, update.target_slug)
            if path is None:
                self.logger.warning(
                    f"related_articles güncellenemedi, dosya bulunamadı slug={update.target_slug}"
                )
                continue

            fields, body = frontmatter.split(path.read_text(encoding="utf-8"))
            if not fields:
                self.logger.warning(f"frontmatter okunamadı, atlanıyor path={path}")
                continue

            related = list(fields.get("related_articles") or [])
            if update.add_related in related:
                continue
            related.append(update.add_related)
            fields["related_articles"] = related
            path.write_text(frontmatter.render(fields, body), encoding="utf-8")
            updated.append(path)
        return updated


# ------------------------------------------------------------------------------ yardımcılar


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _relative_to(path: Path, root: Path) -> str:
    """Repo köküne göreli POSIX yolu — `git add` bu biçimi bekler."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def _static_url_base(images_dir: str, public_root: str) -> str:
    """Disk yolundan public URL'e: `public/blog/images` + kök `public` -> `/blog/images`.
    Statik site jeneratörlerinde `public_root` altındaki her şey site kökünden servis
    edilir; hangi dizinin o rolü üstlendiği `publish.yaml`'da yapılandırılır."""
    path = Path(images_dir)
    root = Path(public_root)
    relative = path.relative_to(root) if path.is_relative_to(root) else path
    return "/" + relative.as_posix().strip("/")


def _find_article_file(content_dir: Path, slug: str) -> Path | None:
    """Dosya adı `{YYYY-MM-DD}-{slug}.md` olduğu için slug'dan yolu doğrudan kuramayız —
    tarihi bilmiyoruz. Bu yüzden dizinde sonek eşleşmesi aranır."""
    if not content_dir.is_dir():
        return None
    matches = sorted(content_dir.glob(f"*-{slug}.md"))
    return matches[0] if matches else None
