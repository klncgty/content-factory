from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from content_factory.integrations.git_ops import LocalGitProvider


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
    return LocalGitProvider()


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
