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

    # Beklenen boyutlar config'den okunur: türev boyutları bir ayar (bkz. engine.yaml —
    # cover, temel görselin gerçek çözünürlüğüne göre seçiliyor), sabitlemek testi her
    # ayar değişikliğinde kırıyordu. Doğrulanan davranış "üç türev de config'deki
    # boyutta üretiliyor" olmalı.
    derivatives = agent_context.settings.engine.image_derivatives
    assert article.image is not None
    for path_str, expected_size in [
        (article.image.cover_path, derivatives["cover"].size),
        (article.image.thumbnail_path, derivatives["thumbnail"].size),
        (article.image.og_image_path, derivatives["og_image"].size),
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

    prompt = stub.requests[0].prompt
    assert "olive oil" in prompt  # olive_and_oil kategorisinin sahnesi
    # Başlık prompt'a GİRMEMELİ: verildiğinde model onu görselin üzerine bozuk harflerle
    # yazıp makaleyle alakasız bir infografik üretiyordu.
    assert _article().title not in prompt
    assert "No text" in prompt


def test_missing_slug_raises(agent_context: AgentContext, base_image: Path) -> None:
    agent_context.image = StubImageProvider(image_path=base_image)
    agent = ImageGeneratorAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_article(slug=None))


def test_missing_image_provider_raises_configuration_error(agent_context: AgentContext) -> None:
    agent = ImageGeneratorAgent(agent_context)  # agent_context.image is None
    with pytest.raises(AgentConfigurationError):
        agent(_article())
