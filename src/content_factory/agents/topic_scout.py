"""TopicScoutAgent — SEO/trend araştırması yaparak kapsam dahilinde aday konular üretir.

Yalnızca konu SEÇER: derin araştırma yapmaz (bkz. `ResearchAgent`), makale yazmaz.
Ürettiği adaylar `Orchestrator` tarafından `ScopeGuard.pre_check`'e karşı filtrelenir —
bu agent'ın kendisi kapsam kontrolü yapmaz (bkz. ARCHITECTURE.md §2).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Topic
from content_factory.utils.json_llm import parse_llm_json


class TopicScoutRequest(BaseModel):
    max_candidates: int = Field(default=5, ge=1, le=20)


class TopicScoutAgent(BaseAgent[TopicScoutRequest, list[Topic]]):
    name = "topic_scout"

    def run(self, input_data: TopicScoutRequest) -> list[Topic]:
        knowledge = self.require_knowledge()

        user_message = self.load_prompts().render_user(
            brand_overview=knowledge.get_brand(),
            products=knowledge.get_products(),
            seed_keyword_clusters=self._format_seed_clusters(),
            used_keywords=", ".join(self._collect_used_keywords()) or "(henüz yok)",
            published_titles=self._format_published_titles(),
            max_candidates=str(input_data.max_candidates),
        )
        content = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        )
        candidates = self._parse_candidates(content)

        if not candidates:
            raise AgentOutputParsingError(f"{self.name}: LLM hiçbir geçerli aday üretmedi")

        candidates.sort(key=lambda t: t.score, reverse=True)
        return candidates[: input_data.max_candidates]

    # ------------------------------------------------------------------------------ dahili

    def _format_seed_clusters(self) -> str:
        clusters = self.context.settings.seo.keyword_clusters
        if not clusters:
            return "(tanımlı küme yok)"
        return "\n".join(f"- ({c.group}) {', '.join(c.seed_keywords)}" for c in clusters)

    def _format_published_titles(self) -> str:
        """Anahtar kelime listesi tek başına yetmiyor: model aynı konuyu farklı kelimelerle
        tekrar öneriyordu (bkz. guards/novelty_guard.py). Başlıkları görmek modelin işini
        kolaylaştırır — ama garanti değildir, asıl eleme NoveltyGuard'da deterministik yapılır."""
        state = self.context.state
        if state is None:
            return "(henüz yok)"
        recent = state.get_recent_articles(self.context.brand, limit=20)
        titles = [f"- ({article.category}) {article.title}" for article in recent if article.title]
        return "\n".join(titles) or "(henüz yok)"

    def _collect_used_keywords(self) -> list[str]:
        state = self.context.state
        if state is None:
            return []
        recent = state.get_recent_articles(self.context.brand, limit=100)
        keywords: set[str] = set()
        for article in recent:
            if article.target_keyword:
                keywords.add(article.target_keyword)
            keywords.update(article.secondary_keywords)
        return sorted(keywords)

    def _parse_candidates(self, content: str) -> list[Topic]:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, list):
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtı bir dizi olmalıydı, {type(data).__name__} alındı"
            )

        candidates: list[Topic] = []
        for item in data:
            if not isinstance(item, dict) or "title" not in item:
                self.logger.warning(f"aday konu ayrıştırılamadı, atlanıyor: {item!r}")
                continue
            try:
                candidates.append(
                    Topic(
                        brand=self.context.brand,
                        title=str(item["title"]),
                        category=item.get("category"),
                        seed_keywords=[str(k) for k in item.get("seed_keywords", [])],
                        score=float(item.get("score", 0.0)),
                        created_run_id=self.context.run_id,
                    )
                )
            except (TypeError, ValueError) as exc:
                self.logger.warning(f"aday konu ayrıştırılamadı, atlanıyor: {item!r} ({exc})")
        return candidates
