"""StrategistAgent — makalenin outline'ını, başlık yapısını ve içerik stratejisini
oluşturur. Konu seçimi TopicScoutAgent'ın, derin araştırma ResearchAgent'ın işidir; bu
agent ikisini birleştirip WriterAgent'ın izleyeceği yapılandırılmış bir plan (`Brief`) üretir.
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Brief, OutlineSection, StrategistInput, Topic
from content_factory.utils.json_llm import parse_llm_json


class StrategistAgent(BaseAgent[StrategistInput, Brief]):
    name = "strategist"
    prompt_vars = frozenset(
        {
            "topic_title",
            "topic_category",
            "seed_keywords",
            "key_facts",
            "suggested_angle",
            "target_audience",
            "writing_rules_summary",
            "min_word_count",
            "max_word_count",
            "target_word_count",
            "min_sections",
        }
    )

    def run(self, input_data: StrategistInput) -> Brief:
        knowledge = self.require_knowledge()
        topic = input_data.topic
        research = input_data.research

        # Outline'ın bölüm sayısı, makalenin uzunluk alt sınırını belirleyen asıl kaldıraç:
        # yazar bölüm başına ortalama ~180 kelime yazıyor, dolayısıyla 4 bölümlük bir
        # outline 800 kelime alt sınırını yapısal olarak tutturamıyor (ölçüm: 4 bölüm ->
        # 351 kelime, 5 bölüm -> 816 kelime). Taban bölüm sayısı buradan hesaplanır.
        bounds = self.context.settings.brand.content_bounds
        target_word_count = int(bounds.min_word_count * 1.25)

        user_message = self.load_prompts().render_user(
            topic_title=topic.title,
            topic_category=topic.category or "(belirtilmemiş)",
            seed_keywords=", ".join(topic.seed_keywords) or "(yok)",
            key_facts="\n".join(f"- {fact}" for fact in research.key_facts) or "(yok)",
            suggested_angle=research.suggested_angle or "(belirtilmemiş)",
            target_audience=knowledge.get_target_audience(),
            writing_rules_summary=knowledge.get_writing_rules(),
            min_word_count=str(bounds.min_word_count),
            max_word_count=str(bounds.max_word_count),
            target_word_count=str(target_word_count),
            min_sections=str(self._min_sections(target_word_count)),
        )
        content = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        )
        return self._parse_response(content, topic=topic)

    _OBSERVED_WORDS_PER_SECTION = 180
    """Writer'ın bölüm başına ölçülen ortalama uzunluğu (gpt-oss-120b, Türkçe)."""

    @classmethod
    def _min_sections(cls, target_word_count: int) -> int:
        return max(5, -(-target_word_count // cls._OBSERVED_WORDS_PER_SECTION))

    def _parse_response(self, content: str, *, topic: Topic) -> Brief:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, dict):
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtı bir nesne olmalıydı, {type(data).__name__} alındı"
            )

        required = ("title", "target_keyword")
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise AgentOutputParsingError(f"{self.name}: eksik alan(lar): {missing}")

        outline_data = data.get("outline", [])
        outline = [
            OutlineSection(heading=str(section["heading"]), summary=str(section.get("summary", "")))
            for section in outline_data
            if isinstance(section, dict) and "heading" in section
        ]

        return Brief(
            topic=topic,
            title=str(data["title"]),
            target_keyword=str(data["target_keyword"]),
            secondary_keywords=[str(k) for k in data.get("secondary_keywords", [])],
            audience=data.get("audience"),
            tone=data.get("tone"),
            target_word_count=int(data.get("target_word_count", 1000)),
            suggested_internal_links=[str(k) for k in data.get("suggested_internal_links", [])],
            outline=outline,
        )
