"""Tek bir temel görselden `cover`/`thumbnail`/`og-image` türevlerini üretir
(bkz. ARCHITECTURE.md §7 — neden 3 ayrı üretim değil de tek üretim + resize).

Yalnızca `ImageGeneratorAgent` bu modülü kullanır. Boyutlar `config/engine.yaml:
image_derivatives`'ten gelir — burada hiçbir boyut hardcode edilmez.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from content_factory.settings.schemas import ImageDerivativeSpec
from content_factory.utils.logging import get_logger

_logger = get_logger("integrations.image_processing")


def derive_image_variants(
    base_image_path: Path,
    *,
    output_dir: Path,
    derivatives: dict[str, ImageDerivativeSpec],
) -> dict[str, Path]:
    """`base_image_path`'teki görselden `derivatives`'te tanımlı her türevi
    (crop-to-fit + resize) üretir, `output_dir/{isim}.{format}` olarak kaydeder."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(base_image_path) as base:
        base = base.convert("RGB")
        _warn_if_upscaling(base.size, derivatives)
        results: dict[str, Path] = {}
        for name, spec in derivatives.items():
            resized = _cover_crop_resize(base, spec.size)
            is_jpeg = spec.format.lower() in ("jpg", "jpeg")
            output_format = "JPEG" if is_jpeg else spec.format.upper()
            output_path = output_dir / f"{name}.{spec.format}"
            resized.save(output_path, format=output_format)
            results[name] = output_path
    return results


def _warn_if_upscaling(
    base_size: tuple[int, int], derivatives: dict[str, ImageDerivativeSpec]
) -> None:
    """Temel görsel en büyük türevden küçükse büyütme (upscale) yapılır ve kapak
    görseli bulanıklaşır. Sessizce olmasın diye uyarılır: çözüm, `config/models.yaml`
    içinde daha yüksek çözünürlüklü bir görsel modeli seçmektir."""
    base_w, base_h = base_size
    for name, spec in derivatives.items():
        target_w, target_h = spec.size
        if target_w > base_w or target_h > base_h:
            _logger.warning(
                f"temel görsel ({base_w}x{base_h}) '{name}' türevinden "
                f"({target_w}x{target_h}) küçük — büyütülerek üretilecek, keskinlik düşebilir"
            )


def _cover_crop_resize(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """CSS `object-fit: cover` ile aynı mantık: hedef en-boy oranına göre ortadan
    kırpar, sonra tam boyuta ölçekler — kenarlarda boşluk/deforme olmadan."""
    target_w, target_h = target_size
    src_w, src_h = image.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = round(src_h * target_ratio)
        left = (src_w - new_w) // 2
        box = (left, 0, left + new_w, src_h)
    else:
        new_h = round(src_w / target_ratio)
        top = (src_h - new_h) // 2
        box = (0, top, src_w, top + new_h)

    return image.crop(box).resize(target_size, Image.LANCZOS)
