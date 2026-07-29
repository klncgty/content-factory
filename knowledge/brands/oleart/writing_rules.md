# Oleart — Yazım Kuralları

> WriterAgent ve SEOOptimizerAgent tarafından okunur. Deterministik/ölçülebilir kurallar
> (kelime sayısı, yasaklı kelimeler) `brands/oleart/brand.yaml` içinde kod ile de
> doğrulanır; burası biçim/üslup kurallarının insan-okunur açıklamasıdır. Üslup için
> `tone.md`, biçimsel tercihler için `style_guide.md` tamamlayıcıdır.

## Uzunluk
- Hedef aralık **800-1500 kelime** (kanonik kaynak: `brand.yaml: content_bounds`).
- Uzunluk bir hedef değil, sonuçtur: konu 900 kelimede bitiyorsa şişirilmez. Dolgu
  paragrafı, tekrar ve "özetin özeti" bölümleri EditorAgent tarafından reddedilir.

## Yapı
- H1 başlık + **en az 3 H2** alt başlık; gerekirse H3 kırılımı.
- **Giriş paragrafı 2-3 cümlede okuyucunun sorusunu netleştirir ve mümkünse kısa cevabı
  hemen verir.** Süslü/şiirsel açılış yapılmaz (bkz. `tone.md` — "böyle yazmayız").
- Kısa paragraflar (3-4 cümle); uygun yerlerde madde listesi veya küçük tablo.
- Sonuç bölümü: konunun özeti veya tek bir eylem çağrısı. Her ikisi birden değil.

## Bilgi ve Doğruluk (en kritik bölüm)
- **Sayısal her iddia** (sıcaklık, oran, süre, yüzde, yıl) knowledge dosyalarında
  bulunmalıdır: `olive_oil.md`, `olive_tree.md`, `kitchen_products.md`. Orada yoksa
  **yazılmaz** — tahmin edilmez, yuvarlanmaz, "yaklaşık" denerek uydurulmaz.
- Araştırma notlarında (ResearchAgent çıktısı) geçmeyen bir gerçek makaleye girmez.
- Kaynak uydurma yasaktır (bkz. `sources.md`).
- Emin olunmayan bilgi "muhtemelen / denilir / bilinir" ile geçiştirilmez; ya doğrulanır
  ya da makaleye alınmaz.
- Marka hakkında `brand.md` ve `products.md`'de olmayan hiçbir bilgi yazılmaz — Oleart'ın
  hasat bölgesi, çeşidi, üretim süreci ve ahşap ürün detayları **bilinmiyor**.

## Yasaklar
- Kaynaksız sağlık/tedavi iddiası (bkz. `forbidden_claims.md`, `legal_rules.md`)
- Kanıtsız üstünlük ifadeleri: "en iyi", "eşsiz", "rakipsiz", "mucize", "kesin çözüm",
  "%100 garanti" (`brand.yaml: forbidden_words` ile kod düzeyinde de kontrol edilir)
- Rakip marka adı
- Uydurma istatistik veya kaynak
- Fiyat/stok bilgisi (blog kalıcıdır, fiyat değişir — bkz. `products.md`, `legal_rules.md`)
- E-ticaret CTA'ları ("sepete ekle", "hemen satın al") — Oleart'ın sepeti yok
- Emoji

## Yaygın Hataların Düzeltilmesi
Oleart blogunun ayırt edici değeri, tüketicinin yanlış bildiği şeyleri **doğru ve
kaynaklı** anlatmasıdır. Bunu yaparken:
- Yanlış inanç önce tarafsızca aktarılır, sonra düzeltilir; okuyucu küçümsenmez.
- Düzeltme mutlaka bir dayanağa bağlanır (bkz. `olive_oil.md` §5, `kitchen_products.md` §3).

## SEO (özet — ayrıntı `seo_rules.md`)
- Hedef anahtar kelime: başlıkta, ilk paragrafta ve en az bir H2'de doğal şekilde geçer.
- Anahtar kelime doldurma yapılmaz.
- Slug kısa, kelime bazlı, Türkçe karakter içermez (ör. `zeytinyagi-donar-mi`).
