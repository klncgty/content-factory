"""StrategistAgent — makalenin outline'ını, başlık yapısını ve içerik stratejisini
oluşturur. Konu seçimi TopicScoutAgent'ın, derin araştırma ResearchAgent'ın işidir; bu
agent ikisini birleştirip WriterAgent'ın izleyeceği yapılandırılmış bir plan (`Brief`) üretir.
"""

from __future__ import annotations

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentOutputParsingError
from content_factory.domain.models import Brief, OutlineSection, StrategistInput, Topic
from content_factory.settings.schemas import ContentBounds, WordCountBounds
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
            "content_types",
            "default_min_word_count",
            "default_max_word_count",
        }
    )

    def run(self, input_data: StrategistInput) -> Brief:
        knowledge = self.require_knowledge()
        topic = input_data.topic
        research = input_data.research
        bounds = self.context.settings.brand.content_bounds

        user_message = self.load_prompts().render_user(
            topic_title=topic.title,
            topic_category=topic.category or "(belirtilmemiş)",
            seed_keywords=", ".join(topic.seed_keywords) or "(yok)",
            key_facts="\n".join(f"- {fact}" for fact in research.key_facts) or "(yok)",
            suggested_angle=research.suggested_angle or "(belirtilmemiş)",
            target_audience=knowledge.get_target_audience(),
            writing_rules_summary=knowledge.get_writing_rules(),
            # Uzunluk kısıtı tek bir sayı değil, bir TABLO olarak verilir: Strategist
            # makalenin tipini de bu çağrıda seçtiği için, seçtiği satırın kısıtına göre
            # outline kurmalıdır. Tablodaki sayılar yalnızca modelin outline'ı doğru
            # ölçeklemesi için; nihai sınırlar seçim ayrıştırıldıktan SONRA kod tarafından
            # yeniden türetilir (bkz. `_parse_response`), yani model kendi barajını koyamaz.
            content_types=self._content_type_catalog(bounds),
            default_min_word_count=str(bounds.min_word_count),
            default_max_word_count=str(bounds.max_word_count),
        )
        content = self.call_llm(
            system_prompt=self.load_prompts().system, user_message=user_message
        )
        return self._parse_response(content, topic=topic)

    _OBSERVED_WORDS_PER_SECTION = 180
    """Writer'ın bölüm başına ölçülen ortalama uzunluğu (gpt-oss-120b, Türkçe)."""

    _MIN_SECTIONS = 3
    """Hiçbir makale bunun altında bölümlenemez — bir tarif bile malzeme/hazırlık/servis
    ayrımını hak eder. Eskiden bu taban 5'ti; 900 kelime tavanlı bir tarif için 5 bölüm
    (5 x 180 = 900) tavanı tek başına dolduruyordu."""

    @classmethod
    def _min_sections(cls, target_word_count: int) -> int:
        return max(cls._MIN_SECTIONS, -(-target_word_count // cls._OBSERVED_WORDS_PER_SECTION))

    @classmethod
    def _max_sections(cls, bounds: WordCountBounds) -> int:
        """Tavanı bölüm başına gözlenen uzunluğa bölerek bulunan üst sınır.

        Neden gerekli: modele yalnızca ALT sınır verildiğinde onu hedef sanıyor. Ölçüldü —
        562 kelime hedefli bir tarif için taban 4 bölümken model 5 bölüm kuruyordu ve
        5 x 180 = 900, tarif tavanının tam üstü. Aralık vermek, outline'ı bandın ortasına
        oturtuyor. Alt sınırın altına asla inmez."""
        ceiling = bounds.max_word_count // cls._OBSERVED_WORDS_PER_SECTION
        return max(ceiling, cls._min_sections(cls._target_word_count(bounds)))

    @classmethod
    def _target_word_count(cls, bounds: WordCountBounds) -> int:
        """Writer'a verilen hedef, tabanın %25 üstü — hedefi tam tabana koymak, modelin
        doğal sapmasında taslağı tabanın ALTINA düşürüyordu. Tavanı asla aşmaz."""
        return min(int(bounds.min_word_count * 1.25), bounds.max_word_count)

    def _content_type_catalog(self, bounds: ContentBounds) -> str:
        """Marka config'indeki tip sözlüğünü prompt'a yazılacak tabloya çevirir.

        Ortak prompt hiçbir tip adını BİLMEZ — `recipe`/`guide` gibi adlar ve açıklamaları
        `brands/{marka}/brand.yaml`'dan gelir (marka bağımsızlığı, ARCHITECTURE.md §8)."""
        rows: list[str] = []
        for name, band in bounds.by_content_type.items():
            target = self._target_word_count(band)
            description = f" — {band.description}" if band.description else ""
            rows.append(
                f"- `{name}`{description} | {band.min_word_count}-{band.max_word_count} kelime "
                f"| {self._min_sections(target)}-{self._max_sections(band)} bölüm"
            )
        return "\n".join(rows) or "(tanımlı tip yok — `content_type` alanını boş bırak)"

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

        content_type = self._resolve_content_type(data.get("content_type"))
        bounds = self.context.settings.brand.content_bounds.for_content_type(content_type)

        return Brief(
            topic=topic,
            title=str(data["title"]),
            target_keyword=str(data["target_keyword"]),
            content_type=content_type,
            secondary_keywords=[str(k) for k in data.get("secondary_keywords", [])],
            audience=data.get("audience"),
            tone=data.get("tone"),
            # Modelin yazdığı `target_word_count` KULLANILMAZ: seçilen tipin bandından
            # deterministik olarak türetilir. Model tipi seçer, sayıyı kod koyar — böylece
            # bir makale kendi barajını düşüremez.
            target_word_count=self._target_word_count(bounds),
            suggested_internal_links=[str(k) for k in data.get("suggested_internal_links", [])],
            outline=outline,
        )

    def _resolve_content_type(self, raw: object) -> str | None:
        """Modelin seçtiği tip config'de tanımlı mı? Değilse `None` döner ve makale markanın
        varsayılan sınırlarına düşer — uydurma bir tip yüzünden run'ı düşürmenin anlamı yok,
        ama sessizce geçmesinin de: düşüş loglanır."""
        known = self.context.settings.brand.content_bounds.known_content_types()
        content_type = str(raw).strip() if raw else ""
        if content_type in known:
            return content_type
        if content_type:
            self.logger.warning(
                f"{self.name}: tanınmayan content_type={content_type!r} "
                f"(tanımlı: {list(known)}) — varsayılan uzunluk sınırları kullanılacak"
            )
        return None
