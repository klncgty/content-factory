"""ResearchAgent — bir `Topic` hakkında yapılandırılmış, doğrulanabilir araştırma notları
hazırlar. Yalnızca knowledge base'teki referans bilgiye dayanır; WriterAgent'ın faktüel
dayanağıdır (bkz. ARCHITECTURE.md §3, `domain.models.ResearchNotes`).
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import ResearchNotes, Topic
from content_factory.utils.json_llm import parse_llm_json

_CATEGORY_KNOWLEDGE_FIELDS: dict[str, list[str]] = {
    "olive_and_oil": ["olive_oil", "olive_tree"],
    "wooden_products": ["olive_tree", "kitchen_products"],
}
_DEFAULT_KNOWLEDGE_FIELDS = ["olive_oil", "olive_tree", "kitchen_products"]


class ResearchAgent(BaseAgent[Topic, ResearchNotes]):
    name = "research"

    def run(self, input_data: Topic) -> ResearchNotes:
        knowledge = self.require_knowledge()
        fields = _CATEGORY_KNOWLEDGE_FIELDS.get(input_data.category, _DEFAULT_KNOWLEDGE_FIELDS)
        reference_knowledge = knowledge.compose(*fields)

        user_message = self.load_prompts().render_user(
            topic_title=input_data.title,
            topic_category=input_data.category or "(belirtilmemiş)",
            seed_keywords=", ".join(input_data.seed_keywords) or "(yok)",
            reference_knowledge=reference_knowledge or "(bu kategori için referans bilgi yok)",
            sources_policy=knowledge.get_sources(),
        )
        content = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        )
        return self._parse_response(content, topic=input_data)

    def _parse_response(self, content: str, *, topic: Topic) -> ResearchNotes:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, dict):
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtı bir nesne olmalıydı, {type(data).__name__} alındı"
            )
        return ResearchNotes(
            topic=topic,
            key_facts=[str(f) for f in data.get("key_facts", [])],
            suggested_angle=str(data.get("suggested_angle", "")),
            sources_used=[str(s) for s in data.get("sources_used", [])],
        )
