"""Replicate ile görsel üretimini elle denemek için tek dosyalık deneme script'i.

Henüz projeye BAĞLANMADI (ImageProvider implementasyonu değil) — amacı, anahtarın ve
API sözleşmesinin çalıştığını doğrulamak ve örnek bir görsel bırakmak.

Çalıştırma:
    uv run python scripts/try_replicate.py
    uv run python scripts/try_replicate.py "kendi prompt'un"

Kimlik bilgisi (.env):
    REPLICATE_API_KEY=r8_...        # REPLICATE_API_TOKEN adı da kabul edilir

Sözleşme:
    base   : https://api.replicate.com/v1
    auth   : Authorization: Bearer <token>
    sürüm  : GET  /models/{owner}/{name}      -> latest_version.id
    üretim : POST /predictions                gövde: {"version": <id>, "input": {...}}
             `Prefer: wait` başlığıyla istek, tahmin bitene kadar (60 sn'ye dek) bekler;
             o süre yetmezse `urls.get` üzerinden yoklamaya (polling) düşülür.
    çıktı  : prediction.output -> görsel URL'si (model bir dizi de döndürebilir)

Not: dokümanlarda geçen kısayol uç nokta (POST /models/{owner}/{name}/predictions) bu
model için `404 {"detail":"No adapter found for model"}` döndürüyor; çalışan yol,
sürüm kimliğiyle /predictions'a göndermek.

Tek görsel üretir ve proje kökündeki `example images/` klasörüne yazar.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE_URL = "https://api.replicate.com/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "example images"

# flux-schnell: en hızlı/en ucuz uçtan uca deneme seçeneği (görsel başına ~0.003 USD).
MODEL = "black-forest-labs/flux-schnell"

POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 180

DEFAULT_PROMPT = (
    "Rustic kitchen still life: a bottle of cold-pressed olive oil and an olive wood "
    "cutting board on a linen cloth, warm natural window light, shallow depth of field, "
    "editorial food photography"
)


def _token() -> str:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    for name in ("REPLICATE_API_KEY", "REPLICATE_API_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    sys.exit("REPLICATE_API_KEY tanımlı değil (.env).")


def _extract_image_url(output: object) -> str | None:
    """Modeller çıktıyı ya tek bir URL ya da URL listesi olarak döndürür."""
    if isinstance(output, str):
        return output
    if isinstance(output, list) and output:
        first = output[0]
        return first if isinstance(first, str) else None
    return None


def main() -> int:
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT
    client = httpx.Client(
        base_url=BASE_URL,
        timeout=120,
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
    )

    # Sürüm kimliği koda gömülmez: modelin güncel sürümü çalışma anında sorulur.
    model_response = client.get(f"/models/{MODEL}")
    print(f"[model] GET /models/{MODEL} -> {model_response.status_code}")
    if model_response.status_code >= 400:
        print(f"[model] hata gövdesi: {model_response.text[:400]}")
        return 1
    version = ((model_response.json().get("latest_version") or {}).get("id")) or ""
    if not version:
        print("[model] latest_version.id alınamadı")
        return 1
    print(f"[model] sürüm: {version[:12]}…")

    payload = {
        "version": version,
        "input": {
            "prompt": prompt,
            "aspect_ratio": "16:9",  # projedeki cover/og türevleri 16:9 tabanlı
            "num_outputs": 1,
            "output_format": "webp",
            "output_quality": 90,
        },
    }
    response = client.post(
        "/predictions",
        json=payload,
        headers={"Prefer": "wait"},  # tahmin biterse yanıtı doğrudan döndür
    )
    print(f"[submit] POST /predictions -> {response.status_code}")
    if response.status_code >= 400:
        print(f"[submit] hata gövdesi: {response.text[:600]}")
        return 1

    prediction = response.json()
    print(f"[submit] id={prediction.get('id')} status={prediction.get('status')}")

    # `Prefer: wait` 60 sn'de bitmezse tahmin hâlâ sırada/işlemede olabilir; yokla.
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while prediction.get("status") in ("starting", "processing") and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        get_url = (prediction.get("urls") or {}).get("get")
        poll = client.get(get_url) if get_url else client.get(f"/predictions/{prediction['id']}")
        if poll.status_code >= 400:
            print(f"[poll] hata {poll.status_code}: {poll.text[:300]}")
            return 1
        prediction = poll.json()
        print(f"[poll] status={prediction.get('status')}")

    if prediction.get("status") != "succeeded":
        print(f"[sonuç] tahmin tamamlanmadı: status={prediction.get('status')}")
        print(f"[sonuç] hata: {prediction.get('error')}")
        return 1

    image_url = _extract_image_url(prediction.get("output"))
    if not image_url:
        print(f"[sonuç] çıktıda görsel URL'si bulunamadı: {prediction.get('output')!r}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"replicate-{prediction['id']}.webp"
    output_path.write_bytes(httpx.get(image_url, timeout=120, follow_redirects=True).content)

    metrics = prediction.get("metrics") or {}
    print(f"[sonuç] {image_url}")
    print(f"[sonuç] süre: {metrics.get('predict_time')} sn")
    print(f"[sonuç] kaydedildi: {output_path} ({output_path.stat().st_size // 1024} KB)")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
