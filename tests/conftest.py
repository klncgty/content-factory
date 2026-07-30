from __future__ import annotations

from pathlib import Path

import pytest

from content_factory.agents.base import AgentContext
from content_factory.cli import _topic_file_specs
from content_factory.knowledge.loader import BrandKnowledge, KnowledgeLoader
from content_factory.prompts.loader import PromptLoader
from content_factory.settings.loader import Settings
from content_factory.state.sqlite_store import SQLiteStateStore


@pytest.fixture
def settings() -> Settings:
    return Settings.load("oleart")


@pytest.fixture
def knowledge(settings: Settings) -> BrandKnowledge:
    return KnowledgeLoader(
        settings.root, topic_files=_topic_file_specs(settings)
    ).load("oleart")


@pytest.fixture
def prompt_loader(settings: Settings) -> PromptLoader:
    return PromptLoader(settings.root, brand="oleart")


@pytest.fixture
def state_store(tmp_path: Path) -> SQLiteStateStore:
    store = SQLiteStateStore(tmp_path / "test.db")
    store.init_schema()
    yield store
    store.close()


@pytest.fixture
def agent_context(
    settings: Settings,
    knowledge: BrandKnowledge,
    prompt_loader: PromptLoader,
    state_store: SQLiteStateStore,
) -> AgentContext:
    return AgentContext(
        brand="oleart",
        run_id="test-run-0001",
        settings=settings,
        knowledge=knowledge,
        prompts=prompt_loader,
        state=state_store,
    )
