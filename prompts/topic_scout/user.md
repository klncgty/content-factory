## Marka Bilgisi

$brand_overview

## Ürünler

$products

## Hedef Anahtar Kelime Kümeleri

$seed_keyword_clusters

## Daha Önce Kullanılmış Anahtar Kelimeler (bunlarla örtüşen konu ÖNERME)

$used_keywords

## Zaten Yayınlanmış Makaleler (bu konuları TEKRAR ETME)

$published_titles

Bir konuyu farklı kelimelerle yeniden yazmak da tekrardır: "X'in faydaları" yayınlandıysa
"X nasıl kullanılır" YENİ BİR KONU DEĞİLDİR. Yukarıdaki listeden farklı bir konu ekseni
seç ve markanın iki ürün grubunu (zeytin/zeytinyağı ve zeytin ağacından ahşap ürünler)
dengeli kullan — son yayınlar hangi gruptaysa diğer gruba ağırlık ver.

## Görev

$max_candidates adet aday konu üret. Her biri için:
- `title`: SEO'ya uygun, aranabilir bir başlık (Türkçe)
- `category`: içerik kapsamındaki grup id'si (`olive_and_oil` veya `wooden_products`)
- `seed_keywords`: bu konuyla ilişkili 2-5 anahtar kelime
- `score`: 0.0-1.0 arası, konunun SEO değeri + markaya uygunluğu tahmini
- `rationale`: bu konuyu neden önerdiğinin tek cümlelik gerekçesi

Yalnızca şu JSON şemasına uyan bir dizi döndür, başka hiçbir açıklama ekleme:

```json
[
  {"title": "...", "category": "...", "seed_keywords": ["..."], "score": 0.0, "rationale": "..."}
]
```
