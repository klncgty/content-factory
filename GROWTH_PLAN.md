# Growth Intelligence Platform — Uygulama Planı ve Görev Listesi

Bu dosya, Content Factory'ye eklenecek ikinci workflow'un (Growth Intelligence Platform)
tasarımını ve adım adım uygulama görevlerini içerir.

**Yeni bir oturumda kullanımı:** "GROWTH_PLAN.md'yi oku, Adım N'i uygula" demek yeterli.
Her adımın görev promptu kendi başına yeterli bilgi taşır.

---

# BÖLÜM 1 — Tasarım Referansı

## Amaç

Siteyi bir **Growth Manager** gibi değerlendiren, mevcut makale üretim pipeline'ından
tamamen bağımsız ikinci bir sistem. Yalnızca içerik kalitesi değil; landing page
performansı, hero, CTA yerleşimi, ürün sayfaları, dönüşüm, kullanıcı akışı, schema
eksikleri, internal linking, topic cluster boşlukları ve genel SEO fırsatları.

Bulguları gerekçesi ve verisiyle açıklar, önceliklendirir, **yalnızca insan onayından
sonra** aksiyon alır.

## Sabit kararlar

| Konu | Karar |
|---|---|
| Tetikleme | **Manuel.** `uv run content-factory growth --brand oleart`. Scheduler/cron **yok** |
| Süreç | Tek süreç, tek makine. Analiz + onay + uygulama aynı yerde |
| Mimari | **LangGraph** state machine (paralel fan-out, koşullu dallanma, revizyon döngüsü, `interrupt()` ile onayda duraklama) |
| LLM | LangGraph yalnızca graf/checkpoint/interrupt için. **LLM çağrıları LangChain'den GEÇMEZ** — mevcut `BaseLLMProvider` kullanılır (`ARCHITECTURE.md` §0.4) |
| Dashboard | FastAPI + Jinja2 + HTMX, `127.0.0.1:8765`, CLI süreci açık olduğu sürece çalışır, tek merkez |
| E-posta | Faz 1'de yok (`Notifier` ABC + `NullNotifier` dikişi kalır) |
| Google auth | Service account JSON, `.env` |
| Core Web Vitals | Bu sürümde kapsam dışı, alan rezerve |
| Execution | Faz 1'de handler'lar no-op; onaylananlar `growth_actions`'a `queued` yazılır |
| DB | `data/{brand}/growth.db` — `.gitignore`'daki `data/*/*.db` zaten kapsıyor, yerel kalır |
| Scheduler dikişi | Tüm workflow `runner.run_growth_analysis()` arkasında; ileride cron eklemek = bu fonksiyonu çağırmak |

## Mevcut sisteme müdahale sözü

**Dokunulmayacak dosyalar:** `orchestrator.py`, `agents/*`, `domain/models.py`, `state/*`,
`guards/*`, `providers/*`, mevcut `prompts/*`, `.github/workflows/publish.yml`.

`cli.py`'ye yalnızca 4 satırlık alt-komut yönlendirmesi eklenecek. Growth için yeni CI
workflow'u **oluşturulmayacak**.

**Baseline: 412 test geçiyor.** Her adımdan sonra bu sayı düşmemeli.

## Hedef sitenin gerçekleri (`../oleart.co` — incelendi)

Düz statik HTML, SSG yok. Arayüz değişikliği teknik olarak mümkün ama ihlal edilirse
siteyi bozacak kurallar var:

| Gerçek | Sonucu |
|---|---|
| `index.html` (35KB) tek sayfa, JS sekme geçişli; `assets/styles.css` (60KB) | Hero/CTA/bölüm değişiklikleri bu iki dosyada |
| `blog/` ve `sitemap.xml` **üretilmiş** — kaynak `content/blog/*.md` + `scripts/build-blog.mjs` | Asla elle düzenlenmez; makale değişikliği `.md`'ye, sonra `npm run build:blog` |
| Ürün kartı **tek kaynak**: `assets/product-card.js` (site + admin paneli ortak) | Kart değişikliği yalnızca bu dosyada |
| Footer çapa id'leri **dört dosyada birden**: `index.html`, `404.html`, `bilgilendirme/index.html`, `scripts/build-blog.mjs::INFO_LINKS` | Çapa değişikliği atomik dört dosya düzenlemesi |
| `assets/analytics.js` içinde **17 özel GA4 event'i** kurulu | CRO analizi tahmin değil ölçüm |
| `53439975822Dakikaotur.html` admin paneli, noindex, GA çağırmaz | Analiz kapsamı dışı |

**Mevcut GA4 event taksonomisi platformun en değerli girdisi:**
`whatsapp_click` (parametreler: `section`, `button_text`, `product_name`), `cta_click`,
`instagram_click`, `phone_click`, `footer_link_click`, `blog_to_product`,
`external_link_click`, `select_product`, `page_view`, `view_product`, `view_blog`,
`policy_section_view`, `blog_read_complete`, `scroll_depth`, `time_on_page`,
`gallery_image_change`. Yani "hangi bölümdeki hangi CTA dönüştürüyor" **zaten ölçülüyor**.

## Merkezî fikir: kanıtsız öneri yoktur

Hedeflenen çıktı örneği:

> "Bu sayfa son 28 günde 18.000 impression aldı ancak CTR yalnızca %1.4. Aynı pozisyondaki
> benzer sayfaların ortalaması %3.8. Başlığın daha dikkat çekici hale getirilmesi yaklaşık
> %20-30 daha fazla organik tıklama sağlayabilir."

Bunu LLM'den "böyle yaz" diye istemek uydurma sayı üretir. Üç katmanlı mekanizma —
repo'nun mevcut `GroundingGuard` felsefesinin uygulaması:

1. **`diagnostics/` (LLM yok)** sayısal kanıtı **kod üretir**: pozisyon→beklenen CTR
   eğrisi, sitenin kendi peer ortalamaları, dönem-üstü-dönem deltalar, huni oranları.
   LLM'e ham metrik değil, **hesaplanmış `Finding` nesneleri** gider.
2. **Agent'lar** bu bulgulara teşhis ve çözüm yazar — sayı üretmez, verilen sayıyı kullanır.
3. **`EvidenceGuard` (LLM yok, zorunlu geçit)** her önerinin gerekçesindeki her sayıyı
   gerçek metriklere karşı doğrular. Doğrulanamayan sayı taşıyan öneri plana giremez.

## LangGraph grafı

```
                              START
                                │
        ┌───────────────────────┼───────────────────────┐         (paralel fan-out)
  collect_analytics    collect_search_console      inspect_site
        └───────────────────────┼───────────────────────┘
                        measure_outcomes        (geçmiş aksiyonların etkisi ölçülür)
                                │
                        run_diagnostics         ← LLM YOK: tüm sayısal kanıt burada
                                │
                          validate_data ──yetersiz──→ END (insufficient_data)
                                │
                       performance_analyst      ← bütünsel teşhis, tüm bulguları okur
                                │
    ┌──────────┬────────────┬───┴────────┬────────────┬──────────┐    (paralel fan-out)
 content_   technical_    seo_        ux_          cro_      internal_   opportunity
 portfolio     seo     strategist   analyst       agent       linking
    └──────────┴────────────┴────────────┴────────────┴──────────┘
                                │
                        content_strategist       ← yeni içerik mi, güncelleme mi
                                │
                        executive_decision ◄──────────────┐
                                │                         │
                          evidence_audit                  │   ← zorunlu geçit
                                │                         │
                          persist_plan                    │
                                │                         │
                  ── interrupt() insan onayı ──           │
                                │                         │
                          apply_feedback ──düzenleme var──┘   (revision_count < max)
                                │ onaylandı
                          execute_approved
                                │
                               END
```

**Revizyon koşulu:** `apply_feedback` sonrası herhangi bir öneri `edited` ise veya serbest
metinli `ask_ai` geldiyse → `executive_decision`'a dön, düzenlemeler kısıt olarak prompt'a
girer. Sadece approve/reject varsa doğrudan `execute_approved`. `max_revisions` (3)
aşılırsa döngü kırılır.

**`evidence_audit`'te elenenler atılmaz** — plana "kanıt yetersiz" etiketiyle ayrı bölümde
gösterilir (Editor'ün `needs_review` felsefesi: sessizce kaybetme, işaretleyip göster).

## Dosya yerleşimi

```
src/content_factory/growth/
├── cli.py  runner.py  progress.py
├── models.py           # Finding, Recommendation, GrowthPlan, snapshot'lar
├── state.py  graph.py  nodes.py
├── diagnostics/        # LLM YOK — kanıt üreten hesap motoru
│   ├── ctr_curve.py  benchmarks.py  decay.py  funnel.py  engine.py
├── guards/evidence_guard.py
├── agents/
│   ├── performance_analyst.py  content_portfolio.py  technical_seo.py
│   ├── seo_strategist.py  ux_analyst.py  cro.py
│   ├── content_strategist.py  executive_decision.py
│   └── internal_linking.py  opportunity.py        # LLM YOK
├── collectors/
│   ├── base.py  google_auth.py  ga4.py  gsc.py  site_inspector.py  stub.py
├── site/
│   ├── model.py        # SiteMap, PageNode, CtaNode
│   └── policy.py       # site.yaml -> "hangi dosya düzenlenebilir" kuralları
├── memory.py
├── store/base.py  store/sqlite.py
├── execution/queue.py  execution/runner.py  execution/handlers/
├── notify/base.py
└── dashboard/app.py  server.py  templates/  static/

tests/growth/           # aynı yapıda testler
prompts/{8 growth agent}/{system,user}.md
config/growth.yaml
brands/oleart/growth.yaml
brands/oleart/site.yaml
knowledge/brands/oleart/site_structure.md
```

## Repo konvansiyonları (her adımda uyulacak)

1. **Türkçe** docstring, yorum ve test adları; İngilizce identifier'lar.
2. `src/content_factory/` içinde **hiçbir marka/site adı geçmez** — her şey config'te.
3. Agent = `BaseAgent[TIn, TOut]` alt sınıfı; `context.llm`, `call_llm()`,
   `parse_llm_json()` kullanılır; prompt'lar `prompts/{name}/` altında `$degisken`
   (Python `string.Template`, Jinja değil).
4. Yeni tablo → `_SCHEMA`'ya `CREATE TABLE IF NOT EXISTS` + `PRAGMA user_version` bump
   (`state/sqlite_store.py` desenini birebir kopyala).
5. Testlerde **gerçek ağ çağrısı yok** — `httpx.MockTransport` veya stub.
6. Test docstring'leri gerçek vakayı/gerekçeyi anlatır (repo'nun en tutarlı alışkanlığı).
7. `ruff`: line-length 100, `select = ["E","F","I","UP","B"]`.
8. Agent'lar birbirini çağırmaz — yalnızca graf üzerinden ve state ile konuşur.

---

# BÖLÜM 2 — Adım Adım Görevler

## Durum

- [x] **Adım 0** — `pyproject.toml`'a bağımlılıklar eklendi (`langgraph`,
      `langgraph-checkpoint-sqlite`, `google-auth`, `selectolax` + `dashboard` extra).
      **`uv sync` HENÜZ ÇALIŞTIRILMADI.**
- [ ] Adım 1 — İskelet + store + site modeli
- [ ] Adım 2 — GA4 + Search Console collector'ları
- [ ] Adım 3 — Site Inspector
- [ ] Adım 4 — Diagnostics kanıt motoru
- [ ] Adım 5 — Deterministik agent'lar + EvidenceGuard
- [ ] Adım 6 — LLM agent'ları + prompt'lar
- [ ] Adım 7 — LangGraph grafı + runner
- [ ] Adım 8 — CLI
- [ ] Adım 9 — Dashboard
- [ ] Adım 10 — Memory + outcome ölçümü
- [ ] Adım 11 — Execution kuyruğu
- [ ] Adım 12 — Dokümantasyon

---

## Adım 1 — İskelet + store + site modeli

> GROWTH_PLAN.md Adım 1'i uygula.
>
> Önce `uv sync --extra dev --extra dashboard` çalıştır ve yeni bağımlılıkların kurulduğunu
> doğrula.
>
> Sonra şunları yaz:
>
> **`src/content_factory/growth/models.py`** — pydantic, `domain/models.py`'deki
> `DomainModel` (`extra="forbid"`) yeniden kullanılır. Sınıflar bağımlılık sırasına göre:
> - `MetricPeriod{start: date, end: date, label: str}`
> - `FindingDomain` StrEnum: `content | seo | ux | cro | technical | linking`
> - `Finding{finding_id, domain, subject, metric, observed, expected|None, delta_pct|None,
>   supporting: dict[str,float], period, severity: int 1-5, source: str}`
> - `PageMetric`, `QueryMetric`, `EventMetric` (event adı + parametre kırılımı + sayı)
> - `AnalyticsSnapshot{period, totals, pages, events, devices, countries, sources}`
> - `SearchConsoleSnapshot{period, totals, queries, pages, index_coverage, sitemap_status}`
> - `SiteSnapshot{pages: list[PageAudit], ctas, link_graph, collected_at}` (detay Adım 3'te
>   dolar, burada iskelet)
> - `RecommendationType` StrEnum: `update_title, update_meta, add_faq, expand_content,
>   merge_content, retire_content, add_internal_links, add_schema, fix_headings,
>   fix_alt_text, new_article, republish, hero_change, cta_change, cta_placement,
>   section_reorder, nav_change, product_card_change, trust_element, mobile_fix,
>   copy_change, page_speed`
> - `ExpectedGain{metric, low_pct, high_pct, basis}`, `EffortEstimate{hours_low, hours_high,
>   complexity, needs_dev}`, `FindingRef{finding_id, note}`
> - `Recommendation` — plandaki tam alan listesi: `ref_no, type, title, domain, target_url,
>   target_file, target_section, diagnosis, evidence: list[FindingRef], proposed_change,
>   expected_gain, impact 1-5, priority 1-5, confidence 0-1, effort, risk, source_agent,
>   status, user_note, evidence_verified`
> - `GrowthPlan{plan_id, brand, run_id, revision, created_at, summary_markdown,
>   recommendations, rejected_by_evidence, status}`
> - `HumanFeedback{command, recommendation_refs, free_text}` — command:
>   `approve_all|approve_selected|reject_selected|edit|ask_ai|finalize`
> - `GrowthAction{action_type, recommendation_ref, params, status, measure_after_days}`
>
> **`src/content_factory/growth/store/base.py`** — `GrowthStore` ABC. Mevcut
> `state/store.py`'nin ABC desenini takip et. Mevcut `StateStore`'u **genişletme**, ayrı
> bir bounded context. Metotlar: `init_schema`, run CRUD, snapshot yazma/okuma, finding
> yazma/okuma, plan + recommendation CRUD, feedback log, action CRUD, outcome CRUD,
> `close`, `__enter__`/`__exit__`.
>
> **`src/content_factory/growth/store/sqlite.py`** — `SQLiteGrowthStore`.
> `state/sqlite_store.py` desenini birebir: modül seviyesinde `_SCHEMA` string'i,
> `_SCHEMA_VERSION = 1`, `_MIGRATIONS: dict[int, list[str]]`, `PRAGMA user_version`,
> `row_factory = sqlite3.Row`, her yazma commit. Tablolar: `growth_runs`,
> `metric_snapshots`, `page_metrics`, `query_metrics`, `event_metrics`, `site_snapshots`,
> `findings`, `growth_plans`, `recommendations`, `growth_feedback`, `growth_actions`,
> `growth_outcomes`. DB yolu: `data/{brand}/growth.db`.
>
> **`src/content_factory/growth/site/model.py` + `policy.py`** — `site.yaml`'ı okuyup
> "bu dosya düzenlenebilir mi" sorusuna **deterministik** cevap veren katman.
> `SitePolicy.check_target(path) -> PolicyVerdict`. Kurallar: `generated` ve `forbidden`
> yollara öneri üretilemez; `synchronized` gruptaki bir dosyaya dokunan öneri grubun
> tamamını kapsamalı; `editable` dışı yollar reddedilir. glob eşleşmesi (`fnmatch`).
>
> **`settings/schemas.py`** — `GrowthConfig` (+ `AnalyticsSettings`, `SearchConsoleSettings`,
> `ThresholdsConfig`, `PlanConfig`, `DashboardConfig`) ve `SiteConfig` (+ `SitePaths`,
> `SiteBuild`, `SiteConversion`). Hepsi `YamlModel` alt sınıfı, tüm alanlar varsayılanlı.
>
> **`settings/loader.py`** — `Settings`'e `growth: GrowthConfig` ve `site: SiteConfig`
> alanları ekle. **Kritik:** `config/growth.yaml`, `brands/{b}/growth.yaml` ve
> `brands/{b}/site.yaml` yoksa `ConfigError` fırlatma — varsayılan nesne kullan. Böylece
> mevcut 412 test etkilenmez. `growth.yaml` için `models.yaml`'daki `_deep_merge` desenini
> kullan (engine + brand üstü yazar).
>
> **`config/growth.yaml`**, **`brands/oleart/growth.yaml`**, **`brands/oleart/site.yaml`** —
> plandaki içerikle, YAML yorumlarında gerekçeler Türkçe.
>
> **Testler** (`tests/growth/`): `conftest.py` (growth_settings, growth_store on tmp_path),
> `test_models.py`, `test_store_sqlite.py` (şema, migrasyon idempotent, CRUD),
> `test_site_policy.py` — `blog/index.html` (generated) reddedilmeli, `api/products.js`
> (forbidden) reddedilmeli, `index.html` (editable) kabul edilmeli, footer çapası önerisi
> dört dosyayı kapsamıyorsa reddedilmeli.
>
> **Bitiş kriteri:** `uv run pytest` → 412 + yeni testler, hepsi geçiyor. `uv run ruff check`
> temiz.

---

## Adım 2 — GA4 + Search Console collector'ları

> GROWTH_PLAN.md Adım 2'yi uygula. Adım 1 tamamlanmış olmalı.
>
> **`growth/collectors/base.py`** — `AnalyticsProvider` ve `SearchConsoleProvider` ABC'leri.
> `providers/llm/base.py`'nin ABC desenini takip et (sınıf attribute olarak `name`,
> `default_api_key_env`). Metotlar `fetch(period, previous_period) -> Snapshot`.
>
> **`growth/collectors/google_auth.py`** — service account JSON'dan access token.
> `google-auth` yalnızca JWT imzalama/token yenileme için kullanılır; API çağrıları
> `httpx` ile. `GOOGLE_SERVICE_ACCOUNT_JSON` env'i hem dosya yolu hem tek satırlık JSON
> içeriği kabul etmeli. Scope'lar: `analytics.readonly`, `webmasters.readonly`.
> Credential yoksa `None` döndür (exception değil) — çağıran stub'a düşer.
>
> **`growth/collectors/ga4.py`** — GA4 Data API `POST
> https://analyticsdata.googleapis.com/v1beta/properties/{id}:runReport`.
> Çekilecekler: sessions, users, engagementRate, averageSessionDuration; landing page ve
> exit page boyutlarında sayfa metrikleri; `eventName` boyutunda **17 özel event** ve
> parametreleri (`section`, `button_text`, `product_name`, `article_title`, `percentage`,
> `seconds`); device/country/source kırılımları. Hem `period` hem `previous_period` için
> çekip normalize et.
>
> **`growth/collectors/gsc.py`** — `POST
> https://www.googleapis.com/webmasters/v3/sites/{siteUrl}/searchAnalytics/query`
> `query` ve `page` boyutlarında; `GET .../sitemaps` sitemap durumu.
> `row_limit` config'ten.
>
> **`growth/collectors/stub.py`** — `StubAnalyticsProvider`, `StubSearchConsoleProvider`.
> Deterministik, gerçekçi veri: birkaç sayfa, birkaç query, striking-distance vakası ve
> düşük-CTR vakası içermeli ki sonraki adımların testleri bunları kullanabilsin.
>
> **Testler** (`tests/growth/collectors/`): `httpx.MockTransport` ile gerçek GA4/GSC yanıt
> şekilleri, normalizasyon, boş yanıt, 401/403/429 hata eşlemesi, credential yokken stub'a
> düşme. Gerçek ağ çağrısı yok.
>
> **Bitiş kriteri:** tüm testler geçiyor, ruff temiz.

---

## Adım 3 — Site Inspector

> GROWTH_PLAN.md Adım 3'ü uygula. Adım 1 tamamlanmış olmalı.
>
> **`growth/collectors/site_inspector.py`** — hedef repo'yu `site.yaml` kurallarına göre
> tarar, `SiteSnapshot` üretir. `selectolax` ile HTML parse. **Hiçbir dosyaya yazmaz.**
>
> Sayfa başına çıkarılacaklar (`PageAudit`):
> - `<title>` ve meta description metni + uzunlukları
> - H1-H6 hiyerarşisi ve hiyerarşi bozuklukları (atlanan seviye, birden çok H1)
> - JSON-LD schema tipleri (`Product`, `FAQPage`, `BreadcrumbList`, `Organization`,
>   `Article`, `WebSite`) ve eksik olanlar
> - CTA envanteri: `[data-cta]`, `.order-link`, `a[href^='https://wa.me']`,
>   `a[href^='tel:']` — her biri için metin, en yakın bölüm id'si, DOM sırası
> - `<img>` alt kapsaması (toplam / alt'lı / boş alt)
> - canonical, robots meta, viewport
> - internal link grafiği (hangi sayfa hangi sayfaya link veriyor) → orphan tespiti için
> - sayfa ağırlığı (HTML byte + referans verilen asset boyutları)
>
> `page_map` ile URL ↔ kaynak dosya eşlemesi: `/blog/{slug}/` → `content/blog/*-{slug}.md`.
> Bu eşleme, GA4 `page_location`'ının hangi dosyada düzeltileceğini bilmemizi sağlar.
>
> `kind: static_html` için `StaticHtmlInspector`; ileride farklı `kind` değerleri için alt
> sınıf eklenebilecek şekilde tasarla (fabrika fonksiyonu).
>
> **Testler** (`tests/growth/collectors/test_site_inspector.py`): `tmp_path` altında
> `oleart.co`'nun küçültülmüş bir kopyası (birkaç HTML dosyası, bir JSON-LD, birkaç CTA,
> alt'sız bir görsel, bir orphan sayfa). Gerçek `../oleart.co`'ya dokunma.
>
> **Bitiş kriteri:** testler geçiyor; `--inspect-only` ile gerçek sitede çalıştırıldığında
> (Adım 8'den sonra) `cd ../oleart.co && git status --porcelain` boş kalmalı.

---

## Adım 4 — Diagnostics kanıt motoru

> GROWTH_PLAN.md Adım 4'ü uygula. Adım 1-3 tamamlanmış olmalı.
>
> **LLM YOK.** Bu katman tüm sayısal kanıtı üretir; agent'lar sayı uydurmaz, buradan alır.
>
> **`growth/diagnostics/ctr_curve.py`** — pozisyona göre beklenen CTR eğrisi.
> Striking distance (pozisyon 5-15 + `min_impressions` üstü). "Beklenenin altında CTR"
> hesabı ve kaçırılan tıklama tahmini.
>
> **`growth/diagnostics/benchmarks.py`** — sitenin **kendi** peer ortalamaları (aynı
> pozisyon bandı, aynı sayfa tipi). Dışarıdan uydurma sektör ortalaması **kullanılmaz**.
>
> **`growth/diagnostics/decay.py`** — dönem-üstü-dönem düşüş, içerik çürümesi,
> yükselen/gerileyen sayfalar, güncellenme yaşı.
>
> **`growth/diagnostics/funnel.py`** — `view_product` → `select_product` →
> `whatsapp_click` dönüşüm oranları; `section` parametresi bazında CTA verimliliği;
> yüksek çıkışlı sayfalar; `scroll_depth` ile "fold altında kalan CTA" sinyali.
>
> **`growth/diagnostics/engine.py`** — hepsini toplar, `growth.yaml` eşikleriyle filtreler,
> `list[Finding]` döndürür. Her `Finding.source` alanı hangi modülden geldiğini söyler
> (`"gsc.ctr_curve"`, `"ga4.funnel"` …) — izlenebilirlik için zorunlu.
>
> **Testler** (`tests/growth/diagnostics/`): her hesap için tablo-güdümlü vakalar.
> **Zorunlu test:** 18.000 impression / %1.4 CTR / pozisyon 8.3 girdisi, peer ortalaması
> %3.8 iken "%20-30 daha fazla tıklama" aralığını üretmeli. Docstring'inde bu vakanın
> kullanıcının hedeflediği çıktı örneği olduğu yazsın.
>
> **Bitiş kriteri:** testler geçiyor, ruff temiz.

---

## Adım 5 — Deterministik agent'lar + EvidenceGuard

> GROWTH_PLAN.md Adım 5'i uygula. Adım 1-4 tamamlanmış olmalı.
>
> **`growth/agents/internal_linking.py`** — **LLM YOK.** Mevcut
> `StateStore.get_recent_articles` / `find_related_articles` / `internal_links` tablosu +
> `SiteSnapshot.link_graph`. Üretir: topic cluster haritası, orphan sayfalar (hiç iç link
> almayan), eksik linkler (yüksek keyword örtüşmesi ama link yok), cluster boşlukları.
> Mevcut `agents/linker.py`'nin keyword-overlap mantığını yeniden kullan, kopyalama.
>
> **`growth/agents/opportunity.py`** — **LLM YOK.** `Finding` listesini fırsat olarak
> sıralar: striking distance, düşük CTR/yüksek impression, yüksek potansiyelli düşük
> performanslı sayfalar, yüksek trafikli düşük dönüşümlü sayfalar.
>
> **`growth/guards/evidence_guard.py`** — **zorunlu geçit, LLM yok.**
> `guards/grounding_guard.py`'yi model al (aynı felsefe, farklı korpus). Her
> `Recommendation`'ın `diagnosis` + `proposed_change` + `expected_gain` metinlerindeki
> **her sayıyı** çıkarır ve `Finding` korpusuna karşı doğrular. Doğrulanamayan sayı taşıyan
> öneri `evidence_verified=False` alır. Ayrıca `SitePolicy.check_target` ile hedef dosya
> kontrolü yapar. Sonuç: `EvidenceResult{verified, rejected, reasons}`.
>
> **Testler:** orphan tespiti, eşik davranışı, uydurma sayı reddi (`Finding`'e bağlı sayı
> geçmeli, olmayan sayı reddedilmeli), generated/forbidden dosyaya öneri reddi.
>
> **Bitiş kriteri:** testler geçiyor, ruff temiz.

---

## Adım 6 — LLM agent'ları + prompt'lar

> GROWTH_PLAN.md Adım 6'yı uygula. Adım 1-5 tamamlanmış olmalı.
>
> 8 adet `BaseAgent[TIn, TOut]` alt sınıfı. Her biri: `name` ClassVar, `prompt_vars`
> ClassVar frozenset, `run()`, `call_llm()` + `parse_llm_json()`. Prompt'lar
> `prompts/{name}/{system,user}.md`, `$degisken` (string.Template) ile.
>
> | Agent | `name` | Sorumluluk |
> |---|---|---|
> | Performance Analyst | `performance_analyst` | Bütünsel teşhis: trafik neden düştü, CTR neden azaldı, hangi içerik yükseliyor/geriliyor, yeni içerik gerçekten gerekli mi |
> | Content Portfolio | `content_portfolio` | Makale bazında: koru/güncelle/genişlet/birleştir/emekliye ayır. Çürüme, keyword yamyamlığı |
> | Technical SEO | `technical_seo` | Schema eksikleri, canonical, meta uzunlukları, heading hiyerarşisi, alt text, index coverage, sitemap tutarlılığı |
> | SEO Strategist | `seo_strategist` | Sayfa bazlı title/meta yeniden yazımı — **somut yeni metin** önerir, "değiştir" demez |
> | UX Analyst | `ux_analyst` | Hero, fold üstü içerik, bölüm sırası, kullanıcı akışı (entrances→exits), mobil, navigasyon, yüksek çıkışın nedeni |
> | CRO | `cro_agent` | CTA yerleşimi/metni (WhatsApp/telefon/sipariş), trust elementleri, ürün kartları, sticky bar. `section` bazlı gerçek dönüşüm verisine dayanır |
> | Content Strategist | `content_strategist` | Yeni makale mi / güncelleme mi / cluster / comparison / guide / FAQ / seasonal |
> | Executive Decision | `executive_decision` | Tüm önerileri okur, çakışanları çözer, ROI/impact/confidence/effort hesaplar, tek sıralı `GrowthPlan`. Revizyon turunda kullanıcı düzenlemeleri kısıt olarak gelir |
>
> **Prompt kuralı:** prompt'a ham metrik tablosu **konmaz** — hesaplanmış `Finding`
> nesneleri konur. Bu hem token maliyetini düşürür hem modelin sayı uydurma alanını
> daraltır. Her agent'ın JSON çıktı şeması `user.md` içinde fenced ```json bloğu olarak
> tanımlanır (mevcut `prompts/scope_guard/user.md` deseni).
>
> **Shared prompt'lar marka-nötr olmalı** — `test_shared_prompts_are_brand_neutral`
> "oleart", "zeytin", "olive_and_oil", "wooden_products" kelimelerini arar.
>
> **`config/models.yaml`** — 8 agent girdisi ekle. LLM'siz growth node'larını (
> `internal_linking`, `opportunity`, collector'lar) **buraya yazma** —
> `create_agent_scoped_llm_provider` her girdi için provider kurar.
>
> **`tests/test_prompts.py`** — ayrı bir `EXPECTED_GROWTH_AGENTS` seti ekle:
> `system.md` + `user.md` zorunlu, **`examples.md` zorunlu değil** (growth prompt'ları
> marka sesi değil veri şeması taşır). `_PROMPT_VARS_OWNERS`'a 8 sınıfı ekle.
>
> **Testler** (`tests/growth/agents/`): her agent için `StubLLMProvider` ile —
> hem dönen domain nesnesi hem **render edilen prompt** üzerinden assert
> (`tests/agents/test_writer.py` deseni: `stub.requests[0].messages[0].content` içinde
> beklenen bilginin geçtiğini doğrula).
>
> **Bitiş kriteri:** testler geçiyor, `test_prompts.py` yeşil, ruff temiz.

---

## Adım 7 — LangGraph grafı + runner

> GROWTH_PLAN.md Adım 7'yi uygula. Adım 1-6 tamamlanmış olmalı.
>
> **`growth/state.py`** — `GrowthState` TypedDict, `total=False`. Paralel yazılan alanlar
> reducer'lı: `findings`, `recommendations`, `rejected_by_evidence`, `step_history` →
> `Annotated[list[...], operator.add]`. Tam alan listesi tasarım bölümünde.
>
> **`growth/nodes.py`** — node fonksiyonları. Her biri **ince sarmalayıcı**: `GrowthState`
> → agent/collector girdisi → çıktı → state güncellemesi (5-15 satır). İş mantığı node'da
> değil agent/diagnostics'te. Ayrıca `NODE_SPECS` listesi — yeni agent eklemek buraya bir
> satır olmalı.
>
> **`growth/graph.py`** — `build_growth_graph(deps) -> CompiledStateGraph`. Tasarım
> bölümündeki grafı kur: 3'lü collector fan-out, `measure_outcomes`, `run_diagnostics`,
> `validate_data` koşullu çıkışı, `performance_analyst`, 6'lı analiz fan-out,
> `content_strategist`, `executive_decision`, `evidence_audit`, `persist_plan`,
> `interrupt()`, `apply_feedback` koşullu dönüşü, `execute_approved`.
> Checkpointer: `SqliteSaver` → `data/{brand}/growth.db`, `thread_id = growth_run_id`.
>
> **`growth/progress.py`** — node bazlı ilerleme yayını. CLI'da satır satır log,
> dashboard'da yoklanabilir durum. Basit bir in-process pub/sub yeterli.
>
> **`growth/runner.py`** — `run_growth_analysis(brand, *, deps, ...) -> GrowthRunHandle`.
> **CLI, dashboard butonu ve gelecekteki scheduler'ın TEK giriş noktası.** Wiring'i
> `cli.py::main`'den kopyala: `load_dotenv`, `Settings.load`, `configure_logging`,
> `SQLiteStateStore` (salt-okunur kullanım), `SQLiteGrowthStore`,
> `create_agent_scoped_llm_provider(settings, cache=InMemoryLLMCache(), state=state_store)`,
> `KnowledgeLoader`, `PromptLoader`, `AgentContext`. Ayrıca `resume_growth_analysis(
> run_id, feedback)`.
>
> **Testler** (`tests/growth/test_graph.py`): fake node'larla `step_history` sırası
> (`tests/test_orchestrator.py` deseni). Zorunlu vakalar:
> - iki collector'ın da çalıştığı
> - `insufficient_data` erken çıkışının hiçbir LLM node'una uğramadığı
> - düzenleme varken `executive_decision`'ın yeniden çağrıldığı
> - sadece approve/reject varken çağrılmadığı
> - `max_revisions` aşıldığında döngünün kırıldığı
> - `interrupt` → `resume` turunun `MemorySaver` ile çalıştığı
>
> **Bitiş kriteri:** testler geçiyor, ruff temiz.

---

## Adım 8 — CLI

> GROWTH_PLAN.md Adım 8'i uygula. Adım 1-7 tamamlanmış olmalı.
>
> **`src/content_factory/cli.py`** — `main`'in **en başına** yalnızca şu yönlendirme:
> ```python
> def main(argv: list[str] | None = None) -> int:
>     args = list(sys.argv[1:] if argv is None else argv)
>     if args and args[0] == "growth":
>         from content_factory.growth.cli import main as growth_main
>         return growth_main(args[1:])
>     ...  # mevcut kod HİÇ DEĞİŞMEDEN devam eder
> ```
> `content-factory --brand oleart` davranışı birebir korunmalı. `pyproject.toml`'a ikinci
> entry point **eklenmez**.
>
> **`growth/cli.py`** — argparse (typer/click değil, repo argparse kullanıyor):
>
> | Bayrak | Davranış |
> |---|---|
> | `--brand` (zorunlu) | marka |
> | (varsayılan) | Analiz → dashboard → tarayıcı; süreç açık kalır |
> | `--serve` | Analiz yok, sadece dashboard (geçmişi incelemek için) |
> | `--headless` | Dashboard yok; plan üretilir, markdown rapora yazılır |
> | `--stub-collectors` | GA4/GSC yerine deterministik sahte veri |
> | `--inspect-only` | Sadece site denetimi (schema/meta/CTA), metrik yok |
> | `--no-browser` | Tarayıcı açma |
> | `--port N` | Varsayılan 8765 |
>
> Çıkış kodu: başarılı analiz 0, `insufficient_data` veya hata 1.
>
> **Testler:** argüman ayrıştırma; `--headless --stub-collectors` ile uçtan uca çalışma
> (`tmp_path` DB'sine yazar, plan üretir).
>
> **Bitiş kriteri:** `uv run content-factory --brand oleart --dry-run` hâlâ çalışıyor
> (Workflow 1 bozulmamış), `uv run content-factory growth --brand oleart --stub-collectors
> --headless` plan üretiyor.

---

## Adım 9 — Dashboard

> GROWTH_PLAN.md Adım 9'u uygula. Adım 1-8 tamamlanmış olmalı.
>
> FastAPI + Jinja2 + HTMX, `127.0.0.1:8765`. **CDN yok** — CSS ve HTMX yerel `static/`
> altında (repo kuralı: dış ağa bağımlılık yok). Tek kullanıcı + localhost olduğu için
> varsayılan kimlik doğrulama yok; opsiyonel `GROWTH_DASHBOARD_TOKEN` ile cookie koruması.
>
> **Sayfalar:**
>
> | Rota | İçerik |
> |---|---|
> | `/` Overview | "Yeni analiz başlat" butonu, sağlık skoru, dönem-üstü-dönem özet kartları, bekleyen onay sayısı, son çalıştırmalar |
> | `/plans/{id}` Growth Plan | Önceliklendirilmiş öneri listesi; alan sekmeleri: Content · SEO · UX · CRO · Technical · Linking; "kanıt yetersiz" bölümü ayrı |
> | `/findings` Bulgular | Ham `Finding` tablosu, filtrelenebilir |
> | `/pages` Sayfa performansı | GA4 + GSC + site denetimi tek satırda; en çok trafik / en çok çıkış / en düşük CTR sıralamaları |
> | `/opportunities` Fırsatlar | Striking distance, düşük CTR-yüksek impression, yüksek trafik-düşük dönüşüm |
> | `/site` Site denetimi | Schema eksikleri, meta uzunlukları, heading hiyerarşisi, CTA envanteri, orphan sayfalar, alt text kapsaması |
> | `/actions` Aksiyon geçmişi | `growth_actions` + `growth_outcomes` deltaları; tahmin vs gerçekleşen |
> | `/performance` Performance History | Haftalık metrik seyri, inline SVG |
> | `/runs/{id}` Çalışma detayı | `step_history`, node süreleri, LLM maliyet özeti |
>
> **Öneri kartı** (`templates/partials/recommendation.html`): üstte başlık + öncelik
> rozeti; gövdede **Neden** (diagnosis), **Kanıt** (metrik satırları, tıklanınca `Finding`
> detayı), **Önerilen değişiklik** (somut metin), **Beklenen kazanım** (aralık + dayanak),
> **Maliyet** (saat + karmaşıklık), **Risk**. Butonlar: `Approve` · `Reject` · `Edit` ·
> `Ask AI Again` — HTMX partial POST, sayfa yenilenmez.
>
> **Toplu komutlar:** `Approve All`, `Approve Selected`, `Reject Selected`.
>
> **İki gönderim butonu:**
> - "Yeniden değerlendir" → düzenlenmiş öneriler + serbest metin Executive Decision'a
>   döner, yeni revizyon aynı sayfada
> - "Onayla ve çalıştır" → `execute_approved`, yalnızca `approved` olanlar
>
> **Yeni analiz:** `POST /runs` → `runner.run_growth_analysis()` arka plan thread'inde;
> `GET /runs/{id}/progress` HTMX ile 2 sn'de bir yoklanır. Aynı marka için eşzamanlı
> ikinci analiz in-process kilitle engellenir.
>
> **`growth/dashboard/server.py`** — uvicorn'u thread'de başlatan yardımcı; CLI bunu
> kullanır.
>
> **Testler:** `fastapi.testclient` ile rota testleri, onay/red/edit uçları, resume
> tetikleme.
>
> **Bitiş kriteri:** `uv run content-factory growth --brand oleart --stub-collectors` ile
> tarayıcı açılıyor, öneri kartında Neden/Kanıt/Önerilen değişiklik/Beklenen kazanım
> görünüyor, Edit → "Yeniden değerlendir" → revision 2 geliyor.

---

## Adım 10 — Memory + outcome ölçümü

> GROWTH_PLAN.md Adım 10'u uygula. Adım 1-9 tamamlanmış olmalı.
>
> **`growth/memory.py`** — `GrowthMemory(store)`, **LLM yok**, saf agregasyon.
> `build_digest() -> str` çıktısı `content_strategist`, `executive_decision`,
> `seo_strategist` ve `cro_agent` prompt'larına değişken olarak verilir. İçeriği:
> - Öneri türü bazında kabul/red oranı ("son 8 planda `new_article` önerilerinin 5'i
>   reddedildi")
> - Serbest metin geri bildirimlerinde tekrar eden temalar
> - `growth_outcomes` üzerinden **ölçülmüş** etki ("title değişikliği uygulanan 3 sayfada
>   ortalama CTR +%18")
> - Tahmin kalibrasyonu: `expected_gain` vs gerçekleşen
>
> **`measure_outcomes` node'u** — her run'da vadesi gelmiş (`measure_after_days`,
> varsayılan 21) `growth_actions` için hedef sayfaların önce/sonra metriklerini
> `growth_outcomes`'a yazar. Model eğitimi yok — kanıt birikimi var.
>
> **Testler:** digest agregasyonu, önce/sonra delta hesabı, tahmin-gerçekleşen
> kalibrasyonu, vadesi gelmemiş aksiyonun ölçülmediği.
>
> **Bitiş kriteri:** testler geçiyor, digest'in prompt'a gerçekten girdiği agent
> testleriyle doğrulanmış.

---

## Adım 11 — Execution kuyruğu

> GROWTH_PLAN.md Adım 11'i uygula. Adım 1-10 tamamlanmış olmalı.
>
> **`growth/execution/queue.py`** — onaylı önerileri `growth_actions`'a yazar
> (`status="queued"`, `measure_after_days` işaretlenir).
>
> **`growth/execution/runner.py`** — `HANDLERS: dict[RecommendationType, Handler]`
> registry. **Faz 1'de handler'lar no-op**: aksiyonu `queued` bırakır, gerekçesini loglar,
> dashboard'da "uygulanmayı bekliyor" gösterir.
>
> **`growth/execution/handlers/`** — iskelet + `base.py::Handler` protokolü. Gerçek
> handler'lar sonradan tek tek eklenecek; graf hiç değişmeyecek.
>
> **Handler sözleşmesi (şimdiden sabitlenir, sonra ihlal edilmez):**
> - Her handler `SitePolicy.check_target` kontrolünden geçer — `generated`/`forbidden`
>   dosyaya yazamaz, `synchronized` grubu bölemez.
> - Değişiklikler `../oleart.co` içinde **ayrı bir git branch'ine** yazılır, `main`'e
>   dokunulmaz. Dashboard `git diff` gösterir; push/PR kullanıcının açık eylemidir.
>   Gerekçe: `publish.yaml` yorumlarında belgelendiği gibi `GIT_TOKEN`'ın PR izni yok ve
>   arayüz değişikliği makale eklemekten çok daha geniş etkili — otonom push doğru olmaz.
> - `build.triggers` eşleşirse `npm run build:blog` çalıştırılır, çıktı da diff'e girer.
> - Makale değişikliği `content/blog/*.md`'ye yapılır, **asla** `blog/`'a.
>
> **Testler:** kuyruğa yazma, yalnızca `approved` olanların geçtiği, policy ihlalinde
> handler'ın çağrılmadığı, no-op handler'ın aksiyonu `queued` bıraktığı.
>
> **Bitiş kriteri:** testler geçiyor; "Onayla ve çalıştır" sonrası
> `sqlite3 data/oleart/growth.db "select action_type,status from growth_actions;"`
> satırları gösteriyor.

---

## Adım 12 — Dokümantasyon

> GROWTH_PLAN.md Adım 12'yi uygula. Adım 1-11 tamamlanmış olmalı.
>
> **`ARCHITECTURE.md`** — yeni **§19 "Growth Intelligence Platform"**. Mevcut bölümlerin
> üslubunu birebir taklit et: karar tabloları, gerekçe blockquote'ları, Mermaid diyagramı.
> İçermeli: graf yapısı, `GrowthState` modeli, SQLite tablo şeması, **site modeli ve
> policy katmanı**, **kanıt zinciri** (diagnostics → agent → EvidenceGuard),
> **manuel tetikleme gerekçesi** ve scheduler dikişi, Workflow 1'den bağımsızlık garantisi.
>
> **`README.md`** — Google service account kurulum adımları (GCP'de service account →
> Analytics Data API + Search Console API etkinleştir → JSON key → GA4 property'de
> Admin > Property Access Management'a **Viewer** ekle → Search Console > Settings >
> Users and permissions'a **Restricted** ekle; scope'lar `analytics.readonly`,
> `webmasters.readonly`), `uv sync --extra dashboard`, `content-factory growth` kullanımı,
> **yeni bir siteye uygulama rehberi** (`brands/{yeni}/site.yaml` + `growth.yaml` +
> `site_structure.md`), "Durum" ve "Bilinen eksikler" güncellemesi.
>
> **`ROADMAP.md`** — Faz 3 kutularını işaretle, "scheduler bilinçli olarak yok" notunu ekle.
>
> **`.env.example`** — `GOOGLE_SERVICE_ACCOUNT_JSON`, `GA4_PROPERTY_ID`, `GSC_SITE_URL`,
> opsiyonel `GROWTH_DASHBOARD_TOKEN`. Ayrıca mevcut boşluğu kapat: **`GROQ_API_KEY`
> `.env.example`'da yok** ama kod ve CI kullanıyor.
>
> **`knowledge/brands/oleart/site_structure.md`** — LLM'in okuyacağı anlatı katmanı:
> sitenin yapısı, neyin neden üretilmiş olduğu, hangi dosyanın tek kaynak olduğu.
> Kanonik kaynak her zaman `site.yaml`; bu dosya ondan sapamaz.
>
> **Bitiş kriteri:** `uv run pytest` yeşil, `uv run ruff check` temiz, dokümanlar tutarlı.

---

# BÖLÜM 3 — Her adımdan sonra çalıştırılacak doğrulama

```bash
# Regresyon — EN ÖNEMLİ
uv run pytest                                      # 412 + yeni testler, hepsi geçmeli
uv run ruff check
uv run content-factory --brand oleart --dry-run    # Workflow 1 bozulmamış

# Growth (Adım 8'den sonra anlamlı)
uv run pytest tests/growth
uv run content-factory growth --brand oleart --stub-collectors --headless
uv run content-factory growth --brand oleart --inspect-only
cd ../oleart.co && git status --porcelain          # BOŞ olmalı — analiz dosya değiştirmez

sqlite3 data/oleart/growth.db \
  "select ref_no,domain,type,priority,evidence_verified from recommendations;"
sqlite3 data/oleart/growth.db \
  "select metric,observed,expected,source from findings limit 20;"
```
