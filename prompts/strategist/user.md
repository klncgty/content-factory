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

## Uzunluk ve Yapı Kısıtı

Makale $min_word_count-$max_word_count kelime olacak (Editor bunu deterministik denetler).
Yazar her bölümü ortalama ~180 kelime yazıyor; bu yüzden outline **en az $min_sections
bölüm** içermeli. Daha az bölümlü bir outline, yazarın alt sınırın altında kalmasına ve
makalenin reddedilmesine yol açıyor. `target_word_count` alanına $target_word_count yaz.

## Görev

Yalnızca şu JSON şemasına uyan bir nesne döndür, başka hiçbir açıklama ekleme:

```json
{
  "title": "makale başlığı",
  "target_keyword": "hedef anahtar kelime",
  "secondary_keywords": ["ikincil kelime 1", "ikincil kelime 2"],
  "audience": "hedef kitle özeti",
  "tone": "ton özeti",
  "target_word_count": 1000,
  "outline": [
    {"heading": "Bölüm başlığı", "summary": "bu bölümde ele alınacakların özeti"}
  ],
  "suggested_internal_links": ["ilgili olabilecek konu/ürün anahtar kelimesi"]
}
```
