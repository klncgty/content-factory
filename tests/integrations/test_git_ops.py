from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest

from content_factory.integrations.git_ops import GitCommandError, LocalGitProvider


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    return bare


@pytest.fixture
def work_repo(tmp_path: Path, bare_remote: Path) -> Path:
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test User")
    _git(work, "remote", "add", "origin", str(bare_remote))

    (work / "README.md").write_text("baslangic\n", encoding="utf-8")
    _git(work, "add", "README.md")
    _git(work, "commit", "-m", "ilk commit")
    _git(work, "push", "-u", "origin", "main")
    return work


@pytest.fixture
def provider() -> LocalGitProvider:
    # token="" -> çalıştıran ortamda GIT_TOKEN tanımlı olsa bile testler yerel bare
    # remote üzerinde deterministik kalsın (token'lı yol GitHub remote'u gerektirir).
    return LocalGitProvider(token="")


def test_direct_push_commits_and_pushes(provider: LocalGitProvider, work_repo: Path) -> None:
    (work_repo / "content.md").write_text("# Yeni makale\n", encoding="utf-8")

    result = provider.commit_and_push(
        repo_path=str(work_repo),
        files=["content.md"],
        message="blog: yeni makale eklendi",
        strategy="direct-push",
    )

    assert result.branch == "main"
    assert result.commit_sha is not None
    assert result.pr_url is None

    log = _git(work_repo, "log", "-1", "--pretty=%s")
    assert "blog: yeni makale eklendi" in log

    # Uzak depoda (origin) da commit görünmeli.
    remote_log = _git(work_repo, "log", "origin/main", "-1", "--pretty=%H")
    assert remote_log.strip() == result.commit_sha


def test_direct_push_with_no_changes_returns_none_commit_sha(
    provider: LocalGitProvider, work_repo: Path
) -> None:
    # README.md zaten commit'lenmiş durumda, değişiklik olmadan tekrar eklenmeye çalışılıyor.
    result = provider.commit_and_push(
        repo_path=str(work_repo),
        files=["README.md"],
        message="değişiklik yok",
        strategy="direct-push",
    )
    assert result.commit_sha is None


def test_pr_then_automerge_creates_branch_and_leaves_main_untouched(
    provider: LocalGitProvider, work_repo: Path
) -> None:
    (work_repo / "content.md").write_text("# PR ile eklenen makale\n", encoding="utf-8")

    result = provider.commit_and_push(
        repo_path=str(work_repo),
        files=["content.md"],
        message="blog: PR ile makale",
        strategy="pr-then-automerge",
        branch="content/test-branch",
    )

    assert result.branch == "content/test-branch"
    assert result.commit_sha is not None
    # gh CLI test ortamında kimlik doğrulanmamış/yok olabilir — PR açılamamışsa None döner,
    # bu bir hata değil, zarif bir düşüştür.

    # Çalışma dizini orijinal dala (main) geri dönmüş olmalı.
    assert provider._current_branch(work_repo) == "main"  # noqa: SLF001

    # Ama içerik dalı uzak depoda gerçekten var ve commit içeriyor.
    branches = _git(work_repo, "branch", "-r")
    assert "origin/content/test-branch" in branches


def test_pr_then_automerge_generates_branch_name_when_not_given(
    provider: LocalGitProvider, work_repo: Path
) -> None:
    (work_repo / "content2.md").write_text("# İkinci makale\n", encoding="utf-8")

    result = provider.commit_and_push(
        repo_path=str(work_repo),
        files=["content2.md"],
        message="blog: ikinci makale",
        strategy="pr-then-automerge",
    )
    assert result.branch.startswith("content/")


def test_commit_and_push_rejects_empty_files_list(
    provider: LocalGitProvider, work_repo: Path
) -> None:
    with pytest.raises(ValueError):
        provider.commit_and_push(
            repo_path=str(work_repo), files=[], message="x", strategy="direct-push"
        )


# ------------------------------------------------------------------- GIT_TOKEN ile push


class _RecordingProvider(LocalGitProvider):
    """`git` çağrılarını gerçekten çalıştırmadan kaydeder — token'lı push'un komut
    kurulumu ağ erişimi olmadan doğrulanabilsin."""

    def __init__(self, remote: str = "https://github.com/klncgty/oleart.git", **kwargs: object):
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.commands: list[tuple[list[str], str | None]] = []
        self._remote = remote

    def _run(  # type: ignore[override]
        self, repo: Path, args: list[str], *, check: bool = True, secret: str | None = None
    ) -> str:
        self.commands.append((args, secret))
        if args[:2] == ["remote", "get-url"]:
            return f"{self._remote}\n"
        return ""


def test_push_with_token_uses_authenticated_url_and_explicit_refspec() -> None:
    provider = _RecordingProvider(token="ghp_gizli")

    provider._push(Path("/tmp/repo"), "content/20260730")  # noqa: SLF001

    args, secret = provider.commands[-1]
    assert args[0] == "push"
    assert args[1] == "https://x-access-token:ghp_gizli@github.com/klncgty/oleart.git"
    assert args[2] == "HEAD:refs/heads/content/20260730"
    # `--set-upstream` KULLANILMAZ: token'ı .git/config'e upstream URL'i olarak yazardı.
    assert "--set-upstream" not in args
    assert secret == "ghp_gizli"


def test_push_without_token_uses_origin() -> None:
    provider = _RecordingProvider(token="")

    provider._push(Path("/tmp/repo"), "content/x")  # noqa: SLF001

    args, _ = provider.commands[-1]
    assert args == ["push", "--set-upstream", "origin", "content/x"]


def test_non_github_remote_with_token_raises_explanatory_error() -> None:
    provider = _RecordingProvider(remote="/tmp/origin.git", token="ghp_gizli")

    with pytest.raises(GitCommandError, match="GitHub remote"):
        provider._push(Path("/tmp/repo"), "content/x")  # noqa: SLF001


def test_token_is_masked_in_command_errors(work_repo: Path) -> None:
    """Token hata metnine sızmamalı — loglar paylaşılabilir olmalı."""
    provider = LocalGitProvider(token="ghp_gizli")

    with pytest.raises(GitCommandError) as excinfo:
        provider._run(  # noqa: SLF001
            work_repo, ["push", "https://x-access-token:ghp_gizli@github.com/a/b.git"],
            secret="ghp_gizli",
        )

    assert "ghp_gizli" not in str(excinfo.value)
    assert "***" in str(excinfo.value)


# ---------------------------------------------------------------- GitHub API ile PR


def _api_provider(handler, *, token: str = "ghp_gizli") -> _RecordingProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    )
    return _RecordingProvider(token=token, client=client)


def _pr_handler(captured: list[httpx.Request], *, merge_status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.method == "POST":
            return httpx.Response(
                201,
                json={"number": 7, "html_url": "https://github.com/klncgty/oleart/pull/7"},
            )
        return httpx.Response(merge_status, json={"merged": merge_status < 400})

    return handler


def test_pull_request_is_created_and_auto_merged_when_token_present() -> None:
    captured: list[httpx.Request] = []
    provider = _api_provider(_pr_handler(captured))

    url = provider._create_pull_request(Path("/tmp/repo"), "content/x", "blog: makale")  # noqa: SLF001

    assert url == "https://github.com/klncgty/oleart/pull/7"
    create, merge = captured
    assert create.url.path == "/repos/klncgty/oleart/pulls"
    assert create.headers["Authorization"] == "Bearer ghp_gizli"
    # `pr-then-automerge`in "automerge" yarısı: PR insan onayı beklemez.
    assert merge.method == "PUT"
    assert merge.url.path == "/repos/klncgty/oleart/pulls/7/merge"
    provider._client.close()  # type: ignore[union-attr]  # noqa: SLF001


def test_failed_automerge_leaves_pr_open_without_raising() -> None:
    """Dal koruması/çakışma merge'i engellerse yayın yine de başarılıdır: içerik push
    edilmiştir, PR insana kalır."""
    captured: list[httpx.Request] = []
    provider = _api_provider(_pr_handler(captured, merge_status=405))

    url = provider._create_pull_request(Path("/tmp/repo"), "content/x", "blog: makale")  # noqa: SLF001

    assert url == "https://github.com/klncgty/oleart/pull/7"
    provider._client.close()  # type: ignore[union-attr]  # noqa: SLF001


def test_automerge_can_be_disabled() -> None:
    captured: list[httpx.Request] = []
    client = httpx.Client(
        transport=httpx.MockTransport(_pr_handler(captured)), base_url="https://api.github.test"
    )
    provider = _RecordingProvider(token="ghp_gizli", client=client, automerge=False)

    provider._create_pull_request(Path("/tmp/repo"), "content/x", "blog: makale")  # noqa: SLF001

    assert [r.method for r in captured] == ["POST"]  # merge çağrısı yok
    client.close()


def test_failed_pull_request_does_not_raise() -> None:
    """PR açılamaması yayını geçersiz kılmaz: içerik push edildi, PR elle açılabilir."""
    provider = _api_provider(lambda request: httpx.Response(422, text="already exists"))

    assert provider._create_pull_request(Path("/tmp/repo"), "content/x", "b") is None  # noqa: SLF001
    provider._client.close()  # type: ignore[union-attr]  # noqa: SLF001
