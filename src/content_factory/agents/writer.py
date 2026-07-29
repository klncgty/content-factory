"""WriterAgent — brief + araştırma notlarına göre marka sesine uygun taslağı yazar.

Diğer LLM kullanan agent'lardan farklı olarak yanıtı JSON değil, düz markdown'dır
(bkz. `prompts/writer/system.md`) — makale gövdesi için JSON'a sarıp açmanın hiçbir
faydası yok, gereksiz bir ayrıştırma adımı ve hata riski eklerdi.
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Article, ArticleStatus, Brief, WriterInput


class WriterAgent(BaseAgent[WriterInput, Article]):
    name = "writer"

    def run(self, input_data: WriterInput) -> Article:
        knowledge = self.require_knowledge()
        brief = input_data.brief
        research = input_data.research

        user_message = self.load_prompts().render_user(
            tone=knowledge.get_tone(),
            writing_rules=knowledge.get_writing_rules(),
            forbidden_words=", ".join(self.context.settings.brand.forbidden_words),
            title=brief.title,
            target_keyword=brief.target_keyword,
            audience=brief.audience or "(belirtilmemiş)",
            target_word_count=str(brief.target_word_count),
            outline=self._format_outline(brief),
            key_facts="\n".join(f"- {fact}" for fact in research.key_facts) or "(yok)",
            feedback=input_data.feedback or "(yok — ilk deneme)",
        )
        body_markdown = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        ).strip()

        if not body_markdown:
            raise AgentOutputParsingError(f"{self.name}: LLM boş bir taslak döndürdü")

        tags = self._build_tags(brief)
        return Article(
            brand=self.context.brand,
            title=brief.title,
            category=brief.topic.category,
            target_keyword=brief.target_keyword,
            secondary_keywords=brief.secondary_keywords,
            body_markdown=body_markdown,
            status=ArticleStatus.DRAFT,
            tags=tags,
            word_count=len(body_markdown.split()),
        )

    @staticmethod
    def _format_outline(brief: Brief) -> str:
        if not brief.outline:
            return "(outline verilmedi — mantıklı bir yapı sen belirle)"
        return "\n".join(f"- {s.heading}: {s.summary}" for s in brief.outline)

    @staticmethod
    def _build_tags(brief: Brief) -> list[str]:
        tags = [brief.target_keyword, *brief.secondary_keywords]
        seen: set[str] = set()
        unique_tags: list[str] = []
        for tag in tags:
            if tag and tag not in seen:
                seen.add(tag)
                unique_tags.append(tag)
        return unique_tags
