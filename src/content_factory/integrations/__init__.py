"""`content_factory.providers` altındaki soyut arayüzlerin somut implementasyonları
(bkz. ARCHITECTURE.md §11):

- `image_client.py` — `ImageProvider` -> `OpenRouterImageProvider` (POST /api/v1/images)
- `git_ops.py` — `GitProvider` -> `LocalGitProvider` (`git`/`gh` subprocess)
- `image_processing.py` — dış API çağırmaz; Pillow ile türev görsel üretimi

`LLMProvider`'ın implementasyonu istisnadır ve `providers/llm/openrouter.py` içinde
yaşar: o katman retry/cache/rate-limit/token sayımı gibi kendi altyapısını taşıdığı için
ayrı bir alt paket olarak modellendi (bkz. `providers/llm/README.md`).
"""
