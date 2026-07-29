from __future__ import annotations

from pathlib import Path

from content_factory.providers.image import ImageProvider, ImageRequest, ImageResult


class StubImageProvider(ImageProvider):
    """Gerçek bir görsel API'sine bağlanmadan, önceden hazırlanmış bir test görselinin
    yolunu döndürür — `ImageGeneratorAgent`'ın türev üretim (resize/crop) mantığını
    gerçek bir görsel dosyasıyla uçtan uca test edebilmek için."""

    def __init__(self, *, image_path: Path) -> None:
        self._image_path = image_path
        self.requests: list[ImageRequest] = []

    def generate(self, request: ImageRequest) -> ImageResult:
        self.requests.append(request)
        return ImageResult(file_path=str(self._image_path), provider="stub", model=request.model)
