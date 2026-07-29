"""OpenRouter Images API implementasyonu — `ImageProvider`'ın somut alt sınıfı.

OpenRouter, görsel üretimi metin tamamlamadan **ayrı** bir endpoint üzerinden sunar:
`POST /api/v1/images`. İstek gövdesi `{model, prompt, n, aspect_ratio?, resolution?}`,
yanıt ise `{"data": [{"b64_json": "...", "media_type": "image/png"}]}` biçimindedir.
Bu yüzden `providers/llm/` katmanının (retry/cache/token sayımı) burada karşılığı yoktur
ve bu sınıf `BaseLLMProvider`'dan türemez — bkz. `providers/image.py`.

Hangi parametrenin destekleneceği modele göre değişir (ör. `google/gemini-2.5-flash-image`
`aspect_ratio` destekler ama `resolution` desteklemez). Bu yüzden `aspect_ratio` ve
`resolution` opsiyoneldir ve yalnızca `config/models.yaml`'da tanımlıysa gönderilir —
desteklenmeyen bir parametre sağlayıcı tarafından 400 ile reddedilir.
"""

from __future__ import annotations

import base64
import binascii
import os
import uuid
from math import gcd
from pathlib import Path

import httpx

from content_factory.providers.image import (
    ImageAuthenticationError,
    ImageInsufficientCreditError,
    ImageInvalidRequestError,
    ImageProvider,
    ImageProviderUnavailableError,
    ImageRateLimitError,
    ImageRequest,
    ImageResponseParsingError,
    ImageResult,
)
from content_factory.settings.loader import Settings
from content_factory.utils.logging import get_logger

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
"""Tek yerden yönetilen varsayılan endpoint — testlerde `base_url` ile değiştirilir."""

_MEDIA_TYPE_EXTENSIONS: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}
_DEFAULT_EXTENSION = "png"


class OpenRouterImageProvider(ImageProvider):
    name = "openrouter"

    default_api_key_env = "IMAGE_API_KEY"
    fallback_api_key_env = "OPENROUTER_API_KEY"
    """`IMAGE_API_KEY` tanımlı değilse OpenRouter'ın kendi anahtarına düşülür: görsel de
    metin de aynı hesap üzerinden faturalanır, ayrı bir anahtar tutmak zorunlu değildir.
    Ayrı anahtar tanımlanabilmesi ise başka bir sağlayıcıya (Imagen, Flux) geçildiğinde
    `.env` sözleşmesinin bozulmaması içindir (bkz. `.env.example`)."""

    def __init__(
        self,
        *,
        output_dir: Path,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 180.0,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        client: httpx.Client | None = None,
        app_title: str = "Content Factory",
    ) -> None:
        self._output_dir = output_dir
        self._aspect_ratio = aspect_ratio
        self._resolution = resolution
        self._logger = get_logger(f"providers.image.{self.name}")
        self._api_key = api_key if api_key is not None else self._api_key_from_env()

        if client is not None:
            self._client = client
        else:
            headers = {"Content-Type": "application/json", "X-Title": app_title}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, headers=headers)

    @classmethod
    def _api_key_from_env(cls) -> str | None:
        return os.environ.get(cls.default_api_key_env) or os.environ.get(cls.fallback_api_key_env)

    def close(self) -> None:
        self._client.close()

    # ---------------------------------------------------------------------------- generate

    def generate(self, request: ImageRequest) -> ImageResult:
        self._require_api_key()

        payload: dict[str, object] = {"model": request.model, "prompt": request.prompt, "n": 1}
        aspect_ratio = _aspect_ratio_from_size(request.size) or self._aspect_ratio
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        if self._resolution:
            payload["resolution"] = self._resolution

        self._logger.info(
            f"image_generate model={request.model} aspect_ratio={aspect_ratio} "
            f"resolution={self._resolution}"
        )
        response = self._post(payload)
        image_bytes, extension = self._extract_image(response.json(), model=request.model)
        file_path = self._write(image_bytes, extension)

        self._logger.info(f"image_generate_ok model={request.model} path={file_path}")
        return ImageResult(file_path=str(file_path), provider=self.name, model=request.model)

    # ------------------------------------------------------------------------ health_check

    def health_check(self) -> bool:
        """Asla exception fırlatmaz — başarısızlık `False` olarak döner."""
        if not self._api_key:
            self._logger.warning(
                f"health_check: {self.default_api_key_env}/{self.fallback_api_key_env} "
                f"tanımlı değil"
            )
            return False
        try:
            return self._client.get("/images/models").status_code == 200
        except httpx.HTTPError as exc:
            self._logger.warning(f"health_check başarısız: {exc}")
            return False

    # ------------------------------------------------------------------------------ dahili

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise ImageAuthenticationError(
                f"{self.default_api_key_env} veya {self.fallback_api_key_env} tanımlı değil — "
                f"görsel üretilemez"
            )

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        model = str(payload["model"])
        try:
            response = self._client.post("/images", json=payload)
        except httpx.TimeoutException as exc:
            raise ImageProviderUnavailableError(
                f"Görsel üretimi zaman aşımına uğradı (model={model})"
            ) from exc
        except httpx.ConnectError as exc:
            raise ImageProviderUnavailableError(f"OpenRouter'a bağlanılamadı: {exc}") from exc
        _raise_for_status(response, model=model)
        return response

    def _extract_image(self, data: object, *, model: str) -> tuple[bytes, str]:
        """`{"data": [{"b64_json": ..., "media_type": ...}]}` yanıtından ham baytları
        çıkarır. Bazı modeller base64 yerine geçici bir URL döndürebildiği için `url`
        biçimi de desteklenir."""
        if not isinstance(data, dict):
            raise ImageResponseParsingError(f"Beklenmeyen yanıt tipi (model={model}): {type(data)}")

        entries = data.get("data")
        if not isinstance(entries, list) or not entries:
            raise ImageResponseParsingError(
                f"Yanıtta görsel yok (model={model}). Sağlayıcı yanıtı: {data}"
            )
        entry = entries[0]
        if not isinstance(entry, dict):
            raise ImageResponseParsingError(f"Beklenmeyen görsel kaydı (model={model}): {entry}")

        extension = _MEDIA_TYPE_EXTENSIONS.get(str(entry.get("media_type", "")), _DEFAULT_EXTENSION)

        encoded = entry.get("b64_json")
        if isinstance(encoded, str) and encoded:
            try:
                return base64.b64decode(encoded, validate=True), extension
            except (binascii.Error, ValueError) as exc:
                raise ImageResponseParsingError(
                    f"Görsel base64 olarak çözülemedi (model={model}): {exc}"
                ) from exc

        url = entry.get("url")
        if isinstance(url, str) and url:
            return self._download(url, model=model), extension

        raise ImageResponseParsingError(
            f"Görsel kaydında ne `b64_json` ne `url` var (model={model}): {entry}"
        )

    def _download(self, url: str, *, model: str) -> bytes:
        try:
            response = httpx.get(url, timeout=self._client.timeout, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise ImageProviderUnavailableError(
                f"Üretilen görsel indirilemedi (model={model}): {exc}"
            ) from exc
        if response.status_code >= 400:
            raise ImageProviderUnavailableError(
                f"Üretilen görsel indirilemedi ({response.status_code}, model={model})"
            )
        return response.content

    def _write(self, image_bytes: bytes, extension: str) -> Path:
        if not image_bytes:
            raise ImageResponseParsingError("Sağlayıcı boş bir görsel döndürdü")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._output_dir / f"{uuid.uuid4().hex}.{extension}"
        file_path.write_bytes(image_bytes)
        return file_path


def _aspect_ratio_from_size(size: tuple[int, int] | None) -> str | None:
    """(1600, 900) -> "16:9". OpenRouter piksel boyutu değil, en-boy oranı kabul eder."""
    if size is None:
        return None
    width, height = size
    if width <= 0 or height <= 0:
        return None
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _raise_for_status(response: httpx.Response, *, model: str) -> None:
    status = response.status_code
    if status < 400:
        return
    if status in (401, 403):
        raise ImageAuthenticationError(
            f"OpenRouter kimlik doğrulama hatası ({status}, model={model})"
        )
    if status == 402:
        raise ImageInsufficientCreditError(
            f"OpenRouter bakiyesi görsel üretimi için yetersiz (model={model}). "
            f"Sağlayıcı yanıtı: {response.text}"
        )
    if status == 429:
        raise ImageRateLimitError(f"OpenRouter rate limit (model={model})")
    if status in (400, 404, 422):
        raise ImageInvalidRequestError(
            f"Geçersiz görsel isteği ({status}, model={model}): {response.text}. "
            f"Model bu parametreleri desteklemiyor olabilir — "
            f"config/models.yaml: agents.image_generator alanlarını kontrol edin."
        )
    raise ImageProviderUnavailableError(f"OpenRouter görsel hatası ({status}, model={model})")


# ------------------------------------------------------------------------------- factory

_REGISTRY: dict[str, type[ImageProvider]] = {"openrouter": OpenRouterImageProvider}


def register_image_provider(name: str, provider_cls: type[ImageProvider]) -> None:
    """Yeni bir görsel sağlayıcıyı kaydeder (ör. `google-imagen`, `replicate-flux`).
    Kaydedildikten sonra `config/models.yaml: agents.image_generator.provider` bu adı
    kullanabilir; hiçbir agent kodu değişmez."""
    _REGISTRY[name] = provider_cls


def available_image_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def create_image_provider(settings: Settings, *, output_dir: Path) -> ImageProvider:
    """`config/models.yaml: agents.image_generator` bölümünden görsel sağlayıcıyı inşa eder.

    LLM tarafındaki gibi ayrı bir `factory.py` modülü yoktur: görsel katmanında tek bir
    implementasyon ve etrafında sarmalanacak bir retry/cache zinciri yok, bu yüzden
    factory somut sınıfın yanında duruyor (bkz. `providers/llm/factory.py` — oradaki
    ayrımın gerekçesi katman sayısıdır)."""
    config = settings.models.for_agent("image_generator")
    provider_name = config.provider or settings.models.default_provider
    provider_cls = _REGISTRY.get(provider_name)
    if provider_cls is None:
        raise ImageInvalidRequestError(
            f"Bilinmeyen görsel sağlayıcı: {provider_name!r} "
            f"(kayıtlı: {available_image_providers()})"
        )
    if provider_cls is not OpenRouterImageProvider:  # pragma: no cover - ileride eklenecek
        return provider_cls()  # type: ignore[call-arg]
    return OpenRouterImageProvider(
        output_dir=output_dir,
        timeout_seconds=float(settings.engine.timeouts.image_generation_seconds),
        aspect_ratio=config.aspect_ratio,
        resolution=config.resolution,
    )
