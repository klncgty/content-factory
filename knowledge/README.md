# Knowledge Base

Content Factory'deki tüm agent'ların ortak, tip güvenli bilgi kaynağı. Hiçbir agent
marka bilgisini (kim olduğu, ürünleri, sesi, kuralları) kendi kodunda veya prompt
string'inde taşımaz — hepsi bu dizinden `KnowledgeLoader` aracılığıyla okur.

## Neden ayrı bir sistem (config'ten farklı olarak)?

Content-factory'de iki farklı "marka bilgisi" katmanı vardır ve bu **bilinçli bir
ayrımdır**:

| | Konum | Format | Kim okur | Amaç |
|---|---|---|---|---|
| **Yapılandırılmış/deterministik kurallar** | `brands/{brand}/*.yaml` | YAML | Kod (`ScopeGuard`, `EditorAgent`, vb.) | Makine tarafından **doğrulanabilir** kurallar: kelime sayısı sınırı, yasaklı kelime listesi, kapsam allowlist'i |
| **Anlatısal/bağlamsal bilgi** | `knowledge/brands/{brand}/*.md` | Markdown | LLM (agent'ların prompt bağlamı) | İnsan-okunur, nüanslı bilgi: marka hikayesi, ürün detayları, ton örnekleri |

Bazı konular her iki katmanda da görünür (ör. içerik kapsamı: `scope.yaml` +
`content_scope.md`; yasaklı iddialar: `brand.yaml` + `forbidden_claims.md`). Bu
**kasıtlı bir çoğullama değil, tutarlılığı test edilen bir eşlemedir**:
`brands/{brand}/*.yaml` her zaman kanonik/enforcement kaynağıdır;
`knowledge/brands/{brand}/*.md` aynı bilgiyi LLM'e *neden* diye açıklamak için
yeniden ifade eder. `tests/test_knowledge.py` bu ikisinin senkron kalmasını
otomatik doğrular (`test_content_scope_matches_scope_yaml`,
`test_forbidden_claims_matches_brand_yaml`) — `scope.yaml`'ı güncelleyip
`content_scope.md`'yi unutursan test kırılır.

## Dizin yapısı

```
knowledge/
├── README.md              # bu dosya
└── brands/
    └── oleart/
        ├── brand.md            # marka kimliği: kim, misyon, vizyon, değerler
        ├── products.md          # satılan tüm ürün kategorileri
        ├── olive_oil.md          # zeytinyağı hakkında doğrulanmış bilgi
        ├── olive_tree.md          # zeytin ağacı hakkında bilgi
        ├── kitchen_products.md     # zeytin ağacından mutfak ürünleri
        ├── faq.md                   # sık sorulan sorular
        ├── writing_rules.md          # yazım standartları
        ├── seo_rules.md                # blog SEO standartları
        ├── content_scope.md             # içerik kapsamı (kanonik: scope.yaml)
        ├── internal_linking.md           # iç link kuralları
        ├── legal_rules.md                  # yasal/regülasyon kuralları
        ├── forbidden_claims.md              # yasaklı ifadeler (kanonik: brand.yaml)
        ├── target_audience.md                 # hedef müşteri profilleri
        ├── tone.md                              # marka sesi
        ├── style_guide.md                         # biçimsel/stilistik tercihler
        └── sources.md                               # güvenilir kaynak politikası
```

Bu dosyalar iki gruba ayrılır:

- **Motor dosyaları** (ton, yazım kuralları, hedef kitle…): her markada bulunur, listesi
  `src/content_factory/knowledge/loader.py::CORE_FILES` içinde sabittir. Yeni bir tane
  eklemek için oraya bir `KnowledgeFileSpec`, `BrandKnowledge`'a karşılık gelen alanı ve
  `get_*()` metodunu eklemek yeterlidir.
- **Markanın konusuna özgü dosyalar** (Oleart için `olive_oil.md`, `olive_tree.md`,
  `kitchen_products.md`): Python'da DEĞİL, `brands/{marka}/knowledge.yaml: topic_files`
  içinde tanımlanır ve `knowledge.get_topic("olive_oil")` / `compose("olive_oil")` ile
  okunur. Böylece bambaşka bir konudaki ikinci marka çekirdek koda dokunmadan eklenebilir.

Geri kalan her şey (cache, validate, compose) bu kayıtlardan otomatik türer.

## Kullanım (agent kodu içinden)

Agent'lar dosyaları asla doğrudan okumaz; `AgentContext.knowledge` üzerinden enjekte
edilen `BrandKnowledge` nesnesini kullanır:

```python
class WriterAgent(BaseAgent[WriterInput, Article]):
    name = "writer"

    def run(self, input_data: WriterInput) -> Article:
        kb = self.context.knowledge
        system_context = kb.compose("brand_overview", "tone", "writing_rules", "olive_oil")
        forbidden = kb.get_forbidden_claims()
        ...
```

`compose()` birden fazla bölümü, aralarında başlıklarla tek bir prompt-hazır metinde
birleştirir — dosya adlarıyla değil, tip güvenli alan adlarıyla çalışır.

## Cache

`KnowledgeLoader`, bir markanın dosyalarını yalnızca ilk `load(brand)` çağrısında
diskten okur; sonraki çağrılar bellekten (thread-safe) döner:

```python
loader = KnowledgeLoader()          # kökü otomatik bulur (CONTENT_FACTORY_ROOT ile override edilebilir)
kb = loader.load("oleart")          # diskten okur, cache'ler
kb2 = loader.load("oleart")         # cache'ten döner (kb is kb2)

loader.invalidate("oleart")         # yalnızca oleart'ı cache'ten düşürür
loader.invalidate()                 # tüm markaların cache'ini temizler
loader.load("oleart", force_reload=True)  # cache'i atlayıp yeniden okur
```

`Orchestrator`, bir pipeline run'ı başlamadan önce `load()` çağırır; run içinde
tekrar tekrar dosya I/O yapılmaz.

## Validation

Eksik/boş/doldurulmamış dosyaları tespit etmek için:

```python
report = loader.validate("oleart")
report.is_valid          # False ise en az bir dosya eksik veya boş
report.has_placeholders  # True ise en az bir dosya hâlâ "Faz 0 çıktısı" şablonunda
report.issues            # KnowledgeValidationIssue listesi (file, kind, detail)
```

`kind` üç değer alabilir: `"missing"` (dosya yok), `"empty"` (dosya boş),
`"placeholder"` (dosya var ama hâlâ doldurulmamış şablon içeriyor — henüz gerçek
marka içeriğiyle değiştirilmemiş). Yalnızca `missing`/`empty` `is_valid`'i düşürür;
`placeholder` ayrı takip edilir — pipeline'ı durdurmaz ama içerik kalitesini doğrudan
etkiler.

**oleart için Faz 0 tamamlandı:** 16 dosyanın hepsi gerçek içerikle dolu,
`has_placeholders` artık `False`. `tests/test_knowledge.py` bunu regresyon olarak
koruyor — yeni bir markanın iskelet dosyaları yanlışlıkla oleart'ın yerine geçerse
test kırılır.

## Yeni bir marka ekleme

Content Factory çoklu-marka olacak şekilde tasarlandı (bkz. ARCHITECTURE.md §10).
Yeni bir marka eklemek **çekirdek koda dokunmadan** yapılabilmelidir:

1. `knowledge/brands/{yeni_marka}/` dizinini oluştur.
2. `CORE_FILES`'taki motor dosyalarının hepsini oluştur (boş bırakma — en azından bu
   README'deki placeholder formatını kullan: `> Faz 0 çıktısı: ...` ile başlayan bir
   not, doldurulacak başlıkların listesi), ayrıca markanın konusuna özgü dosyaları ekle.
3. `brands/{yeni_marka}/` altına `brand.yaml`, `scope.yaml`, `publish.yaml`,
   `seo.yaml`, `schedule.yaml` ve `knowledge.yaml` dosyalarını ekle (bkz. `brands/oleart/`
   örnek olarak). `knowledge.yaml` markanın konu dosyalarını, kategori->knowledge
   eşlemesini ve görsel sahnelerini tanımlar — bunlar eskiden Python'da sabitti.
4. Markaya özgü prompt metni gerekiyorsa `brands/{yeni_marka}/prompts/{agent}/system.md`
   ekle. Ortak `prompts/` dosyaları marka-nötrdür; override DOSYA bazında çalışır, yani
   yalnızca `system.md`'yi ezip `user.md`'yi ortak bırakabilirsin.
4. `content_scope.md`'nin `scope.yaml` ile, `forbidden_claims.md`'nin `brand.yaml`
   ile tutarlı olduğunu doğrulamak için testleri çalıştır:
   ```bash
   uv run pytest tests/test_knowledge.py tests/test_settings.py -v
   ```
   (Testler şu an yalnızca `"oleart"` markasını parametrize ediyor; yeni marka
   eklerken bu testlere ikinci bir parametre seti eklemek de gerekir.)
5. `loader.validate("{yeni_marka}")` ile eksik dosya kalmadığını doğrula.

Hiçbir agent kodu, `src/content_factory/` altındaki hiçbir dosya, yeni marka için
değiştirilmez.

## Test

`tests/test_knowledge.py`: registry bütünlüğü, yükleme, tip güvenli getter'lar,
eksik dosya toleransı, cache/invalidate davranışı, validation, `compose()`, ve
`scope.yaml`/`brand.yaml` ile tutarlılık (drift guard) testleri.
