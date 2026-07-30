"""SEOOptimizerAgent — meta title/description, slug, anahtar kelime dağılımı.

Slug **deterministik** üretilir (LLM'e sorulmaz) — oleart.co'nun kendi derleyicisiyle
(`scripts/build-blog.mjs`) aynı slugify kuralına uyması gerekir (bkz. ARCHITECTURE.md §6);
meta title/description ise doğal dil ürettiği için LLM'e bırakılır.
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Article, SEOData
from content_factory.utils.json_llm import parse_llm_json
from content_factory.utils.text import slugify

_BODY_EXCERPT_MAX_CHARS = 800


class SEOOptimizerAgent(BaseAgent[Article, Article]):
    name = "seo_optimizer"
    prompt_vars = frozenset({"title", "target_keyword", "secondary_keywords", "body_excerpt"})

    def run(self, input_data: Article) -> Article:
        if not input_data.target_keyword:
            raise AgentOutputParsingError(f"{self.name}: article.target_keyword boş olamaz")

        user_message = self.load_prompts().render_user(
            title=input_data.title,
            target_keyword=input_data.target_keyword,
            secondary_keywords=", ".join(input_data.secondary_keywords) or "(yok)",
            body_excerpt=input_data.body_markdown.strip()[:_BODY_EXCERPT_MAX_CHARS],
        )
        content = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        )
        data = self._parse_response(content)

        slug = slugify(input_data.title)
        seo = SEOData(
            meta_title=str(data["meta_title"]),
            meta_description=str(data["meta_description"]),
            slug=slug,
            target_keyword=input_data.target_keyword,
            secondary_keywords=[str(k) for k in data.get("secondary_keywords", [])]
            or input_data.secondary_keywords,
        )
        return input_data.model_copy(update={"seo": seo, "slug": slug})

    def _parse_response(self, content: str) -> dict:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, dict):
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtı bir nesne olmalıydı, {type(data).__name__} alındı"
            )
        missing = [f for f in ("meta_title", "meta_description") if not data.get(f)]
        if missing:
            raise AgentOutputParsingError(f"{self.name}: eksik alan(lar): {missing}")
        return data
