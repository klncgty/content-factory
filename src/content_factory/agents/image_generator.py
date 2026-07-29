"""ImageGeneratorAgent — makale için kapak/küçük görsel/OG görseli hazırlar.

Prompt üretimi **deterministiktir** (LLM çağırmaz): görsel prompt'u markanın görsel
diline (`knowledge.brand`) ve makale kategorisine göre şablonla kurulur — bu mekanik
bir metin birleştirme işidir, LLM'e sormanın maliyeti karşılığı bir fayda sağlamaz.

Tek bir temel görsel `ImageProvider` üzerinden üretilir, ardından `cover/thumbnail/
og-image` türevleri `image_processing.derive_image_variants` ile resize edilir
(bkz. ARCHITECTURE.md §7). Üretilen dosyalar run-scoped bir staging dizinine yazılır;
bunları nihai hedef repoya taşımak `PublisherAgent`'ın işidir.
"""

from __future__ import annotations

from pathlib import Path

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentConfigurationError, AgentOutputParsingError
from content_factory.domain.models import Article, ImageData
from content_factory.integrations.image_processing import derive_image_variants
from content_factory.knowledge.loader import BrandKnowledge
from content_factory.providers.image import ImageRequest

_CATEGORY_VISUAL_HINTS: dict[str, str] = {
    "olive_and_oil": "zeytinyağı şişesi, zeytin dalı, doğal ışık",
    "wooden_products": "zeytin ağacından ahşap mutfak ürünü, sıcak stüdyo ışığı",
}
_DEFAULT_VISUAL_HINT = "zeytin ve zeytinyağı, doğal/sıcak tonlar"


class ImageGeneratorAgent(BaseAgent[Article, Article]):
    name = "image_generator"

    def run(self, input_data: Article) -> Article:
        if not input_data.slug:
            raise AgentOutputParsingError(
                f"{self.name}: article.slug boş — SEOOptimizerAgent'tan sonra çalıştırılmalı"
            )

        knowledge = self.require_knowledge()
        image_provider = self.require_image_provider()
        config = self.load_config()
        if not config.model:
            raise AgentConfigurationError(
                f"{self.name}: config/models.yaml içinde model tanımlı değil"
            )

        prompt = self._build_prompt(input_data, knowledge)
        result = image_provider.generate(ImageRequest(prompt=prompt, model=config.model))

        output_dir = self._staging_dir(input_data.slug)
        derivative_specs = self.context.settings.engine.image_derivatives
        derivatives = derive_image_variants(
            Path(result.file_path), output_dir=output_dir, derivatives=derivative_specs
        )

        image_data = ImageData(
            base_image_path=result.file_path,
            cover_path=str(derivatives["cover"]),
            thumbnail_path=str(derivatives["thumbnail"]),
            og_image_path=str(derivatives["og_image"]),
            alt_text=input_data.title,
        )
        return input_data.model_copy(update={"image": image_data})

    def _build_prompt(self, article: Article, knowledge: BrandKnowledge) -> str:
        visual_hint = _CATEGORY_VISUAL_HINTS.get(article.category, _DEFAULT_VISUAL_HINT)
        brand_summary = knowledge.get_brand().strip()[:300]
        return (
            f"Konu: {article.title}. Görsel öğeler: {visual_hint}. "
            f"Marka bağlamı: {brand_summary}. Fotoğraf gerçekçi, reklam kalitesinde olmalı, "
            "metin/logo içermemeli."
        )

    def _staging_dir(self, slug: str) -> Path:
        run_dir = self.context.settings.resolve(
            self.context.settings.engine.run_artifacts.path_template, run_id=self.context.run_id
        )
        return run_dir / "images" / slug
