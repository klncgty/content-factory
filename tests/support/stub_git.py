from __future__ import annotations

from content_factory.providers.git import CommitResult, GitProvider


class StubGitProvider(GitProvider):
    """GitAgent'ın iş mantığı testleri için sahte git sağlayıcısı.

    Gerçek git mekaniği `tests/integrations/test_git_ops.py`'de gerçek repo'larla test
    edilir; burada test edilen şey GitAgent'ın `publish.yaml`'ı doğru yorumlayıp
    provider'ı doğru argümanlarla çağırması. Yapılan çağrılar `self.calls`'ta birikir.
    """

    def __init__(self, *, result: CommitResult | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._result = result or CommitResult(
            commit_sha="abc1234", branch="content/20260730120000", pr_url="https://pr/1"
        )

    def commit_and_push(
        self,
        *,
        repo_path: str,
        files: list[str],
        message: str,
        strategy: str,
        branch: str | None = None,
    ) -> CommitResult:
        self.calls.append(
            {
                "repo_path": repo_path,
                "files": files,
                "message": message,
                "strategy": strategy,
                "branch": branch,
            }
        )
        return self._result
