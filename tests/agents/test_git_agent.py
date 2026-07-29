from __future__ import annotations

import dataclasses

import pytest

from content_factory.agents.base import AgentContext
from content_factory.agents.git_agent import GitAgent
from content_factory.domain.exceptions import AgentConfigurationError, AgentValidationError
from content_factory.domain.models import Article, PublisherOutput, PublishStrategy
from content_factory.providers.git import CommitResult

from ..support.stub_git import StubGitProvider


def _set_git_config(context: AgentContext, **overrides: object) -> None:
    settings = context.settings
    publish = settings.publish.model_copy(
        update={"git": settings.publish.git.model_copy(update=overrides)}
    )
    context.settings = dataclasses.replace(settings, publish=publish)


def _output(**overrides: object) -> PublisherOutput:
    article = Article(
        brand="oleart",
        slug="zeytinyagi-donar-mi",
        title="Zeytinyağı Donar mı?",
        file_path="content/blog/2026-07-30-zeytinyagi-donar-mi.md",
    )
    defaults: dict[str, object] = {
        "article": article,
        "written_paths": ["content/blog/2026-07-30-zeytinyagi-donar-mi.md"],
    }
    return PublisherOutput(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_returns_publish_result_from_provider(agent_context: AgentContext) -> None:
    agent_context.git = StubGitProvider()

    result = GitAgent(agent_context)(_output())

    assert result.article_slug == "zeytinyagi-donar-mi"
    assert result.file_path == "content/blog/2026-07-30-zeytinyagi-donar-mi.md"
    assert result.commit_sha == "abc1234"
    assert result.pr_url == "https://pr/1"
    assert result.strategy is PublishStrategy.PR_THEN_AUTOMERGE


def test_passes_written_paths_and_repo_to_provider(agent_context: AgentContext) -> None:
    provider = StubGitProvider()
    agent_context.git = provider
    paths = [
        "content/blog/2026-07-30-zeytinyagi-donar-mi.md",
        "public/blog/images/zeytinyagi-donar-mi/cover.webp",
    ]

    GitAgent(agent_context)(_output(written_paths=paths))

    call = provider.calls[0]
    assert call["files"] == paths
    assert call["repo_path"] == str(agent_context.settings.target_repo_path())


def test_pr_strategy_leaves_branch_to_provider(agent_context: AgentContext) -> None:
    provider = StubGitProvider()
    agent_context.git = provider
    _set_git_config(agent_context, publish_strategy="pr-then-automerge")

    GitAgent(agent_context)(_output())

    assert provider.calls[0]["strategy"] == "pr-then-automerge"
    assert provider.calls[0]["branch"] is None


def test_direct_push_uses_configured_branch(agent_context: AgentContext) -> None:
    provider = StubGitProvider(
        result=CommitResult(commit_sha="def5678", branch="main", pr_url=None)
    )
    agent_context.git = provider
    _set_git_config(agent_context, publish_strategy="direct-push", branch="main")

    result = GitAgent(agent_context)(_output())

    assert provider.calls[0]["strategy"] == "direct-push"
    assert provider.calls[0]["branch"] == "main"
    assert result.strategy is PublishStrategy.DIRECT_PUSH
    assert result.pr_url is None


def test_commit_message_is_rendered_from_template(agent_context: AgentContext) -> None:
    provider = StubGitProvider()
    agent_context.git = provider
    _set_git_config(
        agent_context,
        commit_message_template="blog: {slug} eklendi (+ {linked_articles_count} makale)",
    )

    GitAgent(agent_context)(
        _output(
            written_paths=[
                "content/blog/2026-07-30-zeytinyagi-donar-mi.md",
                "content/blog/2026-01-01-erken-hasat-nedir.md",
                "public/blog/images/zeytinyagi-donar-mi/cover.webp",
            ]
        )
    )

    # Yeni makalenin kendi dosyası sayılmaz; yalnızca güncellenen ESKİ makaleler sayılır.
    assert provider.calls[0]["message"] == "blog: zeytinyagi-donar-mi eklendi (+ 1 makale)"


def test_unknown_template_variable_does_not_break_publishing(
    agent_context: AgentContext,
) -> None:
    provider = StubGitProvider()
    agent_context.git = provider
    _set_git_config(agent_context, commit_message_template="blog: {bilinmeyen_alan}")

    GitAgent(agent_context)(_output())

    assert provider.calls[0]["message"] == "blog: {bilinmeyen_alan}"


def test_empty_written_paths_raises(agent_context: AgentContext) -> None:
    agent_context.git = StubGitProvider()
    with pytest.raises(AgentValidationError):
        GitAgent(agent_context)(_output(written_paths=[]))


def test_missing_git_provider_raises_configuration_error(
    agent_context: AgentContext,
) -> None:
    with pytest.raises(AgentConfigurationError):
        GitAgent(agent_context)(_output())
