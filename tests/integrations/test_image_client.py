"""Görsel sağlayıcı testleri — gerçek ağ çağrısı yapılmaz.

`httpx.MockTransport` ile iki sağlayıcının da HTTP sözleşmesi taklit edilir:

- `GoogleAIStudioImageProvider`: `POST /models/{model}:generateContent`, yanıt
  `candidates[0].content.parts[].inlineData.data`
- `OpenRouterImageProvider`: `POST /images`, yanıt `data[0].b64_json`

Doğrulanan şey her iki yönde de aynı: istek gövdesinin doğru kurulduğu ve yanıttan
dosyanın doğru yazıldığı.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from content_factory.integrations.image_client import (
    GoogleAIStudioImageProvider,
    OpenRouterImageProvider,
    available_image_providers,
    create_image_provider,
)
from content_factory.providers.image import (
    ImageAuthenticationError,
    ImageInsufficientCreditError,
    ImageInvalidRequestError,
    ImageProviderUnavailableError,
    ImageRateLimitError,
    ImageRequest,
    ImageResponseParsingError,
)
from content_factory.settings.loader import Settings

PNG_BYTES = b"\x89PNG\r\n\x1a\n-fake-image-bytes"


def _b64(data: bytes = PNG_BYTES) -> str:
    return base64.b64encode(data).decode("ascii")


def _provider(
    tmp_path: Path,
    handler: object,
    **kwargs: object,
) -> OpenRouterImageProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        base_url="https://openrouter.test/api/v1",
    )
    return OpenRouterImageProvider(
        output_dir=tmp_path / "base",
        api_key="test-key",
        client=client,
        **kwargs,  # type: ignore[arg-type]
    )


def _ok_handler(
    captured: list[httpx.Request], *, media_type: str = "image/png", b64: str | None = None
):
    encoded = b64 if b64 is not None else _b64()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, json={"data": [{"b64_json": encoded, "media_type": media_type}]}
        )

    return handler


OPENROUTER_MODEL = "google/gemini-2.5-flash-image"
"""OpenRouter `saglayici/model` biçimi ister; Gemini API çıplak model adı."""


def _request(**kwargs: object) -> ImageRequest:
    payload: dict[str, object] = {
        "prompt": "zeytinyağı şişesi, doğal ışık",
        "model": "gemini-2.5-flash-image",
    }
    payload.update(kwargs)
    return ImageRequest(**payload)  # type: ignore[arg-type]


# ------------------------------------------------------------------------------- mutlu yol


def test_generate_writes_decoded_image_to_output_dir(tmp_path: Path) -> None:
    provider = _provider(tmp_path, _ok_handler([]))

    result = provider.generate(_request(model=OPENROUTER_MODEL))

    path = Path(result.file_path)
    assert path.exists()
    assert path.read_bytes() == PNG_BYTES
    assert path.suffix == ".png"
    assert path.parent == tmp_path / "base"
    assert result.provider == "openrouter"
    # OpenRouter'da model adı olduğu gibi taşınır — Gemini'deki gibi önek temizlenmez.
    assert result.model == OPENROUTER_MODEL


def test_request_targets_images_endpoint_with_expected_payload(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    provider = _provider(tmp_path, _ok_handler(captured), aspect_ratio="16:9")

    provider.generate(_request(model=OPENROUTER_MODEL))

    assert len(captured) == 1
    assert captured[0].url.path.endswith("/images")
    body = json.loads(captured[0].content)
    assert body == {
        "model": OPENROUTER_MODEL,
        "prompt": "zeytinyağı şişesi, doğal ışık",
        "n": 1,
        "aspect_ratio": "16:9",
    }


def test_resolution_sent_only_when_configured(tmp_path: Path) -> None:
    """gemini-2.5-flash-image `resolution` desteklemez; parametre yapılandırılmadıysa
    gövdeye hiç eklenmemeli, aksi halde sağlayıcı 400 döner."""
    captured: list[httpx.Request] = []
    _provider(tmp_path, _ok_handler(captured)).generate(_request())
    assert "resolution" not in json.loads(captured[0].content)

    captured.clear()
    _provider(tmp_path, _ok_handler(captured), resolution="2K").generate(_request())
    assert json.loads(captured[0].content)["resolution"] == "2K"


def test_request_size_is_converted_to_aspect_ratio(tmp_path: Path) -> None:
    """OpenRouter piksel boyutu kabul etmez; `ImageRequest.size` en-boy oranına çevrilir
    ve yapılandırılmış varsayılanı geçersiz kılar."""
    captured: list[httpx.Request] = []
    provider = _provider(tmp_path, _ok_handler(captured), aspect_ratio="1:1")

    provider.generate(_request(size=(1600, 900)))

    assert json.loads(captured[0].content)["aspect_ratio"] == "16:9"


@pytest.mark.parametrize(
    ("media_type", "expected_suffix"),
    [
        ("image/png", ".png"),
        ("image/jpeg", ".jpg"),
        ("image/webp", ".webp"),
        ("image/unknown", ".png"),  # bilinmeyen tip -> güvenli varsayılan
    ],
)
def test_media_type_determines_file_extension(
    tmp_path: Path, media_type: str, expected_suffix: str
) -> None:
    provider = _provider(tmp_path, _ok_handler([], media_type=media_type))
    result = provider.generate(_request())
    assert Path(result.file_path).suffix == expected_suffix


def test_url_response_is_downloaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bazı modeller base64 yerine geçici bir URL döndürebilir."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"url": "https://cdn.test/img.png"}]})

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        assert url == "https://cdn.test/img.png"
        return httpx.Response(200, content=PNG_BYTES)

    monkeypatch.setattr(httpx, "get", fake_get)
    result = _provider(tmp_path, handler).generate(_request())

    assert Path(result.file_path).read_bytes() == PNG_BYTES


# ------------------------------------------------------------------------------- hatalar


def test_missing_api_key_raises_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("anahtar yokken istek gönderilmemeliydi")

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://openrouter.test/api/v1"
    )
    provider = OpenRouterImageProvider(output_dir=tmp_path, client=client)

    with pytest.raises(ImageAuthenticationError):
        provider.generate(_request())


def test_falls_back_to_openrouter_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IMAGE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    client = httpx.Client(
        transport=httpx.MockTransport(_ok_handler([])),
        base_url="https://openrouter.test/api/v1",
    )
    provider = OpenRouterImageProvider(output_dir=tmp_path, client=client)

    assert Path(provider.generate(_request()).file_path).exists()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ImageAuthenticationError),
        (403, ImageAuthenticationError),
        (402, ImageInsufficientCreditError),
        (429, ImageRateLimitError),
        (400, ImageInvalidRequestError),
        (404, ImageInvalidRequestError),
        (422, ImageInvalidRequestError),
        (500, ImageProviderUnavailableError),
        (503, ImageProviderUnavailableError),
    ],
)
def test_http_errors_map_to_typed_exceptions(
    tmp_path: Path, status: int, expected: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="sağlayıcı hata mesajı")

    with pytest.raises(expected):
        _provider(tmp_path, handler).generate(_request())


def test_timeout_maps_to_provider_unavailable(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    with pytest.raises(ImageProviderUnavailableError):
        _provider(tmp_path, handler).generate(_request())


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": [{}]},
        {"created": 1},
        {"data": [{"b64_json": "bu-gecerli-base64-degil!"}]},
    ],
)
def test_unparseable_responses_raise_parsing_error(tmp_path: Path, payload: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ImageResponseParsingError):
        _provider(tmp_path, handler).generate(_request())


def test_empty_image_bytes_raise_parsing_error(tmp_path: Path) -> None:
    provider = _provider(tmp_path, _ok_handler([], b64=""))
    with pytest.raises(ImageResponseParsingError):
        provider.generate(_request())


# ------------------------------------------------------------------ Google AI Studio


def _google_provider(
    tmp_path: Path, handler: object, **kwargs: object
) -> GoogleAIStudioImageProvider:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        base_url="https://gemini.test/v1beta",
    )
    return GoogleAIStudioImageProvider(
        output_dir=tmp_path / "base",
        api_key="test-key",
        client=client,
        **kwargs,  # type: ignore[arg-type]
    )


def _google_ok_handler(captured: list[httpx.Request], *, mime_type: str = "image/png"):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"inlineData": {"mimeType": mime_type, "data": _b64()}}]
                        },
                        "finishReason": "STOP",
                    }
                ]
            },
        )

    return handler


def test_google_generate_writes_decoded_image(tmp_path: Path) -> None:
    result = _google_provider(tmp_path, _google_ok_handler([])).generate(_request())

    path = Path(result.file_path)
    assert path.read_bytes() == PNG_BYTES
    assert path.suffix == ".png"
    assert result.provider == "google-ai-studio"


def test_google_request_shape(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    provider = _google_provider(tmp_path, _google_ok_handler(captured), aspect_ratio="16:9")

    provider.generate(_request())

    request = captured[0]
    assert request.url.path.endswith("/models/gemini-2.5-flash-image:generateContent")
    # Anahtar query parametresiyle gider (x-goog-api-key başlığı yeni anahtar
    # formatında 403 döndürüyor — bkz. GoogleAIStudioImageProvider docstring).
    assert request.url.params["key"] == "test-key"
    assert json.loads(request.content) == {
        "contents": [{"parts": [{"text": "zeytinyağı şişesi, doğal ışık"}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "16:9"},
        },
    }


def test_google_omits_image_config_when_no_aspect_ratio(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    _google_provider(tmp_path, _google_ok_handler(captured)).generate(_request())

    assert "imageConfig" not in json.loads(captured[0].content)["generationConfig"]


def test_google_strips_openrouter_vendor_prefix(tmp_path: Path) -> None:
    """Config yanlışlıkla OpenRouter biçimini (`google/...`) taşıyorsa istek 404 olmamalı."""
    captured: list[httpx.Request] = []
    provider = _google_provider(tmp_path, _google_ok_handler(captured))

    result = provider.generate(_request(model=OPENROUTER_MODEL))

    assert captured[0].url.path.endswith("/models/gemini-2.5-flash-image:generateContent")
    assert result.model == "gemini-2.5-flash-image"


def test_google_size_overrides_configured_aspect_ratio(tmp_path: Path) -> None:
    captured: list[httpx.Request] = []
    provider = _google_provider(tmp_path, _google_ok_handler(captured), aspect_ratio="1:1")

    provider.generate(_request(size=(1600, 900)))

    config = json.loads(captured[0].content)["generationConfig"]
    assert config["imageConfig"]["aspectRatio"] == "16:9"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ImageAuthenticationError),
        (403, ImageAuthenticationError),
        (429, ImageRateLimitError),
        (400, ImageInvalidRequestError),
        (404, ImageInvalidRequestError),
        (500, ImageProviderUnavailableError),
    ],
)
def test_google_http_errors_map_to_typed_exceptions(
    tmp_path: Path, status: int, expected: type[Exception]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "sağlayıcı mesajı"}})

    with pytest.raises(expected):
        _google_provider(tmp_path, handler).generate(_request())


def test_google_quota_zero_message_is_preserved(tmp_path: Path) -> None:
    """429 hem 'çok hızlı' hem 'bu model için kotan 0' olabilir; ikisini ayırt etmek
    yalnızca sağlayıcı mesajıyla mümkün, o yüzden mesaj yutulmamalı."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"message": "Quota exceeded ... limit: 0, model: ..."}}
        )

    with pytest.raises(ImageRateLimitError, match="limit: 0"):
        _google_provider(tmp_path, handler).generate(_request())


@pytest.mark.parametrize(
    "payload",
    [
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": []},
        {
            "candidates": [
                {"content": {"parts": [{"text": "üretemedim"}]}, "finishReason": "SAFETY"}
            ]
        },
    ],
)
def test_google_missing_image_raises_invalid_request(tmp_path: Path, payload: dict) -> None:
    """Güvenlik filtresi görsel döndürmez. Yeniden denemek işe yaramayacağı için bu
    parse hatası değil, geçersiz istek olarak raporlanır."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ImageInvalidRequestError):
        _google_provider(tmp_path, handler).generate(_request())


def test_google_invalid_base64_raises_parsing_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"inlineData": {"data": "gecersiz!"}}]}}]},
        )

    with pytest.raises(ImageResponseParsingError):
        _google_provider(tmp_path, handler).generate(_request())


def test_google_missing_api_key_raises_before_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("anahtar yokken istek gönderilmemeliydi")

    client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://gemini.test/v1beta"
    )
    with pytest.raises(ImageAuthenticationError):
        GoogleAIStudioImageProvider(output_dir=tmp_path, client=client).generate(_request())


def test_google_falls_back_to_google_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

    client = httpx.Client(
        transport=httpx.MockTransport(_google_ok_handler([])),
        base_url="https://gemini.test/v1beta",
    )
    provider = GoogleAIStudioImageProvider(output_dir=tmp_path, client=client)

    assert Path(provider.generate(_request()).file_path).exists()


# ------------------------------------------------------------------------------- factory


def test_registry_contains_both_providers() -> None:
    assert set(available_image_providers()) >= {"google-ai-studio", "openrouter"}


def test_create_image_provider_reads_models_yaml(tmp_path: Path, settings: Settings) -> None:
    """Varsayılan yapılandırma Google AI Studio'dur (bkz. config/models.yaml)."""
    provider = create_image_provider(settings, output_dir=tmp_path)

    assert isinstance(provider, GoogleAIStudioImageProvider)
    config = settings.models.for_agent("image_generator")
    assert provider._aspect_ratio == config.aspect_ratio  # noqa: SLF001
    provider.close()


def test_create_image_provider_can_build_openrouter(tmp_path: Path, settings: Settings) -> None:
    """Sağlayıcı değişimi tek bir config alanıyla olmalı — kod değişmemeli."""
    settings.models.agents["image_generator"] = settings.models.for_agent(
        "image_generator"
    ).model_copy(update={"provider": "openrouter", "resolution": "2K"})

    provider = create_image_provider(settings, output_dir=tmp_path)

    assert isinstance(provider, OpenRouterImageProvider)
    assert provider._resolution == "2K"  # noqa: SLF001
    provider.close()


def test_create_image_provider_rejects_unknown_provider(tmp_path: Path, settings: Settings) -> None:
    settings.models.agents["image_generator"] = settings.models.for_agent(
        "image_generator"
    ).model_copy(update={"provider": "bilinmeyen-saglayici"})

    with pytest.raises(ImageInvalidRequestError):
        create_image_provider(settings, output_dir=tmp_path)
