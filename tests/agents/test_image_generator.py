from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from content_factory.agents.base import AgentContext
from content_factory.agents.image_generator import ImageGeneratorAgent
from content_factory.domain.exceptions import AgentConfigurationError, AgentOutputParsingError
from content_factory.domain.models import Article

from ..support.stub_image import StubImageProvider


@pytest.fixture
def base_image(tmp_path: Path) -> Path:
    path = tmp_path / "base.jpg"
    Image.new("RGB", (2000, 2000), color=(120, 100, 40)).save(path, format="JPEG")
    return path


def _article(slug: str | None = "zeytinyagi-donar-mi") -> Article:
    return Article(
        brand="oleart",
        title="Zeytinyağı Donar mı?",
        category="olive_and_oil",
        target_keyword="zeytinyağı donar mı",
        body_markdown="...",
        slug=slug,
    )


def test_generates_three_derivatives_with_correct_sizes(
    agent_context: AgentContext, base_image: Path
) -> None:
    agent_context.image = StubImageProvider(image_path=base_image)
    agent = ImageGeneratorAgent(agent_context)

    article = agent(_article())

    assert article.image is not None
    for path_str, expected_size in [
        (article.image.cover_path, (1600, 900)),
        (article.image.thumbnail_path, (600, 450)),
        (article.image.og_image_path, (1200, 630)),
    ]:
        assert path_str is not None
        path = Path(path_str)
        assert path.exists()
        with Image.open(path) as img:
            assert img.size == expected_size


def test_alt_text_defaults_to_title(agent_context: AgentContext, base_image: Path) -> None:
    agent_context.image = StubImageProvider(image_path=base_image)
    agent = ImageGeneratorAgent(agent_context)
    article = agent(_article())
    assert article.image.alt_text == "Zeytinyağı Donar mı?"


def test_prompt_reflects_category_visual_hints(
    agent_context: AgentContext, base_image: Path
) -> None:
    stub = StubImageProvider(image_path=base_image)
    agent_context.image = stub
    agent = ImageGeneratorAgent(agent_context)

    agent(_article())

    assert "zeytinyağı şişesi" in stub.requests[0].prompt


def test_missing_slug_raises(agent_context: AgentContext, base_image: Path) -> None:
    agent_context.image = StubImageProvider(image_path=base_image)
    agent = ImageGeneratorAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_article(slug=None))


def test_missing_image_provider_raises_configuration_error(agent_context: AgentContext) -> None:
    agent = ImageGeneratorAgent(agent_context)  # agent_context.image is None
    with pytest.raises(AgentConfigurationError):
        agent(_article())
