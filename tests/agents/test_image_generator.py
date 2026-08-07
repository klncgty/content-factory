from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from content_factory.agents.base import AgentContext
from content_factory.agents.image_generator import ImageGeneratorAgent
from content_factory.domain.exceptions import AgentConfigurationError, AgentOutputParsingError
from content_factory.domain.models import Article

from ..support.stub_image import StubImageProvider
from ..support.stub_llm import StubLLMProvider


@pytest.fixture
def base_image(tmp_path: Path) -> Path:
    path = tmp_path / "base.jpg"
    Image.new("RGB", (2000, 2000), color=(120, 100, 40)).save(path, format="JPEG")
    return path


def _article(
    slug: str | None = "zeytinyagi-donar-mi", *, title: str = "Zeytinyağı Donar mı?"
) -> Article:
    return Article(
        brand="oleart",
        title=title,
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


def _scene(text: str) -> str:
    return json.dumps({"scene": text})


def test_prompt_is_built_from_the_article_title(
    agent_context: AgentContext, base_image: Path
) -> None:
    """Asıl gereksinim: başlık ne anlatıyorsa görselin öznesi odur.

    07.08.2026'ya kadar sahne yalnızca KATEGORİDEN seçiliyordu; "Zeytinyağlı Enginar
    Tarifi" makalesinin görselinde enginar yerine her `olive_and_oil` makalesindeki
    aynı zeytinyağı şişesi vardı."""
    stub = StubImageProvider(image_path=base_image)
    agent_context.image = stub
    agent_context.llm = StubLLMProvider(
        responses=[_scene("braised artichoke hearts with lemon in a shallow ceramic dish")]
    )
    agent = ImageGeneratorAgent(agent_context)

    agent(_article(title="Zeytinyağlı Enginar Tarifi", slug="zeytinyagli-enginar-tarifi"))

    prompt = stub.requests[0].prompt
    assert "artichoke" in prompt
    # Kategori sahnesinin jenerik öznesi artık prompt'a hükmetmemeli.
    assert "olive branch" not in prompt


def test_title_is_sent_to_the_scene_model_but_never_to_the_image_model(
    agent_context: AgentContext, base_image: Path
) -> None:
    """Türkçe başlık görsel prompt'una HAM hâliyle girmez: bir dönem denendi ve model
    başlığı görselin üzerine bozuk harflerle yazıp infografik üretti. Başlık yalnızca
    sahneyi yazan metin modeline gider; görsel modeli sahnenin İngilizcesini görür."""
    stub = StubImageProvider(image_path=base_image)
    agent_context.image = stub
    llm = StubLLMProvider(responses=[_scene("a bowl of artichoke stew")])
    agent_context.llm = llm
    agent = ImageGeneratorAgent(agent_context)

    article = _article(title="Zeytinyağlı Enginar Tarifi")
    agent(article)

    assert article.title in llm.requests[0].messages[0].content
    image_prompt = stub.requests[0].prompt
    assert article.title not in image_prompt
    # Metin karşıtı talimatlar korunmalı — başlığın konusu geldi, yazısı değil.
    assert "No text" in image_prompt


def test_scene_model_failure_falls_back_to_category_scene(
    agent_context: AgentContext, base_image: Path
) -> None:
    """Görsel yayın için önkoşul değildir; sahne modelinin arızası onaylanmış bir
    makalenin yayınlanmasını engellememelidir."""
    stub = StubImageProvider(image_path=base_image)
    agent_context.image = stub
    agent_context.llm = StubLLMProvider(responses=["bu JSON değil"])
    agent = ImageGeneratorAgent(agent_context)

    agent(_article())

    prompt = stub.requests[0].prompt
    assert "olive oil" in prompt  # olive_and_oil kategorisinin sahnesi
    assert "No text" in prompt


def test_missing_llm_falls_back_instead_of_raising(
    agent_context: AgentContext, base_image: Path
) -> None:
    """`agent_context.llm` hiç enjekte edilmemişse de run düşmez."""
    stub = StubImageProvider(image_path=base_image)
    agent_context.image = stub

    article = ImageGeneratorAgent(agent_context)(_article())

    assert article.image is not None
    assert "olive oil" in stub.requests[0].prompt


def test_composition_is_deterministic_per_slug_and_varies_across_slugs() -> None:
    """Aynı makale her run'da aynı çerçeveyi almalı (tekrar üretilebilirlik), farklı
    makaleler farklı almalı. `hash()` kullanılsaydı ilk şart bozulurdu — Python string
    hash'i süreçler arasında tuzlanır."""
    composition = ImageGeneratorAgent._composition_for  # noqa: SLF001

    assert composition("zeytinyagli-enginar-tarifi") == composition("zeytinyagli-enginar-tarifi")
    variants = {composition(f"makale-{i}") for i in range(40)}
    assert len(variants) > 1


def test_scene_is_truncated_when_the_model_writes_a_paragraph(
    agent_context: AgentContext, base_image: Path
) -> None:
    """Aşırı uzun bir sahne, görsel modelinde ana özneyi sulandırır."""
    stub = StubImageProvider(image_path=base_image)
    agent_context.image = stub
    agent_context.llm = StubLLMProvider(responses=[_scene("artichoke " * 200)])
    agent = ImageGeneratorAgent(agent_context)

    agent(_article())

    scene_part = stub.requests[0].prompt.split(",")[0]
    assert len(scene_part) <= 300


def test_missing_slug_raises(agent_context: AgentContext, base_image: Path) -> None:
    agent_context.image = StubImageProvider(image_path=base_image)
    agent = ImageGeneratorAgent(agent_context)
    with pytest.raises(AgentOutputParsingError):
        agent(_article(slug=None))


def test_missing_image_provider_raises_configuration_error(agent_context: AgentContext) -> None:
    agent = ImageGeneratorAgent(agent_context)  # agent_context.image is None
    with pytest.raises(AgentConfigurationError):
        agent(_article())
