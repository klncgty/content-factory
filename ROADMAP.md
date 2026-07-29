# Geliştirme Roadmap (v2)

Mimari detaylar için bkz. `ARCHITECTURE.md`. Roadmap implementasyon sırasını ve
bağımlılıkları tanımlar. Her faz bir öncekinin çalışır durumda olmasını varsayar.

## Faz 0 — Temel Kurulum & Sözleşmeler

- [x] Proje iskeleti, `brands/` + engine `config/` ayrımı
- [x] `brands/oleart/scope.yaml` — içerik kapsamı allowlist'i (kesinleşti, kullanıcı onaylı)
- [x] `pyproject.toml` + `uv` ile Python proje altyapısı (src layout, `uv sync`/`uv run`)
- [x] Knowledge Base sistemi: `knowledge/brands/oleart/*.md` (16 dosya) + `KnowledgeLoader`/
      `BrandKnowledge` (tip güvenli API, cache, `validate()`) — bkz. `knowledge/README.md`
- [x] `knowledge/brands/oleart/*.md` dosyalarının **gerçek içerikle** doldurulması —
      16/16 dosya dolu, `KnowledgeLoader.validate("oleart")` artık placeholder
      raporlamıyor (`tests/test_knowledge.py` regresyon bekçisi). Marka bilgisi
      oleart.co'dan, teknik bilgi TGK/IOC/AB 29/2012 gibi otoritelerden alındı.
      **Marka sahibinden teyit bekleyenler** (hasat bölgesi/çeşidi, sıkım süreci,
      sertifika durumu, ahşap ürün detayları) uydurulmadı; ilgili dosyalarda
      "Doğrulanması Gereken" başlığı altında açık kısıt olarak duruyor
- [ ] `brands/oleart/brand.yaml` içindeki yasaklı kelime/iddia listesinin hukuki gözden
      geçirmeden geçmesi
- [ ] **Blocker:** oleart.co'nun `content/blog/*.md` + `public/blog/images/` yayın
      sözleşmesini (bkz. `ARCHITECTURE.md` §6) okuyup render edebilecek bir yapıya geçmesi —
      **tamamlandı** (oleart.co reposunda `scripts/build-blog.mjs` ile), bu maddeyi
      artık bloke etmiyor.
- [x] OpenRouter hesabı + `OPENROUTER_API_KEY` (`.env`'de tanımlı, `/images/models`
      çağrısıyla doğrulandı; görsel modeli `google/gemini-2.5-flash-image` hesapta mevcut)
- [ ] `config/models.yaml` ilk model seçimlerinin **maliyet/kalite testiyle** doğrulanması
      (ilk makaleler üretildikten sonra)

## Faz 1 — Çekirdek Pipeline (PR modu, tek marka: oleart)

- [x] `StateStore` arayüzü + `SQLiteStateStore` implementasyonu (articles/keywords/
      topics_backlog/internal_links/runs/scope_rejections)
- [x] `BaseAgent` + `AgentContext` (DI) + agent iskeletleri
- [x] `Orchestrator`: gerçek sıralı çağırma (Topic→Research→Strategist→Writer→SEO→Linker→
      Image→Editor→Publisher→Git)
- [x] `ScopeGuard.pre_check` (deterministik keyword match) implemente ve test edildi
- [x] LLM provider katmanı: `BaseLLMProvider` (template method: retry/fallback/rate-limit/
      cache/loglama) + `OpenRouterProvider` (gerçek `httpx` implementasyonu) + `factory.py`
      (`config/models.yaml` routing) — bkz. `providers/llm/README.md`, 72 test
- [x] `ScopeGuard.post_check` (LLM sınıflandırıcı) implementasyonu
- [x] Prompt sistemi: `prompts/{agent}/{system,user,examples}.md` + `PromptLoader`
- [x] **10 agent'ın gerçek iş mantığı**: TopicScout, Research (yeni — Writer'ın faktüel
      dayanağı), Strategist, Writer, SEOOptimizer, Linker (deterministik), ImageGenerator,
      Editor, Publisher (yalnızca dosya yazar), GitAgent (yalnızca git)
- [x] `image_processing.py`: tek temel görselden `cover/thumbnail/og-image` türetme (Pillow)
- [x] `LocalGitProvider` (`git`/`gh` subprocess) — gerçek repo fixture'larıyla test edildi
- [x] Editor retry döngüsü (`engine.yaml: editor_reject_max_retries`, `needs_review` durumu)
      Orchestrator'a eklendi; Editor'ün gerekçeleri Writer'a `feedback` olarak geri veriliyor
- [x] Yayın sonrası kalıcılaştırma: `record_article` / `record_keyword_usage` /
      `record_internal_link` yalnızca git adımı başarılı olduktan sonra
- [x] CLI: `PromptLoader` + `LocalGitProvider` bağlandı, `--dry-run` eklendi
- [x] **Somut `ImageProvider` implementasyonu**: `OpenRouterImageProvider`
      (`integrations/image_client.py`, `POST /api/v1/images`) + `create_image_provider`
      factory + CLI kablolaması. `aspect_ratio`/`resolution` modele göre opsiyonel
      gönderilir; hata durumunda (`ImageProviderError`) Orchestrator makaleyi görselsiz
      yayınlar. 30 test (`tests/integrations/test_image_client.py`).
- [ ] `GitAgent`: `publish_strategy: pr-then-automerge` ile gerçek bir PR üzerinde doğrulama
- [ ] İlk 5-10 makale bu modda üretilip kalite + kapsam uyumu doğrulanır

## Faz 2 — Otonom Zamanlama + Direct Publish

- [ ] Scheduler devreye girer (`.github/workflows/content-pipeline.yml` veya cron)
- [ ] Editor + ScopeGuard gate'ine güven oluştuktan sonra `brands/oleart/publish.yaml:
      publish_strategy` → `direct-push`
- [ ] `NotifierAgent`: çalışma özeti bildirimi (yayınlandı / needs_review / scope-reddi / hata)
- [ ] `state/oleart/needs_review/` kuyruğu + alarm mekanizması
- [ ] `SEOOptimizer` + `Linker` + `ImageGenerator` adımlarının paralelleştirilmesi (ikisi de
      yalnızca `seo.json`'a bağımlı — bkz. `ARCHITECTURE.md` §13 notu)

## Faz 3 — Geri Besleme Döngüsü + Linking Zekası

- [ ] GA4 / Search Console entegrasyonu
- [ ] Yayınlanan makale performansının SQLite `articles` tablosuna işlenmesi
- [ ] `TopicScoutAgent` skorlamasının geçmiş performansa göre iyileştirilmesi
- [ ] `LinkerAgent` eşleştirme yönteminin keyword-overlap'ten embedding-tabanlı benzerliğe
      geçirilmesi (opsiyonel — korpus büyüdükçe)
- [ ] Az-linklenen/orphan makale tespit raporu
- [ ] (opsiyonel) başlık/meta description A/B testleri

## Faz 4 — Çoklu Marka Doğrulaması + Genişleme

- [ ] `brands/` + `knowledge/brands/` altına **ikinci bir marka** eklenerek çoklu-marka
      mimarisinin doğrulanması (çekirdek `src/content_factory/` koduna dokunmadan
      yapılabilmeli — bu fazın kabul kriteri)
- [ ] Sosyal medya modülü (Faz 0-3'te üretilen `cover/thumbnail/og-image` varlıklarının
      yeniden kullanımı)
- [ ] Ürün açıklaması modülü
- [ ] Newsletter modülü
- [ ] Çoklu dil desteği (EN pazar)
