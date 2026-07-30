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

## Araştırma Notları (doğru kabul edilen tek bilgi kaynağı)

$key_facts

Makaledeki somut/sayısal iddiaları bu listeyle karşılaştır: bir iddia burada YOKSA ve
genel bilgiyle de doğrulanamıyorsa, muhtemelen uydurmadır — reddet ve hangi cümlenin
kaynaksız olduğunu `reasons`'da belirt.

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
