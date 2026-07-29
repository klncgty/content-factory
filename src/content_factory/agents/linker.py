"""LinkerAgent — eski makaleleri tarar, ilgili iç linkleri planlar.

Tamamen **deterministiktir** (LLM çağırmaz) — bkz. ARCHITECTURE.md §5: v1 eşleştirme
yöntemi `StateStore.find_related_articles`'ın anahtar kelime/kategori örtüşmesidir.
Eski makalelere dokunuş yalnızca yapılandırılmış `related_articles` güncellemesiyle
sınırlıdır (prose enjeksiyonu değil); yeni makalenin GÖVDESİNE eklenen linkler ise
zaten Editor'ün gözden geçireceği taze içeriktir, bu yüzden burada güvenle metne
işlenir.

`state.record_internal_link(...)` burada ÇAĞRILMAZ: bu agent Editor onayından önce
çalışır, henüz yayınlanmamış/reddedilebilecek bir makale için kalıcı link kaydı
oluşturmak StateStore'u kirletir. Kayıt, gerçek yayından sonra GitAgent/PublisherAgent
tarafından yapılır.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Article, BodyLink, LinkPlan, RelatedArticleUpdate
from content_factory.utils.text import blog_url


class LinkerOutput(BaseModel):
    article: Article
    """`new_article_body_links`'e göre gövdeye doğal iç linkler eklenmiş makale."""
    link_plan: LinkPlan


class LinkerAgent(BaseAgent[Article, LinkerOutput]):
    name = "linker"

    def run(self, input_data: Article) -> LinkerOutput:
        if not input_data.slug:
            raise AgentOutputParsingError(
                f"{self.name}: article.slug boş — SEOOptimizerAgent'tan sonra çalıştırılmalı"
            )
        state = self.require_state()
        linking_cfg = self.context.settings.seo.internal_linking

        keywords = [k for k in [input_data.target_keyword, *input_data.secondary_keywords] if k]
        candidates = state.find_related_articles(
            self.context.brand,
            keywords,
            category=input_data.category,
            exclude_slug=input_data.slug,
            limit=linking_cfg.max_related_articles,
        )

        body = input_data.body_markdown
        body_links: list[BodyLink] = []
        related_updates: list[RelatedArticleUpdate] = []
        related_slugs: list[str] = []

        for candidate in candidates:
            if not candidate.slug:
                continue
            related_slugs.append(candidate.slug)
            related_updates.append(
                RelatedArticleUpdate(target_slug=candidate.slug, add_related=input_data.slug)
            )

            anchor = self._find_anchor(body, candidate)
            if anchor is not None:
                body = self._insert_link(body, anchor, candidate.slug)
                body_links.append(BodyLink(anchor=anchor, target_slug=candidate.slug))

        link_plan = LinkPlan(
            new_article_body_links=body_links, related_articles_updates=related_updates
        )
        linked_article = input_data.model_copy(
            update={"body_markdown": body, "related_articles": related_slugs}
        )
        return LinkerOutput(article=linked_article, link_plan=link_plan)

    # ------------------------------------------------------------------------------ dahili

    @staticmethod
    def _find_anchor(body: str, candidate: Article) -> str | None:
        """Adayın hedef anahtar kelimesi metinde geçiyorsa, geçtiği HALİYLE (orijinal
        büyük/küçük harf) döndürür — link metni olarak kullanılacak."""
        if not candidate.target_keyword:
            return None
        pattern = re.compile(re.escape(candidate.target_keyword), re.IGNORECASE)
        match = pattern.search(body)
        return match.group(0) if match else None

    @staticmethod
    def _insert_link(body: str, anchor: str, target_slug: str) -> str:
        pattern = re.compile(re.escape(anchor))
        return pattern.sub(f"[{anchor}]({blog_url(target_slug)})", body, count=1)
