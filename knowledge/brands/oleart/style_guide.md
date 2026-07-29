# Biçim / Stil Rehberi

> `writing_rules.md`'den farkı: `writing_rules.md` *kurallar* (yapılacak/yapılmayacaklar)
> içerir, bu dosya *biçimsel* tercihleri (noktalama, sayı yazımı, terminoloji) içerir.
> WriterAgent ve SEOOptimizerAgent birlikte okur.

## Terminoloji Tutarlılığı
- "Zeytinyağı" bitişik yazılır (ör. "zeytin yağı" değil)
- **"natürel sızma zeytinyağı"** yazımı kullanılır ("naturel" değil) — Türk Gıda
  Kodeksi'ndeki resmi terim budur (bkz. `olive_oil.md` §1). Site "doğal sızma" dese de
  teknik anlatımda resmi terim geçerlidir; sitedeki ürün ifadesine atıf yapılırken
  özgün yazım korunabilir (bkz. `products.md`)
- Ürün adları her zaman `products.md`/`kitchen_products.md`'deki resmi adla birebir
  aynı yazılır

## Sayı ve Ölçü Birimleri
- Sıcaklık: "6-8°C" formatı (boşluksuz derece işareti)
- Ağırlık/hacim: "5 litre", "350 TL/kg" formatı (bkz. mevcut ürün açıklamaları)

## Noktalama ve Biçim
- Türkçe tırnak işaretleri yerine düz tırnak (" ") kullanılabilir (markdown uyumluluğu
  için) — kod bloklarında/URL'lerde tırnak kullanılmaz
- Emoji kullanılmaz (marka sesi bilgilendirici/güven verici, samimi ama "casual" değil
  — bkz. `tone.md`)
- Başlıklarda Türkçe büyük harf kuralları geçerli (her kelimenin baş harfi değil,
  yalnızca cümle başı ve özel isimler büyük)

## Rakam Yazımı
- **Ölçü, oran ve teknik değerler her zaman rakamla:** "27°C", "5 litre", "0,8",
  "18-24 ay", "3 alt başlık"
- **Ölçü olmayan, metin akışındaki küçük sayılar yazıyla:** "iki farklı yöntem",
  "üç adımda"
- Ondalık ayırıcı **virgül**dür: "0,8" ("0.8" değil)
- Aralıklar kısa çizgiyle ve boşluksuz yazılır: "18-24 ay", "190-210°C"

## Tarih Formatı
- Metin içinde uzun format: "1 Ağustos 2026" — oleart.co `scripts/build-blog.mjs`
  bu formatı zaten kullanıyor, tutarlı kalınmalı
- Dosya adı/frontmatter'da ISO format: `2026-08-01` (yayın sözleşmesi gereği,
  bkz. `ARCHITECTURE.md` §6)
