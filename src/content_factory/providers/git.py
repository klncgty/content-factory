"""Git sağlayıcı arayüzü — yalnızca GitAgent bu arayüzü kullanır.

PublisherAgent'ın hiçbir git bilgisine sahip olmaması bilinçli bir ayrımdır
(bkz. ARCHITECTURE.md §8). Somut implementasyon:
`content_factory.integrations.git_ops.LocalGitProvider` (subprocess ile `git`/`gh` CLI)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class CommitResult(BaseModel):
    commit_sha: str | None = None
    pr_url: str | None = None
    branch: str


class GitProvider(ABC):
    @abstractmethod
    def commit_and_push(
        self,
        *,
        repo_path: str,
        files: list[str],
        message: str,
        strategy: str,
        branch: str | None = None,
    ) -> CommitResult:
        """`strategy`: "direct-push" | "pr-then-automerge" (bkz. brands/{brand}/publish.yaml).
        `branch`, yalnızca "pr-then-automerge" için kullanılır; verilmezse implementasyon
        kendi (ör. zaman damgalı) bir dal adı üretir."""
        raise NotImplementedError
