"""`GitProvider`'ın somut implementasyonu — `git` CLI'ını subprocess ile çalıştırır.

Yalnızca `GitAgent` bu sınıfı kullanır (bkz. ARCHITECTURE.md §8: Publisher/GitAgent
ayrımı).

**Kimlik doğrulama.** `GIT_TOKEN` tanımlıysa push, token gömülü bir remote URL ile
yapılır ve PR doğrudan GitHub REST API'sine açılır. Bunun sebebi taşınabilirlik: aksi
halde yayın adımı makinedeki interaktif `git`/`gh` oturumuna bağlı kalır ve sunucuda /
CI'da (oturum yokken) sessizce çalışmaz. Token yoksa eski davranışa düşülür — mevcut
git kimliğiyle push, PR için `gh` CLI; `gh` de yoksa dal push edilir ama PR açılmaz
(`pr_url=None`), yani sert hata yerine zarif bir düşüş olur.

Token asla loglanmaz ve `.git/config`'e yazılmaz: yalnızca tek bir `git push` çağrısına
argüman olarak verilir, hata mesajlarında da maskelenir.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import httpx

from content_factory.providers.git import CommitResult, GitProvider
from content_factory.utils.logging import get_logger

_logger = get_logger("integrations.git_ops")

GITHUB_API_BASE_URL = "https://api.github.com"
_TOKEN_ENV = "GIT_TOKEN"
_MASK = "***"
_GITHUB_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"
)


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
        token: str | None = None,
        api_base_url: str = GITHUB_API_BASE_URL,
        client: httpx.Client | None = None,
        automerge: bool = True,
    ) -> None:
        self._git = git_executable
        self._gh = gh_executable
        self._branch_prefix = branch_prefix
        self._token = (token if token is not None else os.environ.get(_TOKEN_ENV, "")).strip()
        self._api_base_url = api_base_url
        self._client = client
        self._automerge = automerge
        """`pr-then-automerge` stratejisinde PR'ın açıldıktan sonra otomatik merge edilip
        edilmeyeceği. `False` yapmak PR'ı insan onayına bırakır (`gh` yolunda merge zaten
        yapılmaz — o yol yalnızca token yokken kullanılır)."""

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
            self._push(repo, target_branch)

            pr_url: str | None = None
            if strategy == "pr-then-automerge":
                pr_url = self._create_pull_request(repo, target_branch, message)

            return CommitResult(commit_sha=commit_sha, branch=target_branch, pr_url=pr_url)
        finally:
            if strategy == "pr-then-automerge" and target_branch != original_branch:
                # Çalışma dizinini çağıranın beklediği duruma (orijinal dal) geri döndür.
                self._run(repo, ["checkout", original_branch], check=False)

    # ------------------------------------------------------------------------------ push

    def _push(self, repo: Path, branch: str) -> None:
        if not self._token:
            self._run(repo, ["push", "--set-upstream", "origin", branch])
            return
        # Token'lı URL yalnızca bu çağrıya argüman olarak verilir; `--set-upstream`
        # kullanılmaz, aksi halde token `.git/config`'e upstream URL'i olarak yazılırdı.
        url = self._authenticated_remote_url(repo)
        self._run(repo, ["push", url, f"HEAD:refs/heads/{branch}"], secret=self._token)

    def _authenticated_remote_url(self, repo: Path) -> str:
        owner, name = self._remote_slug(repo)
        return f"https://x-access-token:{self._token}@github.com/{owner}/{name}.git"

    def _remote_slug(self, repo: Path) -> tuple[str, str]:
        remote = self._run(repo, ["remote", "get-url", "origin"]).strip()
        match = _GITHUB_REMOTE.match(remote)
        if match is None:
            raise GitCommandError(
                [self._git, "remote", "get-url", "origin"],
                0,
                f"'origin' bir GitHub remote'u değil: {remote!r} — GIT_TOKEN ile push "
                f"yalnızca GitHub remote'larında desteklenir",
            )
        return match.group("owner"), match.group("repo")

    # -------------------------------------------------------------------------------- PR

    def _create_pull_request(self, repo: Path, branch: str, title: str) -> str | None:
        if not self._token:
            return self._create_pull_request_via_gh(repo, branch, title)

        pull_request = self._create_pull_request_via_api(repo, branch, title)
        if pull_request is None:
            return None
        if self._automerge:
            self._merge_pull_request(repo, pull_request)
        return pull_request.get("html_url")

    def _merge_pull_request(self, repo: Path, pull_request: dict) -> None:
        """PR'ı API üzerinden merge eder (`pr-then-automerge` stratejisinin "automerge"
        yarısı — daha önce yazılmamıştı, PR insan onayı bekliyordu).

        Merge başarısız olursa (dal koruması, çakışma, gerekli kontroller) hata
        FIRLATILMAZ: PR açık kalır ve insan devralır. Yayın zinciri buraya kadar
        başarılıdır, makale push edilmiştir."""
        number = pull_request.get("number")
        if number is None:
            _logger.warning("PR numarası yanıtta yok — otomatik merge atlandı")
            return
        owner, name = self._remote_slug(repo)
        client = self._client or httpx.Client(base_url=self._api_base_url, timeout=30)
        try:
            response = client.put(
                f"/repos/{owner}/{name}/pulls/{number}/merge",
                headers=self._api_headers(),
                json={"merge_method": "squash"},
            )
        except httpx.HTTPError as exc:
            _logger.warning(f"PR #{number} otomatik merge edilemedi (ağ hatası): {exc}")
            return
        finally:
            if self._client is None:
                client.close()

        if response.status_code >= 400:
            _logger.warning(
                f"PR #{number} otomatik merge edilemedi ({response.status_code}): "
                f"{_mask(response.text[:300], self._token)} — PR açık bırakıldı"
            )
            return
        _logger.info(f"PR #{number} otomatik merge edildi")

    def _api_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }

    def _create_pull_request_via_api(self, repo: Path, branch: str, title: str) -> dict | None:
        owner, name = self._remote_slug(repo)
        base = self._base_branch(repo)
        client = self._client or httpx.Client(base_url=self._api_base_url, timeout=30)
        try:
            response = client.post(
                f"/repos/{owner}/{name}/pulls",
                headers=self._api_headers(),
                json={
                    "title": title,
                    "head": branch,
                    "base": base,
                    "body": "Content Factory tarafından otomatik oluşturuldu.",
                },
            )
        except httpx.HTTPError as exc:
            # PR açılamaması yayını geçersiz kılmaz: içerik push edildi, insan elle
            # PR'a çevirebilir. Bu yüzden hata değil uyarı.
            _logger.warning(f"PR açılamadı (ağ hatası): {exc}")
            return None
        finally:
            if self._client is None:
                client.close()

        if response.status_code >= 400:
            _logger.warning(
                f"PR açılamadı ({response.status_code}): {_mask(response.text[:300], self._token)}"
            )
            return None
        return response.json()

    def _create_pull_request_via_gh(self, repo: Path, branch: str, title: str) -> str | None:
        if shutil.which(self._gh) is None:
            _logger.warning(
                f"gh CLI bulunamadı ve {_TOKEN_ENV} tanımlı değil — dal '{branch}' push "
                "edildi ama PR açılmadı (elle PR açılması gerekir)"
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

    # ------------------------------------------------------------------------------ dahili

    def _run(
        self, repo: Path, args: list[str], *, check: bool = True, secret: str | None = None
    ) -> str:
        command = [self._git, "-C", str(repo), *args]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            raise GitCommandError(
                [_mask(part, secret) for part in command],
                result.returncode,
                _mask(result.stderr, secret),
            )
        return result.stdout

    def _current_branch(self, repo: Path) -> str:
        return self._run(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    def _base_branch(self, repo: Path) -> str:
        """PR'ın hedef dalı: remote'un varsayılan dalı, okunamazsa `main`."""
        head = self._run(
            repo, ["symbolic-ref", "refs/remotes/origin/HEAD"], check=False
        ).strip()
        return head.rsplit("/", 1)[-1] if head else "main"

    def _has_staged_changes(self, repo: Path) -> bool:
        status = self._run(repo, ["diff", "--cached", "--name-only"])
        return bool(status.strip())

    def _default_branch_name(self) -> str:
        return f"{self._branch_prefix}{datetime.now():%Y%m%d%H%M%S}"


def _mask(text: str, secret: str | None) -> str:
    """Token'ın log/hata metinlerine sızmasını engeller."""
    return text.replace(secret, _MASK) if secret else text
