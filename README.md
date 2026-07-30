# Content Factory
![Uploading Görüntü.jpeg…]()


Marka-bağımsız, çoklu markaya genişleyebilecek otonom AI blog/SEO içerik üretim motoru.
İlk (ve şu an tek) örnek marka: **Oleart** (`brands/oleart/`, `knowledge/brands/oleart/`).

- Mimari: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- Geliştirme planı: [`ROADMAP.md`](./ROADMAP.md)
- Knowledge Base kullanımı / yeni marka ekleme: [`knowledge/README.md`](./knowledge/README.md)
- LLM provider katmanı / yeni sağlayıcı ekleme: [`src/content_factory/providers/llm/README.md`](./src/content_factory/providers/llm/README.md)

## Temel Tasarım Kararları

- **Kapsam garantisi:** İçerik yalnızca `brands/oleart/scope.yaml`'da tanımlı konularda
  üretilebilir; bu iki bağımsız geçitle (deterministik + LLM sınıflandırıcı) zorlanır, tek bir
  prompt talimatına güvenilmez.
- **Marka bilgisi koddan ayrı:** yapılandırılmış/deterministik kurallar `brands/oleart/*.yaml`'da,
  anlatısal bilgi `knowledge/brands/oleart/*.md`'de (16 dosya, `KnowledgeLoader` ile tip güvenli
  ve cache'li erişim). Yeni bir marka eklemek `brands/{marka}/` + `knowledge/brands/{marka}/`
  dizinlerini doldurmaktan ibarettir, çekirdek koda dokunulmaz.
- **Markdown çıktısı:** Publisher HTML üretmez; `content/blog/*.md` + `public/blog/images/`
  üretir. Sunum, hedef sitenin (oleart.co) sorumluluğundadır.
- **Git ayrımı:** Publisher yalnızca dosya yazar, `GitAgent` yalnızca commit/push yapar.
- **Provider bağımsızlığı:** tüm LLM çağrıları `BaseLLMProvider` (template method: cache,
  fallback, rate-limit, retry, loglama tek yerde) üzerinden; varsayılan implementasyon
  OpenRouter, `config/models.yaml` ile agent başına farklı model seçilebilir. Yeni bir
  sağlayıcı eklemek `factory.register_provider(...)`'dan ibarettir, agent kodu değişmez.
- **SQLite state:** `data/oleart/content_factory.db` — JSON dosyalarının yerini aldı (bkz.
  `ARCHITECTURE.md` §12 gerekçe), agent kodu `StateStore` arayüzü üzerinden çalışır.

## Durum

**Faz 1 çekirdek pipeline'ı uçtan uca çalışıyor** (239 test). 10 agent'ın hepsi gerçek iş
mantığıyla implemente edildi:

| Adım | Agent | Not |
|---|---|---|
| 1 | `TopicScout` | aday konular üretir; `ScopeGuard.pre_check` deterministik olarak eler |
| 2 | `Research` | knowledge base'e dayalı, kaynaklı araştırma notları — Writer'ın faktüel dayanağı |
| 3 | `Strategist` | outline + başlık + anahtar kelime stratejisi (`Brief`) |
| 4 | `Writer` | marka sesine uygun markdown taslak |
| 5 | `SEOOptimizer` | meta title/description (LLM) + **deterministik** slug |
| 6 | `Linker` | LLM'siz; `StateStore` anahtar kelime örtüşmesiyle iç link planı |
| 7 | `ImageGenerator` | tek temel görsel + Pillow ile 3 türev (cover/thumbnail/og) |
| 8 | `Editor` | zorunlu geçit: deterministik kurallar → `ScopeGuard.post_check` → LLM kalite |
| 9 | `Publisher` | frontmatter'lı markdown + görselleri hedef repoya yazar, git'e dokunmaz |
| 10 | `GitAgent` | `LocalGitProvider` ile commit/push veya PR |

Editor reddederse Orchestrator taslak döngüsünü (Writer→SEO→Linker) gerekçeleri `feedback`
olarak geri vererek tekrarlar; `editor_reject_max_retries` tükenirse run `needs_review`
ile kapanır ve hiçbir şey yayınlanmaz. Yayın kayıtları (`articles`, `keywords`,
`internal_links`) yalnızca git adımı başarılı olduktan sonra yazılır.

**Durum:** pipeline uçtan uca kablolanmış durumda. Knowledge Base'in 16 dosyası gerçek
içerikle dolduruldu (`KnowledgeLoader.validate("oleart")` artık placeholder raporlamıyor)
ve görsel üretimi kablolandı: varsayılan sağlayıcı **Google AI Studio (Gemini API)**,
alternatif olarak OpenRouter — ikisi de `integrations/image_client.py`'de, geçiş tek bir
config alanıyla (`agents.image_generator.provider`). Görsel üretimi başarısız olursa
makale görselsiz yayınlanır, pipeline durmaz. oleart.co tarafındaki yayın sözleşmesi
bağımlılığı da tamamlandı (`scripts/build-blog.mjs`).

> **Dikkat — görsel kotası:** Gemini API'de görsel modelleri (`gemini-2.5-flash-image` ve
> tüm `*-image` türevleri) mevcut anahtarda `limit: 0` ile `429 RESOURCE_EXHAUSTED`
> dönüyor; ücretsiz kota metin modellerinde çalışıyor ama **görselde açık değil**. Bu
> çözülene kadar makaleler görselsiz yayınlanır. Alternatif: projede faturalandırmayı
> etkinleştirmek veya `provider: openrouter`'a dönmek (orada görsel üretimi ücretli ama
> çalışıyor).

**Kalan işler:** görsel kotasının açılması, `pr-then-automerge` stratejisinin gerçek bir
PR üzerinde doğrulanması, `brand.yaml` yasaklı ifade listesinin hukuki gözden geçirmesi
ve ilk 5-10 makalenin kalite/maliyet doğrulaması — bkz. `ROADMAP.md`.

## Kurulum

```bash
brew install uv                 # yoksa
uv sync --extra dev
cp .env.example .env            # OPENROUTER_API_KEY, IMAGE_API_KEY, GIT_TOKEN doldur (Faz 1)

uv run pytest                   # testler
uv run ruff check src tests     # lint

uv run content-factory --brand oleart --dry-run   # hedef repoya yazar, commit/push YAPMAZ
uv run content-factory --brand oleart             # tam pipeline (PR açar)
```

`--dry-run`, üretilen makaleyi hedef repoya yazar ama git'e dokunmaz ve yayını
`StateStore`'a kaydetmez — çıktıyı `git diff` ile inceleyip atmak için.
