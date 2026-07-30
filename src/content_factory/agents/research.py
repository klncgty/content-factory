"""ResearchAgent — bir `Topic` hakkında yapılandırılmış, doğrulanabilir araştırma notları
hazırlar. Yalnızca knowledge base'teki referans bilgiye dayanır; WriterAgent'ın faktüel
dayanağıdır (bkz. ARCHITECTURE.md §3, `domain.models.ResearchNotes`).
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import ResearchNotes, Topic
from content_factory.utils.json_llm import parse_llm_json


class ResearchAgent(BaseAgent[Topic, ResearchNotes]):
    name = "research"
    prompt_vars = frozenset(
        {"topic_title", "topic_category", "seed_keywords", "reference_knowledge", "sources_policy"}
    )

    def run(self, input_data: Topic) -> ResearchNotes:
        knowledge = self.require_knowledge()
        # Hangi kategoride hangi konu dosyalarının okunacağı markaya özgüdür ve
        # `brands/{marka}/knowledge.yaml`'da tanımlanır — bkz. ARCHITECTURE.md §3.
        fields = self.context.settings.knowledge.knowledge_fields_for(input_data.category)
        reference_knowledge = knowledge.compose(*fields)
        valid_sources = knowledge.source_filenames(*fields)

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
        return self._parse_response(content, topic=input_data, valid_sources=valid_sources)

    def _parse_response(
        self, content: str, *, topic: Topic, valid_sources: frozenset[str]
    ) -> ResearchNotes:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, dict):
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtı bir nesne olmalıydı, {type(data).__name__} alındı"
            )
        claimed_sources = [str(s) for s in data.get("sources_used", [])]
        sources_used = [s for s in claimed_sources if s in valid_sources]
        fabricated = [s for s in claimed_sources if s not in valid_sources]
        if fabricated:
            self.logger.warning(
                f"{self.name}: uydurma kaynak(lar) atıldı (bu çağrıda gösterilmemiş "
                f"dosyalar): {fabricated}"
            )
        return ResearchNotes(
            topic=topic,
            key_facts=[str(f) for f in data.get("key_facts", [])],
            suggested_angle=str(data.get("suggested_angle", "")),
            sources_used=sources_used,
        )
