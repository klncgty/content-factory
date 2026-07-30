# Content Factory
<img width="1404" height="457" alt="Görüntü" src="https://github.com/user-attachments/assets/e5b79af1-f4ed-4c86-85a8-71564a62c175" />



Marka-bağımsız, çoklu markaya genişleyebilecek otonom AI blog/SEO içerik üretim motoru.
İlk (ve şu an tek) örnek marka: **Oleart** (`brands/oleart/`, `knowledge/brands/oleart/`).

- Mimari: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- Geliştirme planı: [`ROADMAP.md`](./ROADMAP.md)
- Knowledge Base kullanımı / yeni marka ekleme: [`knowledge/README.md`](./knowledge/README.md)
- LLM provider katmanı / yeni sağlayıcı ekleme: [`src/content_factory/providers/llm/README.md`](./src/content_factory/providers/llm/README.md)

## Temel Tasarım Kararları

- **Kapsam garantisi:** İçerik yalnızca `brands/{marka}/scope.yaml`'da tanımlı konularda
  üretilebilir; bu iki bağımsız geçitle (deterministik + LLM sınıflandırıcı) zorlanır, tek bir
  prompt talimatına güvenilmez.
- **Marka bilgisi koddan ayrı:** `content_factory` paketinde hiçbir markanın adı veya konusu
  geçmez. Yapılandırılmış kurallar `brands/{marka}/*.yaml`'da, anlatısal bilgi
  `knowledge/brands/{marka}/*.md`'de, markaya özgü prompt metni ise
  `brands/{marka}/prompts/`'ta yaşar. Yeni bir marka eklemek bu dizinleri doldurmaktan
  ibarettir — çekirdek koda dokunulmaz (bkz. [Yeni marka / yeni konu](#yeni-marka--yeni-konu-ekleme)).
- **Uydurma sayıya karşı deterministik geçit:** `GroundingGuard`, makaledeki birimli
  sayıların (`%`, `°C`, `ay`…) knowledge base'de gerçekten geçip geçmediğini ölçer. "Bu sayı
  doğru mu?" diye LLM'e sormak yetmiyordu — makul görünen uydurma değerler onaylanıyordu.
- **Markdown çıktısı:** Publisher HTML üretmez; `content/blog/*.md` + `public/blog/images/`
  üretir. Sunum, hedef sitenin sorumluluğundadır.
- **Git ayrımı:** Publisher yalnızca dosya yazar, `GitAgent` yalnızca commit/push yapar.
- **Provider bağımsızlığı:** tüm LLM çağrıları `BaseLLMProvider` (template method: cache,
  fallback, rate-limit, retry, loglama tek yerde) üzerinden; varsayılan implementasyon
  OpenRouter, `config/models.yaml` ile agent başına farklı model seçilebilir. Yeni bir
  sağlayıcı eklemek `factory.register_provider(...)`'dan ibarettir, agent kodu değişmez.
- **SQLite state:** `data/{marka}/content_factory.db` — JSON dosyalarının yerini aldı (bkz.
  `ARCHITECTURE.md` §12 gerekçe), agent kodu `StateStore` arayüzü üzerinden çalışır.
  Şema `PRAGMA user_version` tabanlı migration'larla sürümlenir, veri kaybı olmaz.

## Yeni marka / yeni konu ekleme

Motor marka-bağımsızdır: **hangi markada, hangi konuda, hangi siteye** yayın yapılacağı
tamamen config'ten belirlenir. Python'a dokunmak gerekmez.

Çalışacak markayı seçen tek anahtar `--brand` bayrağıdır
(`uv run content-factory --brand oleart`); bu bayrak aşağıdaki iki dizinin tamamını seçer.

| Ne değişecek | Dosya |
|---|---|
| **Hangi siteye yayınlanacak** | `brands/{marka}/publish.yaml` → `target_repo_path`, `content_dir`, `images_dir`, git remote/branch/stratejisi |
| **Hangi konularda yazılabilir** (sert allowlist) | `brands/{marka}/scope.yaml` → `groups[].id` + `topics[]` |
| **Markanın konu bilgisi** (dosya listesi, kategori→bilgi eşlemesi, görsel sahneleri) | `brands/{marka}/knowledge.yaml` |
| **Anlatısal marka bilgisi** (ton, ürünler, SSS, konu bilgi tabanı) | `knowledge/brands/{marka}/*.md` |
| **Yasaklı kelime/iddia, kelime sayısı sınırları** | `brands/{marka}/brand.yaml` |
| **Anahtar kelime kümeleri, iç link hedefleri** | `brands/{marka}/seo.yaml` |
| **Agent başına model/sağlayıcı** | `brands/{marka}/models.yaml` (kök `config/models.yaml` üzerine deep-merge) |
| **Markaya özgü prompt metni** (opsiyonel) | `brands/{marka}/prompts/{agent}/system.md` |

Prompt override'ı **dosya bazında** çalışır: markanın `system.md`'si varsa o kullanılır,
`user.md`'si yoksa ortak `prompts/`'takine düşülür. Kökteki `prompts/` dosyaları
marka-nötrdür ve bir test (`test_shared_prompts_are_brand_neutral`) içlerine marka/konu
adı sızmasını engeller.

Adım adım kurulum ve dosya şablonları için: [`knowledge/README.md`](./knowledge/README.md).

## Durum

**Faz 1 çekirdek pipeline'ı uçtan uca çalışıyor** (397 test) ve canlı yayın yapıyor.
10 agent'ın hepsi gerçek iş mantığıyla implemente edildi:

| Adım | Agent | Not |
|---|---|---|
| 1 | `TopicScout` | aday konular üretir; `ScopeGuard.pre_check` + `NoveltyGuard` deterministik olarak eler. Seçilmeyenler `topics_backlog`'a yazılır — **backlog doluysa bu agent hiç çağrılmaz** |
| 2 | `Research` | knowledge base'e dayalı, kaynaklı araştırma notları — Writer'ın faktüel dayanağı |
| 3 | `Strategist` | outline + başlık + anahtar kelime stratejisi (`Brief`) |
| 4 | `Writer` | marka sesine uygun markdown taslak |
| 5 | `SEOOptimizer` | meta title/description (LLM) + **deterministik** slug |
| 6 | `Linker` | LLM'siz; `StateStore` anahtar kelime örtüşmesiyle iç link planı |
| 7 | `ImageGenerator` | tek temel görsel + Pillow ile 3 türev (cover/thumbnail/og) |
| 8 | `Editor` | zorunlu geçit: deterministik kurallar + `GroundingGuard` (şu an uyarı modunda) → `ScopeGuard.post_check` → LLM kalite |
| 9 | `Publisher` | frontmatter'lı markdown + görselleri hedef repoya yazar, git'e dokunmaz |
| 10 | `GitAgent` | `LocalGitProvider` ile commit/push veya PR |

Editor reddederse Orchestrator taslak döngüsünü (Writer→SEO→Linker) gerekçeleri `feedback`
olarak geri vererek tekrarlar; `editor_reject_max_retries` tükenirse run `needs_review`
ile kapanır ve hiçbir şey yayınlanmaz. Yayın kayıtları (`articles`, `keywords`,
`internal_links`) yalnızca git adımı başarılı olduktan sonra yazılır.

**Durum:** pipeline uçtan uca kablolanmış ve canlıda çalışıyor — oleart.co'ya 3 günde bir
otomatik makale yayınlanıyor (`.github/workflows/publish.yml`). Knowledge Base gerçek
içerikle dolduruldu ve görsel üretimi kablolandı: varsayılan sağlayıcı **Replicate**
(`config/models.yaml -> agents.image_generator.provider`), alternatif olarak Google AI
Studio ve OpenRouter. Sağlayıcı geçişi tek bir config alanıyla yapılır. Görsel üretimi
başarısız olursa makale görselsiz yayınlanır, pipeline durmaz. Hedef sitedeki yayın
sözleşmesi bağımlılığı da tamamlandı (`scripts/build-blog.mjs`).

### Kalite ve gözlemlenebilirlik

Yayınlanan ilk makaleler ölçüldüğünde LLM'in **kaynaktaki sayıları kaydırdığı** görüldü
(knowledge `5-8°C` derken makale `6-8°C`; knowledge'da hiç geçmeyen "ideal saklama
14-18°C" gibi uydurmalar). Buna karşı eklenenler:

- **`GroundingGuard`** (`guards/grounding_guard.py`) — makaledeki birimli sayıları
  knowledge base + araştırma notlarındaki sayılarla birim duyarlı karşılaştırır; zeminsiz
  olanı Editor reddeder. Tarif satırları ("180 °C'de 8-10 dakika kızartın") ve başlık
  numaraları bilinçli olarak kapsam dışıdır — yanlış pozitif bir yayın turunu boşa harcar.
  Yayınlanmış 4 makale üzerinde ölçüldü: 4 gerçek uydurma yakalandı, yanlış pozitif yok.
  **Şu an uyarı modunda** (`config/engine.yaml: grounding.enforce: false`): bulgular
  loglanır ama makale reddedilmez. Canlıda birkaç tur isabeti ölçüldükten sonra
  `true`'ya çekilecek.
- **Kaynak doğrulama** — `ResearchAgent`'ın `sources_used` alanı gerçek knowledge
  dosyalarıyla eşleştirilir; modelin uydurduğu dosya adları elenir.
- **Editor'e araştırma notları** — `key_facts` artık kalite incelemesine de verilir,
  böylece "bu iddia kaynakta var mı?" sorusu sorulabilir.
- **`llm_calls` tablosu** — her LLM çağrısı (model, token, süre) DB'ye yazılır; run
  sonunda model başına maliyet özeti loglanır.
- **Prompt sözleşme testi** — her agent'ın `prompt_vars`'ı ile `user.md`'deki
  `$değişken`ler birebir eşleşmek zorunda; `Template.substitute` eksik değişkende sessiz
  kalmaz, hata fırlatır.

> **Dikkat — görsel kotası:** Google AI Studio'da görsel modelleri (`gemini-2.5-flash-image` ve
> tüm `*-image` türevleri) mevcut anahtarda `limit: 0` ile `429 RESOURCE_EXHAUSTED`
> dönüyor; ücretsiz kota metin modellerinde çalışıyor ama **görselde açık değil**. Bu
> çözülene kadar makaleler görselsiz yayınlanır. Alternatif: projede faturalandırmayı
> etkinleştirmek, `provider: replicate` kullanmak veya `provider: openrouter`'a dönmek.

### Bilinen eksikler

- **İkinci marka henüz denenmedi.** Altyapı hazır ve testle doğrulanıyor
  (`test_second_brand_works_without_touching_python`), ama bugüne kadar yalnızca Oleart
  yapılandırıldı — gerçek bir ikinci marka eklenene kadar sürprizler çıkabilir.
- **`examples.md` dosyaları modele gönderilmiyor.** `PromptSet.examples` yükleniyor ama
  hiçbir agent prompt'una eklemiyor; few-shot örnekleri şu an etkisiz.
- **`brands/{marka}/schedule.yaml` okunmuyor.** Yayın ritmini fiilen
  `.github/workflows/publish.yml` içindeki cron belirliyor; ikisi elle senkron tutulmalı.
- **`blog_url()` `/blog/{slug}/` biçimini sabit üretiyor** (`utils/text.py`) — farklı URL
  yapısı olan bir site için config'e çıkarılmalı.
- `pr-then-automerge` stratejisi gerçek bir PR üzerinde doğrulanmadı (token'ın PR izni
  yok; şu an `direct-push` kullanılıyor, gerekçesi `publish.yaml`'da).
- `brand.yaml` yasaklı ifade listesi hukuki gözden geçirmeden geçmedi.

Ayrıntılı plan: [`ROADMAP.md`](./ROADMAP.md).

## Kurulum

```bash
brew install uv                 # yoksa
uv sync --extra dev
cp .env.example .env            # OPENROUTER_API_KEY, REPLICATE_API_KEY/REPLICATE_API_TOKEN, GIT_TOKEN doldur (Faz 1)

uv run pytest                   # testler
uv run ruff check src tests     # lint

uv run content-factory --brand oleart --dry-run   # hedef repoya yazar, commit/push YAPMAZ
uv run content-factory --brand oleart             # tam pipeline (commit + push)

# başka bir markayı çalıştırmak: brands/{marka}/ + knowledge/brands/{marka}/ hazırla, sonra
uv run content-factory --brand {marka} --dry-run
```

`--dry-run`, üretilen makaleyi hedef repoya yazar ama git'e dokunmaz ve yayını
`StateStore`'a kaydetmez — çıktıyı `git diff` ile inceleyip atmak için.
