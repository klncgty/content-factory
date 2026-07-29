"""`GitProvider`'ın somut implementasyonu — `git`/`gh` CLI'lerini subprocess ile çalıştırır.

Yalnızca `GitAgent` bu sınıfı kullanır (bkz. ARCHITECTURE.md §8: Publisher/GitAgent
ayrımı). `gh` CLI kurulu değilse `pr-then-automerge` stratejisi dal'ı push eder ama PR
açmadan döner (`pr_url=None`) — sert bir hata yerine zarif bir düşüş (graceful
degradation): insan dalı elle PR'a çevirebilir.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from content_factory.providers.git import CommitResult, GitProvider
from content_factory.utils.logging import get_logger

_logger = get_logger("integrations.git_ops")


class GitCommandError(RuntimeError):
    """Bir `git`/`gh` komutu sıfır olmayan bir çıkış koduyla başarısız oldu."""

    def __init__(self, command: list[str], returncode: int, stderr: str) -> None:
        super().__init__(
            f"'{' '.join(command)}' başarısız oldu (kod {returncode}): {stderr.strip()}"
        )
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


class LocalGitProvider(GitProvider):
    def __init__(
        self,
        *,
        git_executable: str = "git",
        gh_executable: str = "gh",
        branch_prefix: str = "content/",
    ) -> None:
        self._git = git_executable
        self._gh = gh_executable
        self._branch_prefix = branch_prefix

    def commit_and_push(
        self,
        *,
        repo_path: str,
        files: list[str],
        message: str,
        strategy: str,
        branch: str | None = None,
    ) -> CommitResult:
        if not files:
            raise ValueError("commit_and_push: 'files' boş olamaz")
        repo = Path(repo_path)

        original_branch = self._current_branch(repo)
        target_branch = original_branch

        try:
            if strategy == "pr-then-automerge":
                target_branch = branch or self._default_branch_name()
                self._run(repo, ["checkout", "-b", target_branch])

            self._run(repo, ["add", *files])
            if not self._has_staged_changes(repo):
                _logger.info(f"commit_and_push: değişiklik yok, commit atlanıyor repo={repo}")
                return CommitResult(commit_sha=None, branch=target_branch, pr_url=None)

            self._run(repo, ["commit", "-m", message])
            commit_sha = self._run(repo, ["rev-parse", "HEAD"]).strip()
            self._run(repo, ["push", "--set-upstream", "origin", target_branch])

            pr_url: str | None = None
            if strategy == "pr-then-automerge":
                pr_url = self._create_pull_request(repo, target_branch, message)

            return CommitResult(commit_sha=commit_sha, branch=target_branch, pr_url=pr_url)
        finally:
            if strategy == "pr-then-automerge" and target_branch != original_branch:
                # Çalışma dizinini çağıranın beklediği duruma (orijinal dal) geri döndür.
                self._run(repo, ["checkout", original_branch], check=False)

    # ------------------------------------------------------------------------------ dahili

    def _run(self, repo: Path, args: list[str], *, check: bool = True) -> str:
        command = [self._git, "-C", str(repo), *args]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            raise GitCommandError(command, result.returncode, result.stderr)
        return result.stdout

    def _current_branch(self, repo: Path) -> str:
        return self._run(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def _has_staged_changes(self, repo: Path) -> bool:
        status = self._run(repo, ["diff", "--cached", "--name-only"])
        return bool(status.strip())

    def _default_branch_name(self) -> str:
        return f"{self._branch_prefix}{datetime.now():%Y%m%d%H%M%S}"

    def _create_pull_request(self, repo: Path, branch: str, title: str) -> str | None:
        if shutil.which(self._gh) is None:
            _logger.warning(
                f"gh CLI bulunamadı — dal '{branch}' push edildi ama PR açılmadı "
                "(elle PR açılması gerekir)"
            )
            return None
        command = [
            self._gh,
            "pr",
            "create",
            "--title",
            title,
            "--body",
            "Content Factory tarafından otomatik oluşturuldu.",
            "--head",
            branch,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=repo)
        if result.returncode != 0:
            _logger.warning(f"gh pr create başarısız oldu: {result.stderr.strip()}")
            return None
        return result.stdout.strip() or None
