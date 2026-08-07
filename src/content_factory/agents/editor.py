"""EditorAgent — zorunlu kalite/kapsam geçidi.

Onaysız hiçbir içerik Publisher'a ulaşmaz (bkz. ARCHITECTURE.md §2, §4, §15).
Kontroller bilinçli olarak ÜÇ katmana ve **ucuzdan pahalıya** doğru sıralanmıştır:

1. Deterministik kontroller (bedava): `brand.yaml`'daki yasaklı kelime/iddia listeleri,
   `content_bounds` kelime sayısı sınırları ve LinkerAgent'ın planladığı linklerin
   gövdeye gerçekten işlenip işlenmediği.
2. `ScopeGuard.post_check` (ucuz sınıflandırma modeli): Writer'ın konudan sapıp
   sapmadığı. Her zaman çalışır — `QAReport.scope_decision` gerçek bir ölçüme dayanmalı,
   "kontrol edilmedi" diye varsayılan bir değer taşımamalıdır.
3. LLM kalite incelemesi (pahalı model): yalnızca ÖZNEL yargı — akıcılık, tekrar, ton,
   iç tutarlılık. Yalnızca ilk iki katman temiz geçtiyse çalışır: makale zaten
   reddedilecekse pahalı çağrıyı yapmanın bir faydası yok, Writer'a verilecek somut
   geri bildirim ilk iki katmandan zaten çıkmış durumdadır.

LLM katmanına duyulan güven SINIRLIDIR ve bu bilinçlidir. 06.08.2026 yayın run'ında
model aynı makaleyi dört kez farklı gerekçelerle reddetti; gerekçelerin çoğu uydurmaydı
(metinde geçmeyen ifadeler), biri ihlal saymadığı maddeleri sıralayan bir kontrol listesi
raporuydu, sonuncusu İngilizce yazılmıştı. Bu yüzden katman 3 iki taraftan kıskaca alındı:

- ÇIKTI BİÇİMİ: yanıt `models.yaml: agents.editor.response_format` ile yapısal çıktıya
  (JSON) zorlanır; destekleyen sağlayıcıda model gramer seviyesinde şema dışına çıkamaz.
- İDDİA DOĞRULAMA: her gerekçe makaleden BİREBİR bir alıntı taşımak zorundadır ve
  `guards/review_guard.py` o alıntının metinde gerçekten geçtiğini ölçer. Geçmeyen
  gerekçe karara katılmaz. Doğrulanan gerekçe kalmazsa makale ONAYLANIR — çünkü elde
  gösterilebilir tek bir ihlal bile yoktur.
"""

from __future__ import annotations

import re

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
from content_factory.guards.review_guard import ReviewFinding, ReviewGuard
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.utils.json_llm import parse_llm_json
from content_factory.utils.text import blog_url

_META_ARTIFACT = re.compile(
    # Satır başındaki "**Yeni paragraf:**" türü etiketler ve "(genişletildi)" gibi
    # süreç notları. Kalıp bilinçli olarak DAR: makalede meşru biçimde geçebilecek
    # "yeni" veya "bölüm" sözcüklerini değil, yalnızca iki nokta üst üste ile biten
    # etiket biçimini ve parantez içindeki süreç notlarını arar.
    r"(?im)^\s*[*_#\s]*((?:yeni|ek|ekstra|ilave|eklenen|genişletilmiş|revize\s+edilmiş)"
    r"\s+(?:paragraf|bölüm|cümle|metin|makale))[*_\s]*:"
    r"|\((?:genişletildi|revize\s+edildi|eklendi\s*-\s*uzunluk)\)",
)


class EditorAgent(BaseAgent[EditorInput, QAReport]):
    name = "editor"
    prompt_vars = frozenset(
        {
            "tone",
            "writing_rules",
            # `content_scope` bilinçli olarak YOK: kapsam kararı katman 2'de
            # (`ScopeGuard.post_check`) deterministik olarak veriliyor. LLM'e ayrıca
            # sormak, hem prompt'u büyütüyor hem de modele gerekçe listesine ekleyeceği
            # fazladan bir kontrol listesi maddesi veriyordu.
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
            *self._check_meta_artifacts(article),
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
        review_unavailable = False
        if not reasons:
            try:
                reasons.extend(self._llm_quality_review(article, input_data.research))
            except AgentOutputParsingError as exc:
                # Onarım turu da başarısızsa geçit KAPALI kalır: incelemesi yapılamamış
                # bir makale asla onaylanmaz (ARCHITECTURE.md §15). Hatayı yükseltmek
                # yerine reddetmenin sebebi, tüm run'ı çökertmemektir — böylece run
                # `needs_review` ile temiz kapanır ve görsel/state kayıtları korunur
                # (03.08.2026'da run exit 1 ile ölmüştü).
                self.logger.error(f"{self.name}: kalite incelemesi okunamadı — geçit kapalı: {exc}")
                review_unavailable = True
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
            # Bu bayrak Orchestrator'a "makale hakkında bir yargı verilmedi" der; oradaki
            # retry döngüsü Writer'ı boşuna çalıştırmamak için buna bakar (bkz.
            # `orchestrator.py::_review_with_retries`).
            review_unavailable=review_unavailable,
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

    @staticmethod
    def _check_meta_artifacts(article: Article) -> list[str]:
        """Yazma sürecine ait talimat/etiket kalıntıları gövdeye sızmış mı?

        Gerçek vaka (04.08.2026): Writer'ın uzunluk genişletme turunda verilen "yeni
        paragraf ekle" talimatını model bir başlık sanıp eklediği her paragrafın önüne
        "**Yeni paragraf:**" yazdı; makale bu hâliyle yayınlandı ve elle geri alınmak
        zorunda kalındı. LLM kalite incelemesi (katman 3) bunu ONAYLADI — okuyucuya
        anlamsız görünen bu tür artıklar modelin dikkatini çekmiyor.

        Kontrol deterministik: yayın için ölümcül, tarifi kolay ve LLM'e sormaya
        değmeyecek kadar kesin bir kusur."""
        leaks = _META_ARTIFACT.findall(article.body_markdown)
        if not leaks:
            return []
        unique = sorted({match.strip() for match in leaks})
        return [
            f"Metinde yazma sürecine ait etiket kalıntısı var: {unique} — bunları "
            "kaldır, makale baştan öyle yazılmış gibi tek parça okunmalı."
        ]

    def _check_word_count(self, article: Article) -> list[str]:
        """Sınırlar makalenin İÇERİK TİPİNE göre çözülür (`brand.yaml:
        content_bounds.by_content_type`) — Writer da aynı çözümlemeyi `brief.content_type`
        üzerinden yapar. Tek bir global taban, tarifleri doğal uzunluklarının üstüne
        çıkmaya zorluyor ve dolgu ürettiriyordu (bkz. `ContentBounds`)."""
        bounds = self.context.settings.brand.content_bounds.for_content_type(article.content_type)
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
            findings = self._parse_review(content)
        except AgentOutputParsingError as exc:
            # Biçim sapması geçici bir arızadır, makale hakkında bir yargı DEĞİLDİR:
            # 03.08.2026'da model JSON yerine ayrıştırılamayan bir yanıt döndürdü ve
            # yayın turu tamamen düştü. Kararı burada uydurmak yerine (ne onay ne red)
            # aynı incelemeyi bir kez daha, biçim şartı hatırlatılarak isteriz.
            # (`response_format` destekleyen sağlayıcıda bu yol pratikte hiç çalışmaz;
            # Replicate gibi yapısal çıktısı olmayan bir fallback'te hâlâ gerekli.)
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
                    '{"decision": "approved" veya "rejected", "reasons": '
                    '[{"alinti": "...", "sorun": "...", "duzeltme": "..."}]}'
                ),
                temperature=0.0,
            )
            findings = self._parse_review(repaired)

        return self._verify_findings(article, findings)

    def _verify_findings(self, article: Article, findings: list[ReviewFinding]) -> list[str]:
        """LLM'in her iddiasını makaleye karşı sınar; doğrulanmayanı karara katmaz.

        Doğrulanan gerekçe kalmazsa liste BOŞ döner, yani makale onaylanır. Bu, "model
        reddetti ama gösterebildiği hiçbir ihlal yok" durumunun tek doğru sonucudur:
        aksi hâlde Writer, metinde bulunmayan bir sorunu düzeltmeye çalışır ve retry
        döngüsü kendi kendine dönerek `needs_review`e düşer (06.08.2026'da olan tam olarak
        buydu)."""
        review = ReviewGuard(f"{article.title}\n{article.body_markdown}").verify(findings)
        for discarded in review.discarded:
            self.logger.warning(
                f"{self.name}: editör iddiası doğrulanamadı, karara katılmıyor "
                f"[{discarded.reason}]: alıntı={discarded.finding.quote!r} "
                f"gerekçe={discarded.finding.problem!r}"
            )
        if findings and not review.has_verified_findings:
            self.logger.warning(
                f"{self.name}: editörün {len(findings)} gerekçesinin tamamı doğrulanamadı "
                "— makale bu katmandan geçiyor"
            )
        return review.feedback_lines()

    def _parse_review(self, content: str) -> list[ReviewFinding]:
        data = parse_llm_json(content, agent_name=self.name)
        if not isinstance(data, dict) or "decision" not in data:
            raise AgentOutputParsingError(
                f"{self.name}: LLM yanıtında 'decision' alanı bulunamadı"
            )

        decision = str(data["decision"]).strip().lower()
        if decision == QADecision.APPROVED.value:
            return []
        if decision != QADecision.REJECTED.value:
            raise AgentOutputParsingError(
                f"{self.name}: geçersiz 'decision' değeri: {decision!r}"
            )

        # `reasons` bir liste değilse (model tek bir string ya da nesne döndürdüyse)
        # üzerinde dolaşmak anlamsız sonuçlar üretirdi — bir string'in elemanları
        # karakterlerdir.
        raw_reasons = data.get("reasons") or []
        if not isinstance(raw_reasons, list):
            raw_reasons = [raw_reasons]

        findings = [
            finding
            for finding in (self._as_finding(item) for item in raw_reasons)
            if finding is not None
        ]
        if not findings:
            # Gerekçesiz bir red, Writer'a hiçbir şey söylemez — retry döngüsü aynı
            # taslağı tekrar üretirdi. Gerekçe uyduramayan bir red, doğrulanamayan bir
            # red ile aynı şeydir: karara katılmaz (bkz. `_verify_findings`).
            self.logger.warning(
                f"{self.name}: editör gerekçe belirtmeden reddetti — karar yok sayılıyor"
            )
        return findings

    @staticmethod
    def _as_finding(item: object) -> ReviewFinding | None:
        """Tek bir `reasons` girdisini `ReviewFinding`'e çevirir.

        Şema `{"alinti", "sorun", "duzeltme"}` bekler. Model bunun yerine düz bir string
        döndürürse (eski şema ya da biçim sapması) bulgu alıntısız kalır ve
        `ReviewGuard` tarafından doğrulanamadığı için elenir — sessizce kabul edilmesi,
        doğrulama katmanını baypas etmek anlamına gelirdi."""
        if isinstance(item, dict):
            quote = str(item.get("alinti") or item.get("quote") or "")
            problem = str(item.get("sorun") or item.get("problem") or "")
            fix = str(item.get("duzeltme") or item.get("fix") or "")
            return ReviewFinding(quote=quote, problem=problem, fix=fix) if problem else None
        if isinstance(item, str) and item.strip():
            return ReviewFinding(quote="", problem=item.strip())
        return None
