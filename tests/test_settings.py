from __future__ import annotations

import pytest

from content_factory.settings.loader import ConfigError, Settings


def test_loads_oleart_settings(settings: Settings) -> None:
    assert settings.brand_name == "oleart"
    assert settings.brand.brand == "oleart"
    assert settings.brand.display_name == "Oleart"


def test_scope_groups_match_expected_categories(settings: Settings) -> None:
    group_ids = {g.id for g in settings.scope.groups}
    assert group_ids == {"olive_and_oil", "wooden_products"}
    olive_group = next(g for g in settings.scope.groups if g.id == "olive_and_oil")
    assert "zeytinyağı" in olive_group.topics


def test_models_config_has_all_agent_roles(settings: Settings) -> None:
    for role in ["topic_scout", "strategist", "writer", "seo_optimizer", "linker", "editor"]:
        cfg = settings.models.for_agent(role)
        assert cfg.model is not None, role


def test_publish_target_repo_path_resolves_next_to_content_factory(settings: Settings) -> None:
    target = settings.target_repo_path()
    assert target.name == "oleart.co"


def test_unknown_brand_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        Settings.load("does-not-exist")
