## Konu

Başlık: $topic_title
Kategori: $topic_category
Anahtar kelimeler: $seed_keywords

## Araştırma Notları

Gerçekler:
$key_facts

Önerilen bakış açısı: $suggested_angle

## Hedef Kitle

$target_audience

## Yazım Kuralları (özet)

$writing_rules_summary

## İçerik Tipi ve Uzunluk Kısıtı

Önce bu konunun hangi içerik tipi olduğuna karar ver. Uzunluk ve bölüm sayısı kısıtı
seçtiğin tipe göre değişir:

$content_types

Tiplerden hiçbiri uymuyorsa `content_type` alanını boş bırak; o durumda makale
$default_min_word_count-$default_max_word_count kelime olur.

Outline'ı **seçtiğin tipin satırına göre** kur. Yazar her bölümü ortalama ~180 kelime
yazıyor, yani bölüm sayısı makalenin uzunluğunu belirleyen asıl kaldıraç:

- Bölüm sayısı satırdaki **aralığın içinde** kalmalı. Aralığın altı, yazarın alt sınırın
  altında kalmasına ve makalenin reddedilmesine yol açar; üstü ise üst sınırı aşırıp
  makaleyi yine reddettirir.
- Aralığın üst ucunu hedef sanma. Anlatacak şeyi olan bölümler yaz; her bölüm okura yeni
  bir şey vermeli. Dolgu bölüm eklemek makaleyi iyileştirmez.

Doğru tipi seçmek önemli: bir tarifi rehber sanıp uzun bir outline kurarsan yazar
boşluğu dolgu paragraflarla doldurur.

## Görev

Yalnızca şu JSON şemasına uyan bir nesne döndür, başka hiçbir açıklama ekleme:

```json
{
  "title": "makale başlığı",
  "target_keyword": "hedef anahtar kelime",
  "content_type": "yukarıdaki listeden bir tip adı, ya da boş",
  "secondary_keywords": ["ikincil kelime 1", "ikincil kelime 2"],
  "audience": "hedef kitle özeti",
  "tone": "ton özeti",
  "outline": [
    {"heading": "Bölüm başlığı", "summary": "bu bölümde ele alınacakların özeti"}
  ],
  "suggested_internal_links": ["ilgili olabilecek konu/ürün anahtar kelimesi"]
}
```

`content_type` yalnızca yukarıdaki listede geçen adlardan biri olabilir; yeni bir tip adı
uydurma.
