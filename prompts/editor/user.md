## Marka Sesi

$tone

## Yazım Kuralları

$writing_rules

## Yasaklı Kelimeler

$forbidden_words

## Yasaklı İddialar

$forbidden_claims

Not: Bu iki listenin metinde birebir geçtiği yerler kod tarafından zaten arandı ve
bulunmadı. Bu listeler sana yalnızca **örtük** ihlalleri tanıyabilmen için veriliyor:
yasaklı kelimeyi yazmadan aynı anlamı ima eden bir cümle (ör. "mucize" demeden mucizevi
bir etki vaat etmek) ya da kaynak göstermeden klinik/istatistiksel bir sağlık iddiası.
Listedeki bir ifadenin metinde geçtiğini iddia etme — geçmiyor.

## Araştırma Notları (doğru kabul edilen tek bilgi kaynağı)

$key_facts

Makaledeki somut/sayısal iddiaları bu listeyle karşılaştır. Bir iddia burada YOKSA ve
genel bilgiyle de doğrulanamıyorsa, o cümleyi alıntılayarak reddet.

## Makale

$article_body

## Görev

Makaleyi incele ve YALNIZCA aşağıdaki JSON şemasına uyan tek bir nesne döndür. Öncesine
veya sonrasına açıklama, başlık, markdown yazma.

```json
{
  "decision": "approved",
  "reasons": []
}
```

Reddediyorsan her gerekçe şu üç alanı taşımalıdır:

```json
{
  "decision": "rejected",
  "reasons": [
    {
      "alinti": "makaleden birebir kopyalanmış cümle veya cümle parçası",
      "sorun": "bu alıntının nesi yanlış (Türkçe)",
      "duzeltme": "yazarın uygulayacağı somut talimat (Türkçe)"
    }
  ]
}
```

`decision` yalnızca `"approved"` veya `"rejected"` olabilir.

`alinti` alanı makalede birebir geçmek zorundadır ve kod tarafından metne karşı
doğrulanır. Doğrulanamayan gerekçe karara katılmaz; alıntısını gösteremediğin bir sorun
için gerekçe yazma. Gösterebileceğin somut bir sorun yoksa `approved` döndür.
