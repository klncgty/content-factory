from __future__ import annotations

from pathlib import Path

import pytest

from content_factory.prompts.loader import PromptLoader

EXPECTED_AGENTS = {
    "topic_scout",
    "research",
    "strategist",
    "writer",
    "seo_optimizer",
    "editor",
    "scope_guard",
}


@pytest.fixture
def loader(settings) -> PromptLoader:  # noqa: ANN001 - pytest fixture injection
    return PromptLoader(settings.root)


@pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
def test_all_llm_agents_have_prompt_files(loader: PromptLoader, agent_name: str) -> None:
    prompt_set = loader.load(agent_name)
    assert prompt_set.system.strip(), f"{agent_name}/system.md boş"
    assert prompt_set.user_template.strip(), f"{agent_name}/user.md boş"
    assert prompt_set.examples.strip(), f"{agent_name}/examples.md boş"


def test_load_returns_cached_instance(loader: PromptLoader) -> None:
    first = loader.load("writer")
    second = loader.load("writer")
    assert first is second


def test_force_reload_bypasses_cache(loader: PromptLoader) -> None:
    first = loader.load("writer")
    second = loader.load("writer", force_reload=True)
    assert first is not second
    assert first == second


def test_invalidate_specific_agent(loader: PromptLoader) -> None:
    first = loader.load("writer")
    loader.invalidate("writer")
    second = loader.load("writer")
    assert first is not second


def test_invalidate_all(loader: PromptLoader) -> None:
    loader.load("writer")
    loader.load("editor")
    loader.invalidate()
    assert loader._cache == {}  # noqa: SLF001 - iç durumu doğrulayan beyaz kutu test


def test_missing_agent_yields_empty_prompt_set_not_error(tmp_path: Path) -> None:
    loader = PromptLoader(tmp_path)
    prompt_set = loader.load("does-not-exist")
    assert prompt_set.system == ""
    assert prompt_set.user_template == ""
    assert prompt_set.examples == ""


def test_render_user_substitutes_variables(loader: PromptLoader) -> None:
    prompt_set = loader.load("seo_optimizer")
    rendered = prompt_set.render_user(
        title="Test Başlık",
        target_keyword="test anahtar kelime",
        secondary_keywords="a, b",
        body_excerpt="...",
    )
    assert "Test Başlık" in rendered
    assert "test anahtar kelime" in rendered
    assert "$title" not in rendered


def test_render_user_leaves_missing_variables_untouched(loader: PromptLoader) -> None:
    prompt_set = loader.load("seo_optimizer")
    rendered = prompt_set.render_user(title="X")
    assert "$target_keyword" in rendered  # safe_substitute -> patlamaz, olduğu gibi kalır
