from __future__ import annotations

import re
from pathlib import Path

import pytest

from content_factory.agents.editor import EditorAgent
from content_factory.agents.research import ResearchAgent
from content_factory.agents.seo_optimizer import SEOOptimizerAgent
from content_factory.agents.strategist import StrategistAgent
from content_factory.agents.topic_scout import TopicScoutAgent
from content_factory.agents.writer import WriterAgent
from content_factory.guards.scope_guard import ScopeGuard
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

# `prompt_vars` taşıyan sınıf, agent adına göre — ScopeGuard bir BaseAgent değil (agent
# değil, saf yardımcı) ama aynı prompt_vars sözleşmesine uyuyor (bkz. guards/scope_guard.py).
_PROMPT_VARS_OWNERS: dict[str, type] = {
    "topic_scout": TopicScoutAgent,
    "research": ResearchAgent,
    "strategist": StrategistAgent,
    "writer": WriterAgent,
    "seo_optimizer": SEOOptimizerAgent,
    "editor": EditorAgent,
    "scope_guard": ScopeGuard,
}

_TEMPLATE_VAR_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")


def _template_vars(text: str) -> set[str]:
    return set(_TEMPLATE_VAR_RE.findall(text))


@pytest.fixture
def loader(settings) -> PromptLoader:  # noqa: ANN001 - pytest fixture injection
    return PromptLoader(settings.root, brand="oleart")


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


def test_render_user_raises_on_missing_variable(loader: PromptLoader) -> None:
    prompt_set = loader.load("seo_optimizer")
    with pytest.raises(KeyError):
        prompt_set.render_user(title="X")  # substitute -> eksik değişkende sessiz kalmaz


@pytest.mark.parametrize("agent_name", sorted(_PROMPT_VARS_OWNERS))
def test_prompt_vars_match_user_template(loader: PromptLoader, agent_name: str) -> None:
    """Agent'ın `render_user`'a gönderdiği anahtarlar (`prompt_vars`) ile `user.md`
    içindeki $değişkenler birebir eşleşmeli — biri diğerinden fazla/eksik olursa
    `Template.substitute` ya KeyError fırlatır ya da agent'ın gönderdiği bir değer
    şablonda hiç kullanılmaz (sessiz bir sözleşme kayması)."""
    owner = _PROMPT_VARS_OWNERS[agent_name]
    prompt_set = loader.load(agent_name)
    template_vars = _template_vars(prompt_set.user_template)
    assert owner.prompt_vars == template_vars, (
        f"{agent_name}: prompt_vars={sorted(owner.prompt_vars)} != "
        f"user.md değişkenleri={sorted(template_vars)}"
    )


# ---------------------------------------------- marka override'ı (Adım 7, madde 2 ve 3)


def test_brand_override_wins_over_shared_prompt(settings) -> None:  # noqa: ANN001
    """`brands/{marka}/prompts/{agent}/system.md` varsa ortak dosyanın yerine geçer."""
    shared = PromptLoader(settings.root).load("writer")
    branded = PromptLoader(settings.root, brand="oleart").load("writer")

    assert shared.system != branded.system
    assert "Oleart" in branded.system
    assert "Oleart" not in shared.system


def test_fallback_to_shared_is_per_file(settings) -> None:  # noqa: ANN001
    """Override DOSYA bazındadır: marka yalnızca system.md'yi ezdiyse user.md ortaktan
    gelir — markaya özgü olan genellikle "sen kimsin", JSON şeması değildir."""
    loader = PromptLoader(settings.root, brand="oleart")
    brand_dir = loader.brand_agent_dir("writer")

    assert (brand_dir / "system.md").exists()
    assert not (brand_dir / "user.md").exists()
    assert loader.load("writer").user_template == PromptLoader(settings.root).load(
        "writer"
    ).user_template


def test_unknown_brand_falls_back_to_shared_prompts(settings) -> None:  # noqa: ANN001
    """Override dizini olmayan bir marka ortak prompt'larla çalışabilmeli — ikinci
    markanın ilk gün çalışması için gereken davranış."""
    loader = PromptLoader(settings.root, brand="henuz-yok")
    assert loader.load("writer").system == PromptLoader(settings.root).load("writer").system


@pytest.mark.parametrize("agent_name", sorted(EXPECTED_AGENTS))
def test_shared_prompts_are_brand_neutral(agent_name: str, settings) -> None:  # noqa: ANN001
    """Ortak prompt'larda markaya/konuya özgü metin kalmamalı — kalırsa ikinci marka
    kendi konusu yerine Oleart'ın konusunu yazar (Adım 7'nin asıl kabul kriteri)."""
    prompt_set = PromptLoader(settings.root).load(agent_name)
    haystack = (
        f"{prompt_set.system}\n{prompt_set.user_template}\n{prompt_set.examples}".lower()
    )

    for term in ("oleart", "zeytin", "olive_and_oil", "wooden_products"):
        assert term not in haystack, f"prompts/{agent_name}/ içinde marka-özel metin: {term!r}"
