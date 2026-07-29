# Blog SEO Standartları

> SEOOptimizerAgent bu dosyayı okur; sayısal/yapısal kurallar `brands/oleart/seo.yaml`
> içinde de config olarak tutulur (agent'ın deterministik kontrol yapabilmesi için) —
> burası bu kuralların *neden*ini ve nüansını taşır.

## Başlık ve Meta
- Meta title 50-60 karakter, hedef anahtar kelimeyi başta içerir
- Meta description 150-160 karakter, tıklamayı teşvik eden ama tıklama tuzağı
  olmayan bir özet
- Slug: kısa, kelime bazlı, Türkçe karakter içermez (bkz. `writing_rules.md`)

## Başlık Hiyerarşisi
- Tek bir H1 (makale başlığı)
- En az 3 H2, gerekirse H3 alt kırılım — İçindekiler bunlardan otomatik üretilir
  (bkz. oleart.co `scripts/build-blog.mjs`)

## Anahtar Kelime Kullanımı
- Hedef anahtar kelime: başlıkta, ilk paragrafta, en az bir H2'de doğal şekilde geçmeli
- Anahtar kelime doldurma (keyword stuffing) yasak — bkz. `writing_rules.md`
- İkincil anahtar kelimeler zorlama olmadan, bağlam uygunsa kullanılır

## Yapısal Veri
- Her makalede `Article` + `BreadcrumbList` JSON-LD zorunlu (oleart.co tarafında
  otomatik üretiliyor, bkz. `../../../oleart.co/scripts/build-blog.mjs`)
- SSS içeren makalelerde `faq.md`'den derlenen sorular `FAQPage` şemasına uygun
  yapılandırılabilir (Faz 1)

## Cadence ve Kannibalizasyon
- Yayın sıklığı ve hedef kelime kümeleri `seo.yaml`'da tanımlı
- Aynı hedef kelimenin iki makalede kullanılmaması SQLite `keywords` tablosuyla
  deterministik kontrol edilir (StrategistAgent, ScopeGuard değil)
