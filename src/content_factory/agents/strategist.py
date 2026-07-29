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

    def run(self, input_data: StrategistInput) -> Brief:
        knowledge = self.require_knowledge()
        topic = input_data.topic
        research = input_data.research

        user_message = self.load_prompts().render_user(
            topic_title=topic.title,
            topic_category=topic.category or "(belirtilmemiş)",
            seed_keywords=", ".join(topic.seed_keywords) or "(yok)",
            key_facts="\n".join(f"- {fact}" for fact in research.key_facts) or "(yok)",
            suggested_angle=research.suggested_angle or "(belirtilmemiş)",
            target_audience=knowledge.get_target_audience(),
            writing_rules_summary=knowledge.get_writing_rules(),
        )
        content = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        )
        return self._parse_response(content, topic=topic)

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
