"""EditorAgent — zorunlu kalite/kapsam geçidi.

Onaysız hiçbir içerik Publisher'a ulaşmaz (bkz. ARCHITECTURE.md §2, §4, §15).
Kontroller bilinçli olarak ÜÇ katmana ve **ucuzdan pahalıya** doğru sıralanmıştır:

1. Deterministik kontroller (bedava): `brand.yaml`'daki yasaklı kelime/iddia listeleri,
   `content_bounds` kelime sayısı sınırları ve LinkerAgent'ın planladığı linklerin
   gövdeye gerçekten işlenip işlenmediği.
2. `ScopeGuard.post_check` (ucuz sınıflandırma modeli): Writer'ın konudan sapıp
   sapmadığı. Her zaman çalışır — `QAReport.scope_decision` gerçek bir ölçüme dayanmalı,
   "kontrol edilmedi" diye varsayılan bir değer taşımamalıdır.
3. LLM kalite incelemesi (pahalı model): dil, akıcılık, tekrar, ton, tutarlılık.
   Yalnızca ilk iki katman temiz geçtiyse çalışır — makale zaten reddedilecekse
   pahalı çağrıyı yapmanın bir faydası yok, Writer'a verilecek somut geri bildirim
   ilk iki katmandan zaten çıkmış durumdadır.
"""

from __future__ import annotations

from content_factory.agents.base import AgentContext, BaseAgent
from content_factory.domain.exceptions import (
    AgentConfigurationError,
    AgentOutputParsingError,
    AgentValidationError,
)
from content_factory.domain.models import (
    Article,
    EditorInput,
    LinkPlan,
    QADecision,
    QAReport,
    ResearchNotes,
    ScopeDecision,
    ScopeRejectionRecord,
)
from content_factory.guards.grounding_guard import GroundingGuard, reference_texts_for
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.utils.json_llm import parse_llm_json
from content_factory.utils.text import blog_url


class EditorAgent(BaseAgent[EditorInput, QAReport]):
    name = "editor"
    prompt_vars = frozenset(
        {
            "tone",
            "writing_rules",
            "content_scope",
            "forbidden_words",
            "forbidden_claims",
            "key_facts",
            "article_body",
        }
    )

    def __init__(self, context: AgentContext, *, scope_guard: ScopeGuard | None = None) -> None:
        super().__init__(context)
        # ScopeGuard bir agent değil, saf bir yardımcıdır — Editor onu `settings.scope`'tan
        # kendisi kurabilir. Parametre yalnızca testin sahte bir guard geçirebilmesi için var.
        self._scope_guard = scope_guard or ScopeGuard(context.settings.scope)

    def run(self, input_data: EditorInput) -> QAReport:
        article = input_data.article
        if not article.body_markdown.strip():
            raise AgentValidationError(f"{self.name}: article.body_markdown boş")

        reasons = [
            *self._check_forbidden_terms(article),
            *self._check_word_count(article),
            *self._check_link_integrity(article, input_data.link_plan),
            *self._check_grounding(article, input_data.research),
        ]

        scope_result = self._scope_guard.post_check(
            article_body=article.body_markdown,
            llm=self.require_llm(),
            prompt_loader=self.require_prompts(),
            model=self._scope_guard_model(),
            run_id=self.context.run_id,
        )
        if scope_result.decision is ScopeDecision.OUT_OF_SCOPE:
            reasons.append(f"Kapsam dışı: {scope_result.reason}")
            self._log_scope_rejection(article, scope_result.reason)

        # Katman 3 — yalnızca ilk iki katman temizse (bkz. modül docstring'i).
        if not reasons:
            try:
                reasons.extend(self._llm_quality_review(article, input_data.research))
            except AgentOutputParsingError as exc:
                # Onarım turu da başarısızsa geçit KAPALI kalır: incelemesi yapılamamış
                # bir makale asla onaylanmaz (ARCHITECTURE.md §15). Hatayı yükseltmek
                # yerine reddetmenin sebebi, tüm run'ı çökertmemektir — böylece Writer
                # bir kez daha denenir, olmazsa run `needs_review` ile temiz kapanır ve
                # görsel/state kayıtları korunur (03.08.2026'da run exit 1 ile ölmüştü).
                self.logger.error(f"{self.name}: kalite incelemesi okunamadı — geçit kapalı: {exc}")
                reasons.append(
                    "Editör kalite incelemesi okunamadı (model geçerli JSON döndürmedi); "
                    "makale güvenli tarafta kalmak için reddedildi — metni değiştirmeden "
                    "yeniden dene."
                )

        return QAReport(
            decision=QADecision.APPROVED if not reasons else QADecision.REJECTED,
            scope_decision=scope_result.decision,
            reasons=reasons,
            retry_count=input_data.retry_count,
        )

    # ------------------------------------------------------- katman 1: deterministik

    def _check_forbidden_terms(self, article: Article) -> list[str]:
        """`brand.yaml`'daki yasaklı kelime/iddia listelerine karşı birebir (case-insensitive)
        arama. Listedeki *tarif niteliğindeki* girdiler (ör. "kaynak gösterilmeyen sağlık
        iddiaları") birebir eşleşmez — onları yakalamak katman 3'ün (LLM) işidir; buradaki
        kontrol yalnızca literal ifadeler için kesin bir güvenlik ağıdır."""
        haystack = f"{article.title}\n{article.body_markdown}".lower()
        brand_config = self.context.settings.brand

        reasons: list[str] = []
        for word in brand_config.forbidden_words:
            if word.lower() in haystack:
                reasons.append(f"Yasaklı kelime kullanılmış: {word!r} — kaldır.")
        for claim in brand_config.forbidden_claims:
            if claim.lower() in haystack:
                reasons.append(f"Yasaklı iddia kullanılmış: {claim!r} — kaldır.")
        return reasons

    def _check_word_count(self, article: Article) -> list[str]:
        bounds = self.context.settings.brand.content_bounds
        word_count = len(article.body_markdown.split())
        if word_count < bounds.min_word_count:
            return [
                f"Makale çok kısa: {word_count} kelime, en az {bounds.min_word_count} olmalı — "
                "mevcut bölümleri derinleştirerek uzat."
            ]
        if word_count > bounds.max_word_count:
            return [
                f"Makale çok uzun: {word_count} kelime, en fazla {bounds.max_word_count} olmalı — "
                "tekrar eden bölümleri kısalt."
            ]
        return []

    @staticmethod
    def _check_link_integrity(article: Article, link_plan: LinkPlan | None) -> list[str]:
        """LinkerAgent'ın planladığı her gövde linki metne gerçekten işlenmiş mi?

        Burada bilinçli olarak bir *minimum iç link sayısı* dayatılmaz: ilk makalelerde
        korpus boş olduğu için ilişkilendirilecek makale yoktur ve böyle bir kural
        pipeline'ı kalıcı olarak kilitlerdi (bkz. `seo.yaml: min_related_articles` — o
        değer bir hedeftir, bir geçit koşulu değil)."""
        if link_plan is None:
            return []
        reasons: list[str] = []
        for link in link_plan.new_article_body_links:
            url = blog_url(link.target_slug)
            if f"]({url})" not in article.body_markdown:
                reasons.append(
                    f"Planlanan iç link gövdede bulunamadı: {link.anchor!r} -> {url}"
                )
        return reasons

    def _check_grounding(self, article: Article, research: ResearchNotes | None) -> list[str]:
        """Makaledeki sayısal iddialar knowledge base'e (+ araştırma notlarına) dayanıyor mu?

        Katman 3'teki LLM incelemesi bu vakaları kaçırıyor: makul görünen bir sayıyı
        ("ideal saklama 14-18°C") model onaylıyor, çünkü sayının kaynakta GEÇİP
        geçmediğini kontrol etmiyor. Bu deterministik ölçüm ise tam olarak onu yapar
        (bkz. `guards/grounding_guard.py`)."""
        knowledge = self.require_knowledge()
        # Hangi knowledge alanlarının referans alınacağı markaya özgüdür
        # (`brands/{marka}/knowledge.yaml: grounding_fields`).
        fields = self.context.settings.knowledge.grounding_fields
        guard = GroundingGuard(
            reference_texts_for(
                [knowledge.compose(field) for field in fields],
                research.key_facts if research is not None else [],
            )
        )
        result = guard.check(article.body_markdown)
        if result.is_grounded:
            return []

        enforce = self.context.settings.engine.grounding.enforce
        mode = "reddedildi" if enforce else "yalnızca uyarı (engine.yaml: grounding.enforce)"
        self.logger.warning(
            f"{self.name}: {len(result.ungrounded)} kaynaksız sayısal iddia [{mode}]: "
            f"{[c.text for c in result.ungrounded]}"
        )
        # Uyarı modunda bulgular karara katılmaz — guard'ın gerçek makalelerdeki
        # isabeti, yayın turunu riske atmadan ölçülebilsin diye (bkz. GroundingConfig).
        return result.reasons() if enforce else []

    # ------------------------------------------------------------ katman 2: kapsam

    def _scope_guard_model(self) -> str:
        """ScopeGuard'ın sınıflandırma modeli Editor'ünkinden AYRIDIR (`config/models.yaml:
        agents.scope_guard`) — ucuz/hızlı bir sınıflandırıcı yeterli."""
        model = self.context.settings.models.for_agent("scope_guard").model
        if not model:
            model = self.load_config().model
        if not model:
            raise AgentConfigurationError(
                f"{self.name}: config/models.yaml içinde scope_guard/editor modeli tanımlı değil"
            )
        return model

    def _log_scope_rejection(self, article: Article, reason: str) -> None:
        if self.context.state is None:
            return
        self.context.state.log_scope_rejection(
            ScopeRejectionRecord(
                brand=self.context.brand,
                run_id=self.context.run_id,
                stage="editor",
                reason=reason,
                payload_snippet=article.title,
            )
        )

    # ------------------------------------------------------ katman 3: LLM kalite

    def _llm_quality_review(self, article: Article, research: ResearchNotes | None) -> list[str]:
        knowledge = self.require_knowledge()
        prompts = self.load_prompts()

        key_facts = research.key_facts if research is not None else []
        user_message = prompts.render_user(
            tone=knowledge.get_tone(),
            writing_rules=knowledge.get_writing_rules(),
            content_scope=knowledge.get_content_scope(),
            forbidden_words=", ".join(self.context.settings.brand.forbidden_words) or "(yok)",
            forbidden_claims="\n".join(
                f"- {claim}" for claim in self.context.settings.brand.forbidden_claims
            )
            or "(yok)",
            key_facts="\n".join(f"- {fact}" for fact in key_facts) or "(araştırma notu yok)",
            article_body=article.body_markdown,
        )
        content = self.call_llm(system_prompt=prompts.system, user_message=user_message)
        try:
            return self._parse_review(content)
        except AgentOutputParsingError as exc:
            # Biçim sapması geçici bir arızadır, makale hakkında bir yargı DEĞİLDİR:
            # 03.08.2026'da model JSON yerine ayrıştırılamayan bir yanıt döndürdü ve
            # yayın turu tamamen düştü. Kararı burada uydurmak yerine (ne onay ne red)
            # aynı incelemeyi bir kez daha, biçim şartı hatırlatılarak isteriz.
            self.logger.warning(
                f"{self.name}: yanıt ayrıştırılamadı, biçim onarımı deneniyor: {exc}"
            )
            repaired = self.call_llm(
                system_prompt=prompts.system,
                user_message=(
                    f"{user_message}\n\n## ÖNEMLİ — BİÇİM\n\n"
                    "Önceki yanıtın geçerli JSON değildi. Yalnızca tek bir JSON nesnesi "
                    "döndür; öncesine/sonrasına açıklama, başlık veya markdown ekleme. "
                    'Metin içindeki tırnakları kaçır (\\"). Şema: '
                    '{"decision": "approved" veya "rejected", "reasons": ["..."]}'
                ),
                temperature=0.0,
            )
            return self._parse_review(repaired)

    def _parse_review(self, content: str) -> list[str]:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, dict) or "decision" not in data:
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtında 'decision' alanı bulunamadı"
            )

        decision = str(data["decision"]).strip().lower()
        reasons = [str(r) for r in data.get("reasons", []) if str(r).strip()]

        if decision == QADecision.APPROVED.value:
            return []
        if decision == QADecision.REJECTED.value:
            # Gerekçesiz bir red, Writer'a hiçbir şey söylemez — retry döngüsü aynı
            # taslağı tekrar üretir. Bu yüzden en az bir gerekçe garanti edilir.
            return reasons or ["Editör makaleyi gerekçe belirtmeden reddetti."]
        raise AgentOutputParsingError(
            f"{self.name}: geçersiz 'decision' değeri: {decision!r}"
        )
