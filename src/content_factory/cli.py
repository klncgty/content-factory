"""Content Factory CLI — bir marka için pipeline'ı çalıştırır.

Kullanım:
    content-factory --brand oleart
    content-factory --brand oleart --dry-run     # dosya yazar, git'e dokunmaz
    content-factory --brand oleart --dry-run --target-repo /tmp/deneme   # izole deneme
    python scripts/run_pipeline.py --brand oleart

Bu modülün tek sorumluluğu **kablolamadır**: config'i yükler, provider'ları kurar,
`AgentContext`'i doldurur ve Orchestrator'ı çalıştırır. Hiçbir iş mantığı içermez.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from content_factory.agents.base import AgentContext
from content_factory.agents.editor import EditorAgent
from content_factory.agents.git_agent import GitAgent
from content_factory.agents.image_generator import ImageGeneratorAgent
from content_factory.agents.linker import LinkerAgent
from content_factory.agents.publisher import PublisherAgent
from content_factory.agents.research import ResearchAgent
from content_factory.agents.seo_optimizer import SEOOptimizerAgent
from content_factory.agents.strategist import StrategistAgent
from content_factory.agents.topic_scout import TopicScoutAgent
from content_factory.agents.writer import WriterAgent
from content_factory.domain.models import RunStatus
from content_factory.guards.scope_guard import ScopeGuard
from content_factory.integrations.git_ops import LocalGitProvider
from content_factory.integrations.image_client import create_image_provider
from content_factory.knowledge.loader import KnowledgeLoader
from content_factory.orchestrator import PipelineAgents, PipelineOrchestrator
from content_factory.prompts.loader import PromptLoader
from content_factory.providers.llm.factory import create_agent_scoped_llm_provider
from content_factory.settings.loader import Settings
from content_factory.state.sqlite_store import SQLiteStateStore
from content_factory.utils.logging import configure_logging, get_logger
from content_factory.utils.paths import project_root


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="content-factory")
    parser.add_argument("--brand", required=True, help="brands/ altındaki marka adı (ör. oleart)")
    parser.add_argument("--run-id", default=None, help="Belirtilmezse otomatik üretilir")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hedef repoya dosyaları yazar ama commit/push YAPMAZ (git provider bağlanmaz)",
    )
    parser.add_argument(
        "--target-repo",
        default=None,
        help=(
            "publish.yaml: target_repo_path'i geçersiz kılar. Gerçek marka reposuna "
            "dokunmadan çıktıyı görmek için --dry-run ile birlikte kullanılır."
        ),
    )
    return parser


def _new_run_id() -> str:
    return f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    run_id = args.run_id or _new_run_id()

    # API anahtarları proje kökündeki .env dosyasından okunur; zaten tanımlı
    # bir çevre değişkeni ezilmez. Bu, current working dir'e bağlı aramayı önler.
    load_dotenv(project_root() / ".env", override=False)

    settings = Settings.load(args.brand)
    if args.target_repo:
        settings = dataclasses.replace(
            settings,
            publish=settings.publish.model_copy(update={"target_repo_path": args.target_repo}),
        )

    log_dir = settings.resolve(settings.engine.run_artifacts.path_template, run_id=run_id)
    configure_logging(brand=args.brand, run_id=run_id, log_dir=log_dir)
    logger = get_logger("cli")
    logger.info(f"pipeline başlıyor brand={args.brand} run_id={run_id}")
    override_note = " (--target-repo ile override edildi)" if args.target_repo else ""
    logger.info(f"hedef repo: {settings.target_repo_path()}{override_note}")
    if args.dry_run:
        logger.info("dry-run: commit/push yapılmayacak, yayın StateStore'a kaydedilmeyecek")

    db_path = settings.resolve(settings.engine.state_store.path_template)
    state_store = SQLiteStateStore(db_path)
    state_store.init_schema()

    knowledge_loader = KnowledgeLoader(settings.root)
    report = knowledge_loader.validate(args.brand)
    if not report.is_valid:
        logger.warning(f"knowledge base eksik/boş dosyalar içeriyor: {report.issues}")
    elif report.has_placeholders:
        logger.info("knowledge base henüz placeholder içeriyor (Faz 0 tamamlanmadı)")
    knowledge = knowledge_loader.load(args.brand)

    # Tüm agent'lar için agent bazlı sağlayıcı seçimi destekler. `brands/{brand}/models.yaml`
    # içindeki `provider:` override'ları artık tek bir wrapper üzerinden çalışır.
    llm_provider = create_agent_scoped_llm_provider(settings)

    # Görsel sağlayıcı da aynı ilkeyle kurulur: hangi sağlayıcı/model kullanılacağı
    # config/models.yaml: agents.image_generator'dan gelir. Temel görsel run dizinine
    # yazılır; türevleri (cover/thumbnail/og) ImageGeneratorAgent üretir.
    image_provider = create_image_provider(settings, output_dir=log_dir / "images" / "_base")

    context = AgentContext(
        brand=args.brand,
        run_id=run_id,
        settings=settings,
        knowledge=knowledge,
        prompts=PromptLoader(settings.root),
        llm=llm_provider,
        # `--dry-run`'da git provider hiç bağlanmaz; Orchestrator zaten GitAgent'ı
        # çağırmaz, provider'ın burada None kalması bunu ayrıca garanti eder.
        git=None if args.dry_run else LocalGitProvider(),
        image=image_provider,
        state=state_store,
    )

    agents = PipelineAgents(
        topic_scout=TopicScoutAgent(context),
        research=ResearchAgent(context),
        strategist=StrategistAgent(context),
        writer=WriterAgent(context),
        seo_optimizer=SEOOptimizerAgent(context),
        linker=LinkerAgent(context),
        image_generator=ImageGeneratorAgent(context),
        editor=EditorAgent(context),
        publisher=PublisherAgent(context),
        git_agent=GitAgent(context),
    )
    scope_guard = ScopeGuard(settings.scope)

    orchestrator = PipelineOrchestrator(
        context=context, agents=agents, scope_guard=scope_guard, publish=not args.dry_run
    )
    result = orchestrator.run()

    logger.info(f"pipeline bitti status={result.status.value} adımlar={result.step_history}")
    _log_summary(logger, result, settings=settings, log_dir=log_dir)
    if result.error:
        logger.error(f"hata: {result.error}")
    llm_provider.close()
    image_provider.close()
    state_store.close()

    return 0 if result.status == RunStatus.COMPLETED else 1


def _log_summary(logger: logging.Logger, result, settings: Settings, log_dir: Path) -> None:
    logger.info(f"run log: {log_dir / 'run.log'}")
    if result.status != RunStatus.COMPLETED:
        logger.warning(
            "pipeline doğru tamamlanmadı; durum=%s. Logu kontrol edin veya yeniden çalıştırın.",
            result.status.value,
        )


if __name__ == "__main__":
    sys.exit(main())