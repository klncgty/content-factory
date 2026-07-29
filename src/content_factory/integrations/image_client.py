"""`ImageProvider`'ın somut implementasyonları ve sağlayıcı factory'si.

Üç sağlayıcı kayıtlıdır; hangisinin kullanılacağı tamamen
`config/models.yaml: agents.image_generator.provider` alanındandır — agent kodu
sağlayıcı adı bilmez (bkz. ARCHITECTURE.md §9).

- **`replicate`** (varsayılan): Replicate. Diğerlerinden farkı **iki adımlı** olması:
  modelin güncel sürümü sorulur (`GET /models/{owner}/{name}` -> `latest_version.id`),
  sonra `POST /predictions` ile üretim başlatılır ve sonuç bir **URL** olarak döner
  (base64 değil), bu yüzden ayrıca indirilir.
- **`google-ai-studio`**: Google AI Studio / Gemini API.
  `POST /v1beta/models/{model}:generateContent`, gövdede
  `generationConfig.responseModalities: ["IMAGE"]`; görsel
  `candidates[0].content.parts[].inlineData.data` içinde base64 döner.
- **`openrouter`**: OpenRouter Images API. `POST /api/v1/images`, yanıt
  `{"data": [{"b64_json": ..., "media_type": ...}]}`.

Hepsi metin (LLM) katmanından ayrıdır: görsel üretimi ayrı bir endpoint ve ayrı
bir istek/yanıt sözleşmesi kullandığından `BaseLLMProvider`'ın retry/cache/token-sayımı
katmanları buraya uymaz — bu yüzden bu sınıflar `BaseLLMProvider`'dan türemez.

Desteklenen istek parametreleri modele göre değişir (ör. OpenRouter'da
`google/gemini-2.5-flash-image` `aspect_ratio` destekler ama `resolution` desteklemez).
Bu yüzden `aspect_ratio`/`resolution` opsiyoneldir ve yalnızca config'de tanımlıysa
gönderilir; desteklenmeyen bir parametre sağlayıcı tarafından 400 ile reddedilir.
"""

from __future__ import annotations

import base64
import binascii
import os
import time
import uuid
from collections.abc import Callable
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

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GOOGLE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
REPLICATE_BASE_URL = "https://api.replicate.com/v1"
"""Endpoint'ler tek yerden yönetilir — testlerde `base_url` parametresiyle değiştirilir."""

_MEDIA_TYPE_EXTENSIONS: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
}
_DEFAULT_EXTENSION = "png"


class _HttpImageProvider(ImageProvider):
    """İki somut sağlayıcının paylaştığı ortak davranış: API anahtarının çevreden
    çözülmesi, üretilen baytların diske yazılması ve MIME tipinden dosya uzantısı."""

    name: str
    default_api_key_env: str
    fallback_api_key_env: str | None = None

    def __init__(
        self,
        *,
        output_dir: Path,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        client: httpx.Client | None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._logger = get_logger(f"providers.image.{self.name}")
        self._api_key = api_key if api_key is not None else self._api_key_from_env()
        self._client = client or httpx.Client(
            base_url=base_url, timeout=timeout_seconds, headers=headers or {}
        )

    @classmethod
    def _api_key_from_env(cls) -> str | None:
        key = os.environ.get(cls.default_api_key_env)
        if key or cls.fallback_api_key_env is None:
            return key
        return os.environ.get(cls.fallback_api_key_env)

    def close(self) -> None:
        self._client.close()

    def _require_api_key(self) -> None:
        if not self._api_key:
            names = self.default_api_key_env
            if self.fallback_api_key_env:
                names += f" veya {self.fallback_api_key_env}"
            raise ImageAuthenticationError(f"{names} tanımlı değil — görsel üretilemez")

    def _decode(self, encoded: str, *, model: str) -> bytes:
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageResponseParsingError(
                f"Görsel base64 olarak çözülemedi (model={model}): {exc}"
            ) from exc

    def _write(self, image_bytes: bytes, extension: str) -> Path:
        if not image_bytes:
            raise ImageResponseParsingError("Sağlayıcı boş bir görsel döndürdü")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._output_dir / f"{uuid.uuid4().hex}.{extension}"
        file_path.write_bytes(image_bytes)
        return file_path

    @staticmethod
    def _extension_for(media_type: object) -> str:
        return _MEDIA_TYPE_EXTENSIONS.get(str(media_type), _DEFAULT_EXTENSION)

    def _download(self, url: str, *, model: str) -> bytes:
        """Sağlayıcı base64 yerine geçici bir URL döndürdüğünde kullanılır (Replicate
        her zaman, OpenRouter bazı modellerde)."""
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


# ------------------------------------------------------------------- Google AI Studio


class GoogleAIStudioImageProvider(_HttpImageProvider):
    """Google AI Studio (Gemini API) görsel üretimi.

    Anahtar **query parametresi** (`?key=`) ile gönderilir, `x-goog-api-key` başlığıyla
    değil: Google'ın yeni `AQ.`-önekli anahtar formatı başlık yöntemiyle bu endpoint'te
    `403 PERMISSION_DENIED` döndürüyor, query parametresi ise her iki anahtar formatıyla
    da çalışıyor.
    """

    name = "google-ai-studio"
    default_api_key_env = "GEMINI_API_KEY"
    fallback_api_key_env = "GOOGLE_API_KEY"

    def __init__(
        self,
        *,
        output_dir: Path,
        api_key: str | None = None,
        base_url: str = GOOGLE_BASE_URL,
        timeout_seconds: float = 180.0,
        aspect_ratio: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            output_dir=output_dir,
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            client=client,
            headers={"Content-Type": "application/json"},
        )
        self._aspect_ratio = aspect_ratio

    def generate(self, request: ImageRequest) -> ImageResult:
        self._require_api_key()
        model = _strip_vendor_prefix(request.model)

        generation_config: dict[str, object] = {"responseModalities": ["IMAGE"]}
        aspect_ratio = _aspect_ratio_from_size(request.size) or self._aspect_ratio
        if aspect_ratio:
            generation_config["imageConfig"] = {"aspectRatio": aspect_ratio}

        payload = {
            "contents": [{"parts": [{"text": request.prompt}]}],
            "generationConfig": generation_config,
        }

        self._logger.info(f"image_generate model={model} aspect_ratio={aspect_ratio}")
        response = self._post(f"/models/{model}:generateContent", payload, model=model)
        image_bytes, extension = self._extract_image(response.json(), model=model)
        file_path = self._write(image_bytes, extension)

        self._logger.info(f"image_generate_ok model={model} path={file_path}")
        return ImageResult(file_path=str(file_path), provider=self.name, model=model)

    def health_check(self) -> bool:
        """Asla exception fırlatmaz. Model listesi ücretsizdir — kota tüketmez."""
        if not self._api_key:
            self._logger.warning(f"health_check: {self.default_api_key_env} tanımlı değil")
            return False
        try:
            response = self._client.get("/models", params={"key": self._api_key})
            return response.status_code == 200
        except httpx.HTTPError as exc:
            self._logger.warning(f"health_check başarısız: {exc}")
            return False

    def _post(self, path: str, payload: dict[str, object], *, model: str) -> httpx.Response:
        try:
            response = self._client.post(path, params={"key": self._api_key}, json=payload)
        except httpx.TimeoutException as exc:
            raise ImageProviderUnavailableError(
                f"Görsel üretimi zaman aşımına uğradı (model={model})"
            ) from exc
        except httpx.ConnectError as exc:
            raise ImageProviderUnavailableError(f"Gemini API'ye bağlanılamadı: {exc}") from exc
        _raise_for_google_status(response, model=model)
        return response

    def _extract_image(self, data: object, *, model: str) -> tuple[bytes, str]:
        if not isinstance(data, dict):
            raise ImageResponseParsingError(f"Beklenmeyen yanıt tipi (model={model}): {type(data)}")

        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            # Prompt güvenlik filtresine takıldıysa candidates hiç dönmez, yalnızca
            # promptFeedback döner — bu yüzden ayrı ve okunur bir mesaj veriyoruz.
            feedback = data.get("promptFeedback")
            raise ImageInvalidRequestError(
                f"Model görsel döndürmedi (model={model}). promptFeedback={feedback}"
            )

        candidate = candidates[0] if isinstance(candidates[0], dict) else {}
        parts = (candidate.get("content") or {}).get("parts")
        for part in parts if isinstance(parts, list) else []:
            inline = part.get("inlineData") if isinstance(part, dict) else None
            if isinstance(inline, dict) and inline.get("data"):
                extension = self._extension_for(inline.get("mimeType"))
                return self._decode(str(inline["data"]), model=model), extension

        raise ImageInvalidRequestError(
            f"Yanıtta görsel verisi yok (model={model}). "
            f"finishReason={candidate.get('finishReason')} — istem güvenlik filtresine "
            f"takılmış olabilir; aynı istemi yeniden denemek yardımcı olmaz."
        )


def _strip_vendor_prefix(model: str) -> str:
    """`google/gemini-2.5-flash-image` -> `gemini-2.5-flash-image`.

    OpenRouter `saglayici/model` biçimini kullanır, Gemini API ise çıplak model adını.
    Config yanlışlıkla OpenRouter biçimini taşıyorsa istek sessizce 404 olmasın diye
    önek burada temizlenir."""
    return model.split("/", 1)[1] if "/" in model else model


def _raise_for_google_status(response: httpx.Response, *, model: str) -> None:
    status = response.status_code
    if status < 400:
        return
    detail = response.text[:500]
    if status in (401, 403):
        raise ImageAuthenticationError(
            f"Gemini API kimlik doğrulama/izin hatası ({status}, model={model}): {detail}"
        )
    if status == 429:
        # Gemini'de 429 hem "çok hızlı istek" hem "bu model için kotan 0" anlamına
        # gelebilir; ikincisinde yeniden denemek işe yaramaz, bu yüzden sağlayıcı
        # mesajını olduğu gibi taşıyoruz (limit: 0 ifadesi orada görünür).
        raise ImageRateLimitError(f"Gemini API kota/rate limit (model={model}): {detail}")
    if status in (400, 404, 422):
        raise ImageInvalidRequestError(
            f"Geçersiz görsel isteği ({status}, model={model}): {detail}"
        )
    raise ImageProviderUnavailableError(f"Gemini API hatası ({status}, model={model}): {detail}")


# ------------------------------------------------------------------------- OpenRouter


class OpenRouterImageProvider(_HttpImageProvider):
    name = "openrouter"

    default_api_key_env = "IMAGE_API_KEY"
    fallback_api_key_env = "OPENROUTER_API_KEY"
    """`IMAGE_API_KEY` tanımlı değilse OpenRouter'ın kendi anahtarına düşülür: görsel de
    metin de aynı hesap üzerinden faturalanır, ayrı bir anahtar tutmak zorunlu değildir."""

    def __init__(
        self,
        *,
        output_dir: Path,
        api_key: str | None = None,
        base_url: str = OPENROUTER_BASE_URL,
        timeout_seconds: float = 180.0,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        client: httpx.Client | None = None,
        app_title: str = "Content Factory",
    ) -> None:
        resolved_key = api_key if api_key is not None else self._api_key_from_env()
        headers = {"Content-Type": "application/json", "X-Title": app_title}
        if resolved_key:
            headers["Authorization"] = f"Bearer {resolved_key}"
        super().__init__(
            output_dir=output_dir,
            api_key=resolved_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            client=client,
            headers=headers,
        )
        self._aspect_ratio = aspect_ratio
        self._resolution = resolution

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
        _raise_for_openrouter_status(response, model=model)
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

        extension = self._extension_for(entry.get("media_type"))

        encoded = entry.get("b64_json")
        if isinstance(encoded, str) and encoded:
            return self._decode(encoded, model=model), extension

        url = entry.get("url")
        if isinstance(url, str) and url:
            return self._download(url, model=model), extension

        raise ImageResponseParsingError(
            f"Görsel kaydında ne `b64_json` ne `url` var (model={model}): {entry}"
        )


def _raise_for_openrouter_status(response: httpx.Response, *, model: str) -> None:
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


# --------------------------------------------------------------------------- Replicate


class ReplicateImageProvider(_HttpImageProvider):
    """Replicate görsel üretimi.

    Diğer iki sağlayıcıdan iki noktada ayrılır:

    1. **Sürüm çözümlemesi.** İstek gövdesinde model adı değil, modelin bir sürümünün
       kimliği gider. Sürüm kimliği koda gömülmez — her üretimde
       `GET /models/{owner}/{name}` ile güncel sürüm okunur, böylece model güncellendiğinde
       config'e dokunmak gerekmez. (Dokümanlarda geçen kısayol uç nokta
       `POST /models/{owner}/{name}/predictions`, denenen modelde
       `404 {"detail":"No adapter found for model"}` döndürdüğü için kullanılmıyor.)
    2. **Asenkron sonuç.** Üretim bir "prediction" kaydı yaratır. `Prefer: wait` başlığı
       çoğu istekte sonucu tek turda getirir; getirmezse `urls.get` yoklanır. Çıktı base64
       değil, geçici bir URL'dir; dosya ayrıca indirilir.
    """

    name = "replicate"
    default_api_key_env = "REPLICATE_API_KEY"
    fallback_api_key_env = "REPLICATE_API_TOKEN"

    _TERMINAL_STATUSES = ("succeeded", "failed", "canceled")

    def __init__(
        self,
        *,
        output_dir: Path,
        api_key: str | None = None,
        base_url: str = REPLICATE_BASE_URL,
        timeout_seconds: float = 180.0,
        aspect_ratio: str | None = None,
        output_format: str = "webp",
        poll_interval_seconds: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else self._api_key_from_env()
        headers = {"Content-Type": "application/json"}
        if resolved_key:
            headers["Authorization"] = f"Bearer {resolved_key}"
        super().__init__(
            output_dir=output_dir,
            api_key=resolved_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            client=client,
            headers=headers,
        )
        self._aspect_ratio = aspect_ratio
        self._output_format = output_format
        self._poll_interval = poll_interval_seconds
        self._sleep_fn = sleep_fn
        self._timeout_seconds = timeout_seconds

    def generate(self, request: ImageRequest) -> ImageResult:
        self._require_api_key()
        model = request.model
        version = self._latest_version(model)

        payload: dict[str, object] = {
            "version": version,
            "input": {
                "prompt": request.prompt,
                "num_outputs": 1,
                "output_format": self._output_format,
            },
        }
        aspect_ratio = _aspect_ratio_from_size(request.size) or self._aspect_ratio
        if aspect_ratio:
            payload["input"]["aspect_ratio"] = aspect_ratio  # type: ignore[index]

        self._logger.info(
            f"image_generate model={model} version={version[:12]} aspect_ratio={aspect_ratio}"
        )
        response = self._request("POST", "/predictions", model=model, json=payload)
        prediction = self._await_completion(response.json(), model=model)

        image_url = _first_output_url(prediction.get("output"))
        if not image_url:
            raise ImageResponseParsingError(
                f"Yanıtta görsel URL'si yok (model={model}): output={prediction.get('output')!r}"
            )

        extension = image_url.rsplit(".", 1)[-1].lower()
        if extension not in _MEDIA_TYPE_EXTENSIONS.values():
            extension = self._output_format
        file_path = self._write(self._download(image_url, model=model), extension)

        self._logger.info(f"image_generate_ok model={model} path={file_path}")
        return ImageResult(file_path=str(file_path), provider=self.name, model=model)

    def health_check(self) -> bool:
        """Asla exception fırlatmaz. `/account` ücretsizdir — kredi harcamaz."""
        if not self._api_key:
            self._logger.warning(
                f"health_check: {self.default_api_key_env}/{self.fallback_api_key_env} "
                f"tanımlı değil"
            )
            return False
        try:
            return self._client.get("/account").status_code == 200
        except httpx.HTTPError as exc:
            self._logger.warning(f"health_check başarısız: {exc}")
            return False

    def _latest_version(self, model: str) -> str:
        response = self._request("GET", f"/models/{model}", model=model)
        version = ((response.json().get("latest_version") or {}).get("id")) or ""
        if not version:
            raise ImageResponseParsingError(
                f"Modelin güncel sürümü okunamadı (model={model}) — `latest_version.id` yok"
            )
        return str(version)

    def _await_completion(self, prediction: dict[str, object], *, model: str) -> dict[str, object]:
        """`Prefer: wait` sonucu getirmediyse tahmin bitene kadar yoklar."""
        deadline = time.monotonic() + self._timeout_seconds
        while str(prediction.get("status")) not in self._TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                raise ImageProviderUnavailableError(
                    f"Görsel üretimi zaman aşımına uğradı (model={model}, "
                    f"status={prediction.get('status')})"
                )
            self._sleep_fn(self._poll_interval)
            get_url = (prediction.get("urls") or {}).get("get")  # type: ignore[union-attr]
            path = str(get_url) if get_url else f"/predictions/{prediction.get('id')}"
            prediction = self._request("GET", path, model=model).json()
            self._logger.info(
                f"image_generate_poll model={model} status={prediction.get('status')}"
            )

        status = str(prediction.get("status"))
        if status != "succeeded":
            raise ImageInvalidRequestError(
                f"Görsel üretimi başarısız (model={model}, status={status}): "
                f"{prediction.get('error')}"
            )
        return prediction

    def _request(
        self, method: str, path: str, *, model: str, json: dict[str, object] | None = None
    ) -> httpx.Response:
        # `Prefer: wait` yalnızca üretim isteğinde anlamlı: sonuç hazırsa aynı yanıtta gelir.
        headers = {"Prefer": "wait"} if method == "POST" else None
        try:
            response = self._client.request(method, path, json=json, headers=headers)
        except httpx.TimeoutException as exc:
            raise ImageProviderUnavailableError(
                f"Görsel üretimi zaman aşımına uğradı (model={model})"
            ) from exc
        except httpx.ConnectError as exc:
            raise ImageProviderUnavailableError(f"Replicate'e bağlanılamadı: {exc}") from exc
        _raise_for_replicate_status(response, model=model)
        return response


def _first_output_url(output: object) -> str | None:
    """Modeller çıktıyı tek bir URL ya da URL listesi olarak döndürür."""
    if isinstance(output, str):
        return output or None
    if isinstance(output, list):
        for entry in output:
            if isinstance(entry, str) and entry:
                return entry
    return None


def _raise_for_replicate_status(response: httpx.Response, *, model: str) -> None:
    status = response.status_code
    if status < 400:
        return
    detail = response.text[:500]
    if status in (401, 403):
        raise ImageAuthenticationError(
            f"Replicate kimlik doğrulama hatası ({status}, model={model}): {detail}"
        )
    if status == 402:
        raise ImageInsufficientCreditError(
            f"Replicate bakiyesi görsel üretimi için yetersiz (model={model}): {detail}"
        )
    if status == 429:
        raise ImageRateLimitError(f"Replicate rate limit (model={model}): {detail}")
    if status in (400, 404, 422):
        raise ImageInvalidRequestError(
            f"Geçersiz görsel isteği ({status}, model={model}): {detail}. "
            f"Model adı `sahip/model` biçiminde mi ve parametreler bu modelde destekleniyor mu? "
            f"config/models.yaml: agents.image_generator alanlarını kontrol edin."
        )
    raise ImageProviderUnavailableError(f"Replicate görsel hatası ({status}, model={model})")


# ---------------------------------------------------------------------------- ortak


def _aspect_ratio_from_size(size: tuple[int, int] | None) -> str | None:
    """(1600, 900) -> "16:9". Her iki sağlayıcı da piksel boyutu değil, en-boy oranı
    kabul eder."""
    if size is None:
        return None
    width, height = size
    if width <= 0 or height <= 0:
        return None
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


# ------------------------------------------------------------------------------- factory

_REGISTRY: dict[str, type[ImageProvider]] = {
    "replicate": ReplicateImageProvider,
    "google-ai-studio": GoogleAIStudioImageProvider,
    "openrouter": OpenRouterImageProvider,
}


def register_image_provider(name: str, provider_cls: type[ImageProvider]) -> None:
    """Yeni bir görsel sağlayıcıyı kaydeder (ör. `replicate-flux`). Kaydedildikten sonra
    `config/models.yaml: agents.image_generator.provider` bu adı kullanabilir; hiçbir
    agent kodu değişmez."""
    _REGISTRY[name] = provider_cls


def available_image_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def create_image_provider(settings: Settings, *, output_dir: Path) -> ImageProvider:
    """`config/models.yaml: agents.image_generator` bölümünden görsel sağlayıcıyı inşa eder.

    LLM tarafındaki gibi ayrı bir `factory.py` modülü yoktur: görsel katmanında sarmalanacak
    bir retry/cache zinciri olmadığı için factory somut sınıfların yanında duruyor
    (bkz. `providers/llm/factory.py` — oradaki ayrımın gerekçesi katman sayısıdır)."""
    config = settings.models.for_agent("image_generator")
    provider_name = config.provider or settings.models.default_provider
    provider_cls = _REGISTRY.get(provider_name)
    if provider_cls is None:
        raise ImageInvalidRequestError(
            f"Bilinmeyen görsel sağlayıcı: {provider_name!r} "
            f"(kayıtlı: {available_image_providers()})"
        )

    timeout_seconds = float(settings.engine.timeouts.image_generation_seconds)
    if provider_cls is ReplicateImageProvider:
        return ReplicateImageProvider(
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            aspect_ratio=config.aspect_ratio,
        )
    if provider_cls is GoogleAIStudioImageProvider:
        return GoogleAIStudioImageProvider(
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            aspect_ratio=config.aspect_ratio,
        )
    if provider_cls is OpenRouterImageProvider:
        return OpenRouterImageProvider(
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            aspect_ratio=config.aspect_ratio,
            resolution=config.resolution,
        )
    return provider_cls()  # type: ignore[call-arg]  # register_image_provider ile eklenenler
