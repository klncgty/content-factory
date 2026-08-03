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
"X nasıl kullanılır" YENİ BİR KONU DEĞİLDİR. Başa sıfat eklemek de yeni konu yapmaz:
"A Ürünü ile X Yapmak" yayınlandıysa "B Ürünü ile X Yapma Teknikleri" AYNI KONUDUR ve
elenir. Yukarıdaki listeden farklı bir konu ekseni
seç ve markanın ürün gruplarını dengeli kullan — son yayınlar hangi gruptaysa diğer
gruba ağırlık ver.

Tekrardan kaçınmanın en güvenilir yolu somut olmaktır: her tarif farklı bir yemeği
anlattığı için doğal olarak yeni bir konudur. Yukarıdaki anahtar kelime kümelerinde
verilen yemeklerden HENÜZ YAZILMAMIŞ olanlara öncelik ver.

## Görev

$max_candidates adet aday konu üret. Her biri için:
- `title`: SEO'ya uygun, aranabilir bir başlık (Türkçe)
- `category`: yukarıdaki "Hedef Anahtar Kelime Kümeleri" bölümünde geçen grup id'si
- `seed_keywords`: bu konuyla ilişkili 2-5 anahtar kelime
- `score`: 0.0-1.0 arası, konunun SEO değeri + markaya uygunluğu tahmini
- `rationale`: bu konuyu neden önerdiğinin tek cümlelik gerekçesi

Yalnızca şu JSON şemasına uyan bir dizi döndür, başka hiçbir açıklama ekleme:

```json
[
  {"title": "...", "category": "...", "seed_keywords": ["..."], "score": 0.0, "rationale": "..."}
]
```
