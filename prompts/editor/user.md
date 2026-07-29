## Marka Sesi

$tone

## Yazım Kuralları

$writing_rules

## İçerik Kapsamı

$content_scope

## Yasaklı Kelimeler

$forbidden_words

## Yasaklı İddialar

$forbidden_claims

Not: Bu listelerin birebir geçtiği yerler zaten otomatik olarak yakalanıyor. Senin işin
**dolaylı/eşanlamlı** ihlalleri bulmak — ör. "mucize" yazmadan mucizevi etki ima etmek,
ya da kaynak göstermeden klinik/istatistiksel bir sağlık iddiasında bulunmak.

## Makale

$article_body

## Görev

Yalnızca şu JSON şemasına uyan bir nesne döndür, başka hiçbir açıklama ekleme:

```json
{
  "decision": "approved",
  "reasons": ["gerekçe veya düzeltme talebi (varsa)"]
}
```

`decision` yalnızca `"approved"` veya `"rejected"` olabilir.
