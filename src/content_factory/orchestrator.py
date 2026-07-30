"""Pipeline yöneticisi — agent sırasını bilir, bağımlılıkları enjekte eder.

Sıra (bkz. ARCHITECTURE.md §1, §13):
TopicScout -> [ScopeGuard.pre_check] -> Research -> Strategist -> Writer -> SEOOptimizer
-> Linker -> ImageGenerator -> Editor -> Publisher -> GitAgent.

İki bilinçli tasarım kararı:

- **Editor, Linker'dan SONRA çalışır** — "onaysız hiçbir içerik yayınlanmaz" garantisi
  (ARCHITECTURE.md §15) makaleye eklenen iç linkleri de kapsamalıdır.
- **Editor reddederse yalnızca taslak döngüsü tekrarlanır** (Writer -> SEO -> Linker),
  görsel yeniden üretilmez: görsel makalenin başlığına/konusuna bağlıdır, metnine değil,
  ve yeniden üretmek her retry'da gereksiz bir üretim maliyeti demektir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from content_factory.agents.base import AgentContext
from content_factory.agents.editor import EditorAgent
from content_factory.agents.git_agent import GitAgent
from content_factory.agents.image_generator import ImageGeneratorAgent
from content_factory.agents.linker import LinkerAgent
from content_factory.agents.publisher import PublisherAgent
from content_factory.agents.research import ResearchAgent
from content_factory.agents.seo_optimizer import SEOOptimizerAgent
from content_factory.agents.strategist import StrategistAgent
from content_factory.agents.topic_scout import TopicScoutAgent, TopicScoutRequest
from content_factory.agents.writer import WriterAgent
from content_factory.domain.exceptions import AgentConfigurationError
from content_factory.domain.models import (
    Article,
    Brief,
    EditorInput,
    InternalLinkRecord,
    LinkPlan,
    PublisherInput,
    QADecision,
    QAReport,
    ResearchNotes,
    RunState,
    RunStatus,
    ScopeDecision,
    ScopeRejectionRecord,
    StrategistInput,
    Topic,
    WriterInput,
)
from content_factory.guards.novelty_guard import NoveltyGuard
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.providers.image import ImageProviderError
from content_factory.utils.logging import get_logger

_BACKLOG_FETCH_LIMIT = 20
"""Backlog'dan bir run'da kaç bekleyen konunun değerlendirileceği. TopicScout tek seferde
en fazla 20 aday üretebildiği (bkz. `TopicScoutRequest.max_candidates`) için bu sınır
pratikte tüm backlog'u kapsar; asıl işlevi patolojik bir birikimde sorguyu sınırlamaktır."""


class PipelineError(RuntimeError):
    """Bir pipeline adımı, run'ı sürdürülemez kılan bir hatayla durdu."""


@dataclass
class PipelineAgents:
    """DI konteyneri — hangi agent implementasyonlarının kullanılacağını belirtir.
    Agent'lar birbirini import etmez; bağımlılıklar yalnızca burada birbirine bağlanır."""

    topic_scout: TopicScoutAgent
    research: ResearchAgent
    strategist: StrategistAgent
    writer: WriterAgent
    seo_optimizer: SEOOptimizerAgent
    linker: LinkerAgent
    image_generator: ImageGeneratorAgent
    editor: EditorAgent
    publisher: PublisherAgent
    git_agent: GitAgent


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        context: AgentContext,
        agents: PipelineAgents,
        scope_guard: ScopeGuard | None = None,
        publish: bool = True,
    ) -> None:
        self.context = context
        self.agents = agents
        self.scope_guard = scope_guard
        self.publish = publish
        """False ise (CLI `--dry-run`) GitAgent ÇALIŞMAZ ve yayın StateStore'a
        kaydedilmez — aksi halde gerçekte push edilmemiş bir makale "yayınlandı"
        olarak kaydedilir ve sonraki run'lar onu var sayardı."""
        self.logger = get_logger("orchestrator")

    def run(self) -> RunState:
        state = RunState(
            run_id=self.context.run_id,
            brand=self.context.brand,
            status=RunStatus.RUNNING,
            started_at=datetime.now(),
        )
        if self.context.state is not None:
            self.context.state.start_run(self.context.run_id, self.context.brand)

        try:
            self._run_pipeline(state)
        except PipelineError as exc:
            # Beklenen/işlenmiş duruşlar (ör. kapsam onaylı aday yok): run FAILED olarak
            # kapanır ama süreç çökmez — zamanlayıcı bir sonraki çalışmayı yapabilir.
            self.logger.error(f"pipeline durdu: {exc}")
            state.status = RunStatus.FAILED
            state.error = str(exc)
        except Exception as exc:
            self.logger.exception("pipeline beklenmeyen bir hatayla durdu")
            state.status = RunStatus.FAILED
            state.error = f"{type(exc).__name__}: {exc}"

        state.finished_at = datetime.now()
        self._finish_state_store(state)
        return state

    # --------------------------------------------------------------------------- adımlar

    def _run_pipeline(self, state: RunState) -> None:
        topic = self._select_topic(state)
        state.topic = topic

        state.step_history.append("research")
        research = self.agents.research(topic)
        state.research = research
        self.logger.info(
            f"research: {len(research.key_facts)} bulgu, "
            f"{len(research.sources_used)} kaynak, açı={research.suggested_angle[:60]!r}"
        )

        state.step_history.append("strategist")
        brief = self.agents.strategist(StrategistInput(topic=topic, research=research))
        state.brief = brief
        self.logger.info(
            f"strategist: başlık={brief.title!r} hedef_kelime={brief.target_keyword!r} "
            f"{len(brief.outline)} bölüm, hedef ~{brief.target_word_count} kelime"
        )

        # Görsel bir kez üretilir ve retry döngüsü boyunca yeniden kullanılır.
        article, link_plan = self._draft_cycle(state, brief, research, feedback=None)
        article = self._generate_image(state, article)

        qa_report = self._review_with_retries(state, brief, research, article, link_plan)
        state.qa_report = qa_report
        article = state.article or article
        link_plan = state.link_plan

        if qa_report.decision is not QADecision.APPROVED:
            self.logger.warning(
                f"editor onaylamadı ({qa_report.retry_count} deneme sonunda) — "
                f"insan incelemesine alınıyor: {qa_report.reasons}"
            )
            state.status = RunStatus.NEEDS_REVIEW
            return

        state.step_history.append("publisher")
        publisher_output = self.agents.publisher(
            PublisherInput(article=article, link_plan=link_plan)
        )
        state.article = publisher_output.article
        target_root = self.context.settings.target_repo_path()
        self.logger.info(f"publisher: {len(publisher_output.written_paths)} dosya yazıldı")
        for written in publisher_output.written_paths:
            self.logger.info(f"  -> {target_root}/{written}")

        if not self.publish:
            self.logger.warning(
                "dry-run: dosyalar yazıldı ama commit/push yapılmadı ve yayın "
                "StateStore'a kaydedilmedi"
            )
            state.status = RunStatus.COMPLETED
            return

        state.step_history.append("git_agent")
        state.publish_result = self.agents.git_agent(publisher_output)

        self._record_publication(publisher_output.article, link_plan)
        state.status = RunStatus.COMPLETED

    def _select_topic(self, state: RunState) -> Topic:
        """Önce `topics_backlog`'a bakılır; orada kullanılabilir bir konu varsa TopicScout
        HİÇ ÇAĞRILMAZ (bir LLM çağrısı tasarrufu). Backlog boş/bayatsa yeni adaylar
        üretilir ve seçilmeyenler bir sonraki run için backlog'a yazılır."""
        from_backlog = self._take_from_backlog(state)
        if from_backlog is not None:
            return from_backlog
        return self._scout_new_topic(state)

    def _take_from_backlog(self, state: RunState) -> Topic | None:
        """Backlog'daki en uygun bekleyen konuyu döndürür, yoksa `None`.

        Backlog kayıtları bayatlayabilir: bir konu kaydedildikten sonra ona benzer bir
        makale yayınlanmış ya da `scope.yaml` daralmış olabilir. Bu yüzden bekleyen
        konular kullanılmadan önce aynı deterministik süzgeçlerden (scope + novelty)
        yeniden geçirilir; elenenler `stale` olarak işaretlenir ki her run'da tekrar
        değerlendirilmesinler."""
        store = self.context.state
        if store is None:
            return None

        pending = store.get_pending_topics(self.context.brand, limit=_BACKLOG_FETCH_LIMIT)
        if not pending:
            return None

        usable: list[Topic] = []
        for topic in pending:
            reason = self._backlog_reject_reason(topic)
            if reason is None:
                usable.append(topic)
                continue
            self.logger.info(f"backlog: {topic.title!r} bayatladı ({reason}) — stale")
            if topic.id is not None:
                store.mark_topic_status(topic.id, "stale")

        if not usable:
            # Hepsi bayatsa TopicScout'a düşülür — bayat bir konuyu zorla kullanmaktansa
            # yeni aday üretmek doğru davranış.
            self.logger.info("backlog: kullanılabilir konu kalmadı, TopicScout çağrılacak")
            return None

        state.step_history.append("topic_backlog")
        selected = self._pick_topic(usable)
        if selected.id is not None:
            store.mark_topic_status(selected.id, "used")
        self.logger.info(
            f"backlog: {len(usable)} bekleyen konudan seçildi — {selected.title!r} "
            f"(grup={selected.category}, skor={selected.score}); TopicScout atlandı"
        )
        return selected

    def _backlog_reject_reason(self, topic: Topic) -> str | None:
        """Bekleyen bir konunun artık kullanılamamasının gerekçesi, kullanılabilirse `None`.
        Her iki kontrol de deterministiktir ve LLM çağırmaz."""
        if self.scope_guard is not None:
            result = self.scope_guard.pre_check(
                title=topic.title, seed_keywords=topic.seed_keywords
            )
            if result.decision is not ScopeDecision.IN_SCOPE:
                return "kapsam dışı kaldı"

        guard = self._novelty_guard()
        if guard is not None:
            novelty = guard.check(title=topic.title, seed_keywords=topic.seed_keywords)
            if novelty.is_duplicate:
                return novelty.reason
        return None

    def _scout_new_topic(self, state: RunState) -> Topic:
        """TopicScout adayları üretir, `ScopeGuard.pre_check` deterministik olarak eler,
        en yüksek skorlu onaylı aday seçilir (TopicScout adayları skora göre sıralı döndürür).
        Seçilmeyen uygun adaylar backlog'a yazılır."""
        state.step_history.append("topic_scout")
        candidates = self.agents.topic_scout(TopicScoutRequest())
        self.logger.info(
            f"topic_scout: {len(candidates)} aday konu -> "
            f"{[candidate.title for candidate in candidates]}"
        )

        if self.scope_guard is None:
            approved = candidates
        else:
            approved = []
            for candidate in candidates:
                result = self.scope_guard.pre_check(
                    title=candidate.title, seed_keywords=candidate.seed_keywords
                )
                if result.decision is ScopeDecision.IN_SCOPE:
                    # pre_check hangi gruba düştüğünü de söyler; kategori burada kesinleşir.
                    approved.append(candidate.model_copy(update={"category": result.matched_group}))
                else:
                    self._log_scope_rejection(candidate, result.reason)

        if not approved:
            raise PipelineError("topic_scout: kapsam onaylı aday konu üretilemedi")

        fresh = self._drop_repeated_topics(approved)
        selected = self._pick_topic(fresh)
        self.logger.info(
            f"scope_guard: {len(approved)}/{len(candidates)} aday kapsamda, "
            f"{len(fresh)} tanesi yeni konu — "
            f"seçilen: {selected.title!r} (grup={selected.category}, skor={selected.score})"
        )
        self._backlog_unselected(fresh, selected=selected)
        return selected

    def _backlog_unselected(self, fresh: list[Topic], *, selected: Topic) -> None:
        """Bu run'da kullanılmayan uygun adayları bir sonraki run için saklar.

        Yalnızca `fresh` (kapsam onaylı + tekrar olmayan) adaylar yazılır — kapsam dışı
        veya zaten yazılmış bir konuyu saklamanın faydası yok, sonraki run'da nasılsa
        elenirdi. Backlog yalnızca TopicScout'un çalıştığı run'larda büyür; dolu olduğu
        sürece TopicScout hiç çağrılmadığı için sınırsız birikme olmaz."""
        store = self.context.state
        if store is None:
            return

        leftovers = [topic for topic in fresh if topic.title != selected.title]
        if not leftovers:
            return

        store.add_topic_candidates(leftovers)
        self.logger.info(
            f"backlog: {len(leftovers)} kullanılmayan aday sonraki run için kaydedildi -> "
            f"{[topic.title for topic in leftovers]}"
        )

    def _novelty_guard(self) -> NoveltyGuard | None:
        """Yayınlanmış makalelere karşı kurulmuş guard; StateStore yoksa veya hiç yayın
        yapılmamışsa `None` (karşılaştırılacak bir şey yok)."""
        store = self.context.state
        if store is None:
            return None
        published = store.get_recent_articles(self.context.brand, limit=100)
        return NoveltyGuard(published) if published else None

    def _drop_repeated_topics(self, approved: list[Topic]) -> list[Topic]:
        """Yayınlanmış makalelerle aynı konuyu tekrar eden adayları eler (bkz.
        `guards/novelty_guard.py`). Hepsi elenirse liste olduğu gibi döner: konu
        tekrarı yayını tamamen durduracak kadar ciddi bir hata değil, tercih meselesidir."""
        guard = self._novelty_guard()
        if guard is None:
            return approved

        fresh: list[Topic] = []
        for candidate in approved:
            result = guard.check(title=candidate.title, seed_keywords=candidate.seed_keywords)
            if result.is_duplicate:
                self.logger.info(f"novelty: {candidate.title!r} elendi — {result.reason}")
            else:
                fresh.append(candidate)

        if not fresh:
            self.logger.warning(
                "novelty: tüm adaylar yayınlanmış konuların tekrarı — en yüksek skorlu "
                "aday yine de kullanılıyor, konu havuzu genişletilmeli (seo.yaml)"
            )
            return approved
        return fresh

    def _pick_topic(self, candidates: list[Topic]) -> Topic:
        """Aday listesi skora göre sıralıdır; eşit koşulda EN SON YAYINLANANDAN FARKLI bir
        kategoriye öncelik verilir. Aksi halde blog tek bir gruba (ör. hep zeytinyağı)
        kayıyor ve markanın diğer ürün ekseni (ahşap ürünler) hiç yazılmıyor."""
        state = self.context.state
        if state is not None:
            recent = state.get_recent_articles(self.context.brand, limit=1)
            if recent:
                last_category = recent[0].category
                rotated = [c for c in candidates if c.category != last_category]
                if rotated:
                    self.logger.info(
                        f"kategori rotasyonu: son yayın {last_category!r} olduğu için "
                        f"farklı gruptan aday seçiliyor"
                    )
                    return rotated[0]
        return candidates[0]

    def _draft_cycle(
        self,
        state: RunState,
        brief: Brief,
        research: ResearchNotes,
        *,
        feedback: str | None,
        previous_draft: str | None = None,
    ) -> tuple[Article, LinkPlan]:
        """Writer -> SEOOptimizer -> Linker. Editor reddettiğinde tekrarlanan tek bölüm
        budur: metin değişince slug/meta ve iç linkler de yeniden hesaplanmalıdır."""
        state.step_history.append("writer")
        article = self.agents.writer(
            WriterInput(
                brief=brief,
                research=research,
                feedback=feedback,
                previous_draft=previous_draft,
            )
        )
        self.logger.info(f"writer: {len(article.body_markdown.split())} kelime yazıldı")

        state.step_history.append("seo_optimizer")
        article = self.agents.seo_optimizer(article)
        if article.seo is not None:
            self.logger.info(
                f"seo_optimizer: slug={article.seo.slug!r} "
                f"meta_title={article.seo.meta_title!r} "
                f"({len(article.secondary_keywords)} ikincil kelime)"
            )

        state.step_history.append("linker")
        linker_output = self.agents.linker(article)
        self.logger.info(
            f"linker: {len(linker_output.link_plan.new_article_body_links)} gövde linki, "
            f"{len(linker_output.link_plan.related_articles_updates)} eski makale güncellenecek"
        )

        state.article = linker_output.article
        state.link_plan = linker_output.link_plan
        return linker_output.article, linker_output.link_plan

    def _generate_image(self, state: RunState, article: Article) -> Article:
        """Görsel üretimi opsiyoneldir: makale görselsiz de yayınlanabilir — Publisher
        bu durumu zaten destekler. Görsel bir zenginleştirmedir, yayın için bir önkoşul
        değil. Bu yüzden iki hata sınıfı da yutulur:

        - `AgentConfigurationError`: hiç `ImageProvider` yapılandırılmamış (ör. `--dry-run`
          öncesi kurulum, API anahtarı yok).
        - `ImageProviderError`: sağlayıcı çağrısı başarısız (ağ, kota, geçersiz model).
          Görsel API'sinin geçici bir arızası, onaylanmış bir makalenin yayınlanmasını
          engellememelidir."""
        state.step_history.append("image_generator")
        try:
            article = self.agents.image_generator(article)
        except (AgentConfigurationError, ImageProviderError) as exc:
            self.logger.warning(f"görsel üretilemedi, görselsiz devam ediliyor: {exc}")
        state.article = article
        return article

    def _review_with_retries(
        self,
        state: RunState,
        brief: Brief,
        research: ResearchNotes,
        article: Article,
        link_plan: LinkPlan,
    ) -> QAReport:
        """Editor gate'i + `engine.yaml: retries.editor_reject_max_retries` kadar yeniden
        yazdırma. Her denemede Editor'ün gerekçeleri Writer'a `feedback` olarak geri verilir."""
        max_retries = self.context.settings.engine.retries.editor_reject_max_retries

        for attempt in range(max_retries + 1):
            state.step_history.append("editor")
            report = self.agents.editor(
                EditorInput(
                    article=article, link_plan=link_plan, research=research, retry_count=attempt
                )
            )
            self.logger.info(
                f"editor: karar={report.decision.value} kapsam={report.scope_decision.value} "
                f"(deneme {attempt + 1}/{max_retries + 1})"
                + (f" gerekçeler={report.reasons}" if report.reasons else "")
            )
            if report.decision is QADecision.APPROVED or attempt == max_retries:
                return report

            self.logger.info(
                f"editor reddetti (deneme {attempt + 1}/{max_retries + 1}), "
                f"yeniden yazdırılıyor: {report.reasons}"
            )
            image = article.image
            article, link_plan = self._draft_cycle(
                state,
                brief,
                research,
                feedback="\n".join(f"- {r}" for r in report.reasons),
                # Reddedilen taslağın kendisi de verilir: Writer sıfırdan yazmak yerine
                # yalnızca gerekçelerde yazan yerlere dokunur (bkz. WriterInput.previous_draft).
                previous_draft=article.body_markdown,
            )
            # Görsel başlığa bağlıdır, metne değil — yeniden üretmek yerine taşınır.
            article = article.model_copy(update={"image": image})
            state.article = article

        raise AssertionError("ulaşılamaz: döngü her durumda bir QAReport döndürür")

    # ------------------------------------------------------------------- kalıcılaştırma

    def _record_publication(self, article: Article, link_plan: LinkPlan | None) -> None:
        """Yayın BAŞARIYLA tamamlandıktan sonra kalıcı kayıtlar — daha önce değil:
        reddedilebilecek/yayınlanamayacak bir makale StateStore'u kirletmemeli
        (bkz. `agents/linker.py` docstring'i)."""
        state_store = self.context.state
        if state_store is None or not article.slug:
            return

        state_store.record_article(article)
        for keyword in filter(None, [article.target_keyword, *article.secondary_keywords]):
            state_store.record_keyword_usage(self.context.brand, keyword, article.slug)

        if link_plan is None:
            return
        for link in link_plan.new_article_body_links:
            state_store.record_internal_link(
                InternalLinkRecord(
                    brand=self.context.brand,
                    source_slug=article.slug,
                    target_slug=link.target_slug,
                    link_type="body_link",
                    created_run_id=self.context.run_id,
                )
            )
        for update in link_plan.related_articles_updates:
            state_store.record_internal_link(
                InternalLinkRecord(
                    brand=self.context.brand,
                    source_slug=update.target_slug,
                    target_slug=update.add_related,
                    link_type="related_section",
                    created_run_id=self.context.run_id,
                )
            )

    def _log_scope_rejection(self, topic: Topic, reason: str) -> None:
        self.logger.info(f"scope_guard.rejected topic={topic.title!r} reason={reason}")
        if self.context.state is None:
            return
        self.context.state.log_scope_rejection(
            ScopeRejectionRecord(
                brand=self.context.brand,
                run_id=self.context.run_id,
                stage="topic_scout",
                reason=reason,
                payload_snippet=topic.title,
            )
        )

    def _finish_state_store(self, state: RunState) -> None:
        if self.context.state is not None:
            self.context.state.finish_run(state.run_id, state.status.value, state.error)
