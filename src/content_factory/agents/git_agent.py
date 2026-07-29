"""GitAgent — Publisher'ın diske yazdığı dosyaları commit/push eder (veya PR açar).

Yalnızca bu agent git/gh bilir (bkz. ARCHITECTURE.md §8). Kendisi hiçbir subprocess
çalıştırmaz: tüm git mekaniği `GitProvider` arayüzünün arkasındadır (varsayılan
implementasyon `integrations.git_ops.LocalGitProvider`); bu agent yalnızca
`publish.yaml`'daki stratejiyi/commit mesajını yorumlar ve sonucu `PublishResult`'a çevirir.

StateStore'a kayıt atmaz — yayın sonrası kalıcılaştırma Orchestrator'ın işidir
(bkz. `orchestrator.PipelineOrchestrator._record_publication`).
"""

from __future__ import annotations

from datetime import datetime

from content_factory.agents.base import BaseAgent
from content_factory.domain.exceptions import AgentValidationError
from content_factory.domain.models import PublisherOutput, PublishResult, PublishStrategy


class GitAgent(BaseAgent[PublisherOutput, PublishResult]):
    name = "git_agent"

    def run(self, input_data: PublisherOutput) -> PublishResult:
        article = input_data.article
        if not article.slug:
            raise AgentValidationError(f"{self.name}: article.slug boş")
        if not input_data.written_paths:
            raise AgentValidationError(
                f"{self.name}: written_paths boş — commit edilecek dosya yok"
            )

        git_config = self.context.settings.publish.git
        strategy = PublishStrategy(git_config.publish_strategy)

        result = self.require_git_provider().commit_and_push(
            repo_path=str(self.context.settings.target_repo_path()),
            files=input_data.written_paths,
            message=self._commit_message(input_data),
            strategy=strategy.value,
            # direct-push'ta hedef dal config'ten gelir; PR modunda dal adını
            # provider üretir (bkz. GitProvider.commit_and_push docstring'i).
            branch=git_config.branch if strategy is PublishStrategy.DIRECT_PUSH else None,
        )

        self.logger.info(
            f"yayınlandı slug={article.slug} strateji={strategy.value} "
            f"dal={result.branch} commit={result.commit_sha} pr={result.pr_url}"
        )
        return PublishResult(
            article_slug=article.slug,
            file_path=article.file_path or input_data.written_paths[0],
            commit_sha=result.commit_sha,
            pr_url=result.pr_url,
            strategy=strategy,
            published_at=datetime.now(),
        )

    def _commit_message(self, output: PublisherOutput) -> str:
        """`publish.yaml: commit_message_template`'i doldurur. Şablon marka ekibi
        tarafından düzenlenebildiği için bilinmeyen bir `{placeholder}` pipeline'ı
        çökertmemeli — böyle bir durumda şablon ham haliyle kullanılır ve loglanır."""
        variables = {
            "slug": output.article.slug or "",
            "linked_articles_count": self._linked_articles_count(output),
            "title": output.article.title,
        }
        template = self.context.settings.publish.git.commit_message_template
        try:
            return template.format(**variables)
        except (KeyError, IndexError) as exc:
            self.logger.warning(
                f"commit_message_template'de bilinmeyen değişken ({exc}); şablon ham kullanılıyor"
            )
            return template

    @staticmethod
    def _linked_articles_count(output: PublisherOutput) -> int:
        """Yeni makalenin kendi dosyası dışında yazılan markdown sayısı — yani
        `related_articles` frontmatter'ı güncellenen eski makaleler."""
        markdown_files = [path for path in output.written_paths if path.endswith(".md")]
        return max(0, len(markdown_files) - 1)
