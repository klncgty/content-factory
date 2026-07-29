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
        # Editor kelime sayısını deterministik olarak denetliyor (editor.py::_check_word_count);
        # aynı sınırları yazma anında da vererek gereksiz reddet-yeniden yaz döngüsünü azaltıyoruz.
        bounds = self.context.settings.brand.content_bounds

        user_message = self.load_prompts().render_user(
            tone=knowledge.get_tone(),
            writing_rules=knowledge.get_writing_rules(),
            forbidden_words=", ".join(self.context.settings.brand.forbidden_words),
            title=brief.title,
            target_keyword=brief.target_keyword,
            audience=brief.audience or "(belirtilmemiş)",
            target_word_count=str(self._effective_target(brief, bounds.min_word_count)),
            min_word_count=str(bounds.min_word_count),
            max_word_count=str(bounds.max_word_count),
            words_per_section=str(self._words_per_section(brief, bounds.min_word_count)),
            outline=self._format_outline(brief),
            key_facts="\n".join(f"- {fact}" for fact in research.key_facts) or "(yok)",
            feedback=input_data.feedback or "(yok — ilk deneme)",
            previous_draft=input_data.previous_draft
            or "(yok — ilk deneme, sıfırdan yaz)",
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
    def _effective_target(brief: Brief, min_word_count: int) -> int:
        """Writer'a verilen hedef uzunluk.

        Modeller hedefin sürekli ALTINDA kalıyor: aynı brief ile ölçülen değerler hedef
        1000 kelimeyken 542-975 (ortalama ~%70). Hedefi olduğu gibi vermek makalelerin
        yarısının editor'ün alt sınırına takılıp gereksiz yeniden yazma turu doğurması
        demekti; bu yüzden hedef, alt sınırın %50 üstüne çekilerek sapmaya pay bırakılır.
        Üst sınır (`max_word_count`) prompt'ta ayrıca verildiği için aşırı uzama riski
        editor tarafından zaten yakalanır."""
        return max(brief.target_word_count, int(min_word_count * 1.5))

    @classmethod
    def _words_per_section(cls, brief: Brief, min_word_count: int) -> int:
        """Bölüm başına kelime bütçesi — modeller toplam hedeften çok buna uyuyor."""
        section_count = max(1, len(brief.outline))
        return max(80, cls._effective_target(brief, min_word_count) // section_count)

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
