"""Higgsfield görsel üretimini elle denemek için tek dosyalık deneme script'i.

Henüz projeye BAĞLANMADI (ImageProvider implementasyonu değil) — amacı, kimlik
bilgilerinin ve API sözleşmesinin çalıştığını doğrulamak.

Çalıştırma:
    uv run python scripts/try_higgsfield.py
    uv run python scripts/try_higgsfield.py "kendi prompt'un"

Kimlik bilgileri (.env): Higgsfield İKİ değer ister — anahtar kimliği ve secret.
    HIGGSFIELD_API_KEY_ID=...       # anahtar kimliği (hf-api-key), UUID biçiminde
    HIGGSFIELD_API_KEY_SECRET=...   # secret (hf-secret), 64 karakterlik hex
`HIGGSFIELD_API_KEY` / `HIGGSFIELD_API_SECRET` adları da kabul edilir; tek satırlık
birleşik biçim de olur: HIGGSFIELD_KEY=anahtar:secret

API'nin doğruladığı biçimler deneyerek saptandı: `hf-api-key` UUID değilse istek 422
("Input should be a valid UUID") döner; secret'ı tek başına göndermek 401 verir.

Sözleşme (higgsfield-js SDK kaynağından):
    base   : https://platform.higgsfield.ai
    auth   : hf-api-key + hf-secret başlıkları
    üretim : POST /v1/text2image/soul   gövde: {"params": {...}}
    durum  : GET  /v1/job-sets/{id}     -> jobs[].status / jobs[].results.raw.url
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

BASE_URL = "https://platform.higgsfield.ai"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "state" / "higgsfield_deneme"
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 180

DEFAULT_PROMPT = (
    "Rustic kitchen still life: a bottle of cold-pressed olive oil and an olive wood "
    "cutting board on a linen cloth, warm natural window light, shallow depth of field, "
    "editorial food photography"
)


def _credentials() -> tuple[str, str]:
    """(api_key, secret) döndürür. Eksikse ne yapılacağını söyleyip çıkar."""
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    combined = os.environ.get("HIGGSFIELD_KEY") or os.environ.get("HF_KEY")
    if combined and combined.count(":") == 1:
        api_key, secret = combined.split(":")
        return api_key.strip(), secret.strip()

    api_key = _first_env("HIGGSFIELD_API_KEY_ID", "HIGGSFIELD_API_KEY")
    secret = _first_env("HIGGSFIELD_API_KEY_SECRET", "HIGGSFIELD_API_SECRET")

    # Tek bir değer varsa hangisi olduğunu biçiminden anlayabiliyoruz: anahtar kimliği
    # UUID, secret ise uzun bir hex dizisi. Yanlış alana yazılmış bir secret'ı sessizce
    # göndermek API'den anlaşılmaz bir 422 aldırıyordu.
    if api_key and not secret and not _looks_like_uuid(api_key):
        secret, api_key = api_key, ""

    if not api_key or not secret:
        eksik = "HIGGSFIELD_API_KEY (anahtar kimliği, UUID)" if not api_key else (
            "HIGGSFIELD_API_SECRET (secret)"
        )
        sys.exit(
            f"Eksik kimlik bilgisi: {eksik}\n"
            "Higgsfield her istekte iki değer ister:\n"
            "  hf-api-key -> anahtar kimliği, UUID biçiminde (ör. 3f8b...-...)\n"
            "  hf-secret  -> secret, 64 karakterlik hex\n"
            "cloud.higgsfield.ai > API keys sayfasından ikisini de alıp .env'e yazın:\n"
            "  HIGGSFIELD_API_KEY=<uuid>\n"
            "  HIGGSFIELD_API_SECRET=<hex>\n"
            "(veya tek satırda: HIGGSFIELD_KEY=<uuid>:<hex>)"
        )
    return api_key, secret


def _first_env(*names: str) -> str:
    """İlk tanımlı çevre değişkenini döndürür — aynı değer için birden fazla isim
    dolaşımda (HIGGSFIELD_API_KEY_ID / HIGGSFIELD_API_KEY)."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def main() -> int:
    api_key, secret = _credentials()
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    client = httpx.Client(
        base_url=BASE_URL,
        timeout=60,
        headers={"hf-api-key": api_key, "hf-secret": secret},
    )

    # 1) Kimlik doğrulamayı ucuz bir GET ile dene — üretim kotası harcamadan.
    probe = client.get("/v1/text2image/soul-styles")
    print(f"[auth] GET /v1/text2image/soul-styles -> {probe.status_code}")
    if probe.status_code in (401, 403):
        print(f"[auth] kimlik bilgileri reddedildi: {probe.text[:300]}")
        return 1

    # 2) Görsel üretimini başlat.
    payload = {
        "params": {
            "prompt": prompt,
            "width_and_height": "1536x1536",
            "quality": "1080p",
            "batch_size": 1,
        }
    }
    response = client.post("/v1/text2image/soul", json=payload)
    print(f"[submit] POST /v1/text2image/soul -> {response.status_code}")
    if response.status_code >= 400:
        print(f"[submit] hata gövdesi: {response.text[:600]}")
        if response.status_code == 403 and "credit" in response.text.lower():
            print(
                "[submit] Kimlik bilgileri GEÇERLİ (auth adımı 200 döndü); eksik olan "
                "hesap bakiyesi. cloud.higgsfield.ai üzerinden kredi yükleyin."
            )
        return 1

    job_set = response.json()
    job_set_id = job_set.get("id")
    print(f"[submit] job_set_id={job_set_id}")

    # 3) Bitene kadar durumu sor.
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    image_url: str | None = None
    while time.monotonic() < deadline:
        status_response = client.get(f"/v1/job-sets/{job_set_id}")
        if status_response.status_code >= 400:
            print(f"[poll] hata {status_response.status_code}: {status_response.text[:300]}")
            return 1
        jobs = status_response.json().get("jobs", [])
        statuses = [job.get("status") for job in jobs]
        print(f"[poll] {statuses}")
        if any(status in ("completed", "failed", "nsfw", "canceled") for status in statuses):
            for job in jobs:
                results = job.get("results") or {}
                raw = results.get("raw") or {}
                if raw.get("url"):
                    image_url = raw["url"]
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if not image_url:
        print("[sonuç] görsel URL'si alınamadı (zaman aşımı veya başarısız iş)")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{job_set_id}.jpg"
    output_path.write_bytes(httpx.get(image_url, timeout=120, follow_redirects=True).content)
    print(f"[sonuç] {image_url}")
    print(f"[sonuç] kaydedildi: {output_path} ({output_path.stat().st_size // 1024} KB)")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
