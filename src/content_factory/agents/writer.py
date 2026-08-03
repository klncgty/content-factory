"""WriterAgent — brief + araştırma notlarına göre marka sesine uygun taslağı yazar.

Diğer LLM kullanan agent'lardan farklı olarak yanıtı JSON değil, düz markdown'dır
(bkz. `prompts/writer/system.md`) — makale gövdesi için JSON'a sarıp açmanın hiçbir
faydası yok, gereksiz bir ayrıştırma adımı ve hata riski eklerdi.

Uzunluk garantisi: modeller prompt'taki hedefe güvenilir uymuyor (hedef 1000 iken
ölçülen 635-741 kelime). Bu yüzden Writer, Editor'ün alt sınırını prompt'a yazmakla
yetinmez; taslağı üretir üretmez kelime sayısını KENDİSİ ölçer ve tabanın altındaysa
aynı taslağı genişletme turlarıyla uzatır (bkz. `_expand_to_floor`). Böylece kısa
taslaklar Editor'e hiç ulaşmaz ve pahalı Writer->SEO->Linker->Editor retry döngüsü
uzunluk yüzünden dönmez.
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Article, ArticleStatus, Brief, ResearchNotes, WriterInput


class WriterAgent(BaseAgent[WriterInput, Article]):
    name = "writer"
    prompt_vars = frozenset(
        {
            "tone",
            "writing_rules",
            "forbidden_words",
            "title",
            "target_keyword",
            "audience",
            "target_word_count",
            "min_word_count",
            "max_word_count",
            "words_per_section",
            "outline",
            "key_facts",
            "feedback",
            "previous_draft",
        }
    )

    _FLOOR_MARGIN = 100
    """Writer'ın kendi tabanı, Editor'ün alt sınırının bu kadar ÜSTÜNDEDİR
    (800 -> 900). Alt sınırın tam üstünü hedeflemek yeterli değil: SEO/Linker
    adımları metni değiştirmez ama modelin kelime sayımı bizimkiyle birebir örtüşmez;
    pay bırakılmazsa taslak sınırın birkaç kelime altında kalıp yine reddedilir."""

    _MAX_EXPANSION_PASSES = 2
    """Taban tutturulamadığında yapılacak en fazla genişletme turu. Her tur ucuz bir
    ek LLM çağrısıdır; iki turda tabana ulaşamayan bir taslak zaten Editor retry
    döngüsüne düşer, burada sonsuz döngüye girmenin anlamı yok."""

    def run(self, input_data: WriterInput) -> Article:
        brief = input_data.brief

        body_markdown = self._generate(
            brief,
            input_data.research,
            feedback=input_data.feedback,
            previous_draft=input_data.previous_draft,
        )
        if not body_markdown:
            raise AgentOutputParsingError(f"{self.name}: LLM boş bir taslak döndürdü")

        body_markdown = self._expand_to_floor(brief, input_data.research, body_markdown)

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

    def _generate(
        self,
        brief: Brief,
        research: ResearchNotes,
        *,
        feedback: str | None,
        previous_draft: str | None,
    ) -> str:
        """Tek bir Writer LLM çağrısı. Hem ilk taslak hem genişletme turları bu yolu
        kullanır — genişletme, "önceki taslağı şu geri bildirimle revize et" işinin
        özel bir hâlidir, ayrı bir prompt gerektirmez."""
        knowledge = self.require_knowledge()
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
            feedback=feedback or "(yok — ilk deneme)",
            previous_draft=previous_draft or "(yok — ilk deneme, sıfırdan yaz)",
        )
        return self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        ).strip()

    def _expand_to_floor(self, brief: Brief, research: ResearchNotes, body_markdown: str) -> str:
        """Taslak tabanın altındaysa, SIFIRDAN YAZDIRMADAN genişletme turları uygular.

        Her tur, mevcut taslağı `previous_draft` olarak ve eksik kelime sayısını somut
        bir geri bildirim olarak verir — user prompt'un "önceki taslak varsa revize et"
        yolu devreye girer. Bir tur taslağı UZATMADIYSA (boş/daha kısa yanıt) eldeki en
        uzun taslak korunur; kötü bir genişletme, iyi bir taslağı asla ezmez."""
        floor = self._word_floor(self.context.settings.brand.content_bounds.min_word_count)
        max_words = self.context.settings.brand.content_bounds.max_word_count

        for attempt in range(1, self._MAX_EXPANSION_PASSES + 1):
            word_count = len(body_markdown.split())
            if word_count >= floor:
                return body_markdown

            self.logger.warning(
                f"taslak {word_count} kelime, taban {floor} — "
                f"genişletme turu {attempt}/{self._MAX_EXPANSION_PASSES}"
            )
            expanded = self._generate(
                brief,
                research,
                feedback=(
                    f"- Makale çok kısa: {word_count} kelime, en az {floor} kelime olmalı "
                    f"(üst sınır {max_words}). Önceki taslaktaki hiçbir bölümü ve cümleyi "
                    f"silme; her `##` bölümüne araştırma notlarına dayanan 1-2 yeni paragraf "
                    f"ekleyerek genişlet."
                ),
                previous_draft=body_markdown,
            )
            if len(expanded.split()) > word_count:
                body_markdown = expanded
            else:
                self.logger.warning(
                    "genişletme turu taslağı uzatmadı, mevcut taslak korunuyor"
                )

        final_count = len(body_markdown.split())
        if final_count < floor:
            self.logger.warning(
                f"genişletme turlarına rağmen taslak {final_count} kelime (taban {floor}) — "
                "karar Editor'e bırakılıyor"
            )
        return body_markdown

    @classmethod
    def _word_floor(cls, min_word_count: int) -> int:
        return min_word_count + cls._FLOOR_MARGIN

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
