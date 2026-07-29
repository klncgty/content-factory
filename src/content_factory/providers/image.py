"""Görsel üretim sağlayıcı arayüzü.

`LLMProvider`'dan kasıtlı olarak ayrıdır: görsel üretim ayrı bir endpoint ve ayrı bir
istek/yanıt sözleşmesi kullanır, dolayısıyla `BaseLLMProvider`'ın retry/cache/token
sayımı katmanları buraya uymaz — bkz. ARCHITECTURE.md §9. Somut implementasyon
`integrations/image_client.py` içindedir (`OpenRouterImageProvider`); agent kodu hangi
sağlayıcının kullanıldığını bilmez, yalnızca bu arayüzü görür.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ImageRequest(BaseModel):
    prompt: str
    model: str
    size: tuple[int, int] | None = None
    """İstenen en-boy oranının kaynağı. Somut sağlayıcı bunu kendi API'sinin beklediği
    biçime çevirir (ör. OpenRouter'da `aspect_ratio: "16:9"`). `None` ise sağlayıcının
    yapılandırılmış varsayılanı kullanılır."""


class ImageResult(BaseModel):
    file_path: str
    provider: str
    model: str


class ImageProviderError(Exception):
    """Görsel sağlayıcı katmanının tüm hatalarının temel sınıfı.

    `AgentError` hiyerarşisinden ayrıdır (bkz. `domain/exceptions.py`): bu katman
    ağ/sağlayıcı hatalarını temsil eder. Orchestrator bu hatayı yakalar ve makaleyi
    görselsiz yayınlar — görsel bir zenginleştirmedir, yayın önkoşulu değildir."""


class ImageAuthenticationError(ImageProviderError):
    """API anahtarı tanımsız veya geçersiz."""


class ImageInsufficientCreditError(ImageProviderError):
    """Sağlayıcı bakiyesi yetersiz. Yeniden denemek anlamsızdır."""


class ImageRateLimitError(ImageProviderError):
    """Sağlayıcı rate limit uyguladı."""


class ImageInvalidRequestError(ImageProviderError):
    """İstek sağlayıcı tarafından reddedildi (geçersiz model, desteklenmeyen parametre)."""


class ImageProviderUnavailableError(ImageProviderError):
    """Sağlayıcıya ulaşılamadı, zaman aşımı veya 5xx."""


class ImageResponseParsingError(ImageProviderError):
    """Yanıt başarılı döndü ama içinden görsel verisi çıkarılamadı."""


class ImageProvider(ABC):
    @abstractmethod
    def generate(self, request: ImageRequest) -> ImageResult:
        """Tek bir temel görsel üretir ve diske yazar; dönen `ImageResult.file_path`
        o dosyayı gösterir. Türevler (cover/thumbnail/og-image) `image_processing`
        katmanında resize ile üretilir, burada değil."""
        raise NotImplementedError
