"""ImageGeneratorAgent — makale için kapak/küçük görsel/OG görseli hazırlar.

Görsel sahnesi makalenin BAŞLIĞINDAN türetilir: başlık ne anlatıyorsa görselin öznesi
odur. Türkçe başlık, kısa bir LLM çağrısıyla İngilizce bir fotoğraf sahnesine çevrilir
(`prompts/image_generator/`), sonuç deterministik bir kompozisyon ve stil son ekiyle
birleştirilip `ImageProvider`'a verilir.

Neden LLM (07.08.2026'ya kadar deterministikti): sahne yalnızca makale KATEGORİSİNDEN
seçiliyordu (`knowledge.yaml: image_scenes`) ve markanın tanımlı iki kategorisi olduğu
için sistemin üretebileceği iki görsel vardı. Sonuç: "Zeytinyağlı Enginar Tarifi"
makalesinin görselinde enginar yoktu — her `olive_and_oil` makalesi gibi bir şişe
zeytinyağı ve zeytin dalı vardı, ve yayınlanan bütün görseller birbirinin aynısıydı.
Başlıktan sahneye geçiş mekanik bir birleştirme değil, çeviri + görselleştirme işidir;
sabit bir sözlük ise yalnızca önceden yazılmış konularda çalışır, backlog'a giren her
yeni konuda sessizce jenerik sahneye düşerdi.

Başlığın prompt'a HAM hâliyle girmediğine dikkat: bir dönem denenmiş ve model başlığı
görselin üzerine yazmaya çalışıp bozuk yazılı bir infografik üretmişti. Bu yüzden LLM'e
"başlığı yaz" değil "başlığın konusunu göster" denir, çıktı yalnızca görülebilir
nesnelerden oluşur ve `_PHOTOGRAPHIC_STYLE`'daki metin karşıtı talimatlar korunur.

LLM çağrısı başarısız olursa eski kategori sahnesine düşülür — görsel yayın için bir
önkoşul değildir (bkz. `orchestrator.py::_generate_image`), bu yüzden bu adım run'ı
asla düşürmez.

Tek bir temel görsel `ImageProvider` üzerinden üretilir, ardından `cover/thumbnail/
og-image` türevleri `image_processing.derive_image_variants` ile resize edilir
(bkz. ARCHITECTURE.md §7). Üretilen dosyalar run-scoped bir staging dizinine yazılır;
bunları nihai hedef repoya taşımak `PublisherAgent`'ın işidir.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import ClassVar

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import (
    AgentConfigurationError,
    AgentError,
    AgentOutputParsingError,
)
from content_factory.domain.models import Article, ImageData
from content_factory.integrations.image_processing import derive_image_variants
from content_factory.knowledge.loader import BrandKnowledge
from content_factory.providers.image import ImageRequest
from content_factory.providers.llm import LLMMessage, LLMRequest
from content_factory.providers.llm.exceptions import LLMError
from content_factory.utils.json_llm import parse_llm_json

_PHOTOGRAPHIC_STYLE = (
    "editorial food photography, natural window light, shallow depth of field, "
    "photorealistic, high detail. No text, no letters, no words, no labels, no logo, "
    "no watermark, no infographic, no collage, no split-screen comparison."
)
"""Negatif talimatlar prompt'un İÇİNE yazılır: flux-schnell'in ayrı bir
`negative_prompt` girdisi yok (bkz. Replicate şeması)."""

_COMPOSITIONS = (
    "shot from directly overhead as a flat lay",
    "shot from a low three-quarter angle, close to the subject",
    "shot at table level with the background falling out of focus",
    "shot from above at a slight angle, with soft shadows to one side",
    "shot close-up, filling most of the frame",
)
"""Kompozisyon varyasyonları.

Sahne başlıktan geldiği için farklı konular zaten farklı görüntü verir; bu liste aynı
konu etrafındaki makalelerin de aynı çerçeveyle çıkmasını engeller. Seçim slug'dan
türetilen bir hash ile yapılır — yani DETERMİNİSTİKTİR: aynı makale her çalıştırmada
aynı kompozisyonu alır, farklı makaleler farklı alır."""

_SCENE_MODEL_ROLE = "image_prompt"
"""Sahne metnini yazan model, görseli üreten modelden AYRI bir config girdisidir
(`models.yaml: agents.image_prompt`). `agents.image_generator` bir `ImageProvider`'ı
yapılandırır (flux-schnell); oraya bir metin modeli yazılamaz."""

_MAX_SCENE_CHARS = 300
"""Sahne tarifi için üst sınır. Model bazen tek cümle yerine paragraf yazıyor; aşırı
uzun bir prompt görsel modelinde ana özneyi sulandırır."""


class ImageGeneratorAgent(BaseAgent[Article, Article]):
    name = "image_generator"
    prompt_vars: ClassVar[frozenset[str]] = frozenset(
        {"title", "target_keyword", "headings", "brand_context"}
    )

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
        """Görsel prompt'u: başlıktan türetilen sahne + kompozisyon + stil son eki."""
        scene = self._scene_for(article, knowledge)
        composition = self._composition_for(article.slug)
        return f"{scene}, {composition}. {_PHOTOGRAPHIC_STYLE}"

    def _scene_for(self, article: Article, knowledge: BrandKnowledge) -> str:
        """Başlığın konusunu gösteren İngilizce sahne. Çağrı başarısızsa kategori
        sahnesine düşer.

        Hata YUTULUR ve yükseltilmez: görsel yayın için bir önkoşul değildir, sahne
        yazan bir modelin geçici arızası onaylanmış bir makalenin yayınlanmasını
        engellememelidir. Düşüş her zaman loglanır — sessizce jenerik görsele dönmek,
        07.08.2026'da düzeltilen sorunun ta kendisiydi."""
        try:
            scene = self._generate_scene(article, knowledge)
        except (AgentError, LLMError) as exc:
            fallback = self.context.settings.knowledge.image_scene_for(article.category)
            self.logger.warning(
                f"{self.name}: sahne üretilemedi, kategori sahnesine düşülüyor "
                f"(kategori={article.category!r}): {exc}"
            )
            return fallback
        self.logger.info(f"{self.name}: görsel sahnesi başlıktan türetildi: {scene!r}")
        return scene

    def _generate_scene(self, article: Article, knowledge: BrandKnowledge) -> str:
        prompts = self.load_prompts()
        user_message = prompts.render_user(
            title=article.title,
            target_keyword=article.target_keyword or "(belirtilmemiş)",
            headings=self._headings(article) or "(bölüm başlığı yok)",
            brand_context=knowledge.get_brand() or "(marka bağlamı yok)",
        )

        config = self.context.settings.models.for_agent(_SCENE_MODEL_ROLE)
        if not config.model:
            raise AgentConfigurationError(
                f"{self.name}: config/models.yaml içinde {_SCENE_MODEL_ROLE} modeli tanımlı değil"
            )
        request = LLMRequest(
            system_prompt=prompts.system,
            messages=[LLMMessage(role="user", content=user_message)],
            model=config.model,
            temperature=config.temperature if config.temperature is not None else 0.3,
            max_tokens=config.max_tokens or 300,
            fallback_models=config.fallback_models,
            response_format=config.response_format,
        )
        response = self.require_llm().generate(
            request, agent_name=_SCENE_MODEL_ROLE, run_id=self.context.run_id
        )

        data = parse_llm_json(response.content, agent_name=self.name)
        scene = str(data.get("scene", "")).strip() if isinstance(data, dict) else ""
        if not scene:
            raise AgentOutputParsingError(f"{self.name}: LLM yanıtında 'scene' alanı boş")
        return scene[:_MAX_SCENE_CHARS].strip().rstrip(".")

    @staticmethod
    def _headings(article: Article) -> str:
        """Gövdedeki `##` başlıkları — modele konuyu netleştirmek için verilir. Makalenin
        tamamını göndermek gereksiz: sahne başlığa dayanır, başlıklar yalnızca bağlamdır."""
        headings = [
            line.lstrip("#").strip()
            for line in article.body_markdown.splitlines()
            if line.startswith("##")
        ]
        return "\n".join(f"- {heading}" for heading in headings)

    @staticmethod
    def _composition_for(slug: str) -> str:
        """Slug'dan deterministik kompozisyon seçimi: aynı makale her zaman aynı
        çerçeveyi alır, farklı makaleler farklı. `hash()` KULLANILMAZ — Python'da
        string hash'i süreçler arasında tuzlanır ve aynı makale her run'da farklı
        kompozisyon alırdı."""
        digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()
        return _COMPOSITIONS[int(digest, 16) % len(_COMPOSITIONS)]

    def _staging_dir(self, slug: str) -> Path:
        run_dir = self.context.settings.resolve(
            self.context.settings.engine.run_artifacts.path_template, run_id=self.context.run_id
        )
        return run_dir / "images" / slug
