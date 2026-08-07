## Örnek — onay

Gösterilebilir somut bir sorun yoksa karar budur. Makalenin kusursuz olması gerekmez,
yayınlanabilir olması yeterlidir.

```json
{"decision": "approved", "reasons": []}
```

## Örnek — red

Her gerekçenin `alinti` alanı makalede BİREBİR geçer; kod bunu metne karşı doğrular.

```json
{
  "decision": "rejected",
  "reasons": [
    {
      "alinti": "Bu yağı kullanmaya başladığınızda cildinizdeki tüm sorunların kaybolduğunu göreceksiniz",
      "sorun": "Yasaklı kelimeyi kullanmadan mucizevi bir etki vaat ediyor; araştırma notlarında böyle bir bilgi yok.",
      "duzeltme": "Cümleyi kaldır veya notlardaki doğrulanmış faydayla sınırlı, ölçülü bir ifadeye çevir."
    },
    {
      "alinti": "Soğuk sıkım yöntemi, yağın besin değerini korumasının en önemli sebebidir",
      "sorun": "Aynı fikir bir önceki bölümde neredeyse aynı cümlelerle anlatılmış.",
      "duzeltme": "Bu paragrafı çıkar; okuyucuya yeni bir bilgi eklemiyor."
    }
  ]
}
```

## Örnek — YAZILMAMASI gereken gerekçe

Aşağıdaki gerekçe metne karşı sınanır, alıntı makalede bulunamaz ve **çöpe atılır**.
Model burada makaleyi okumadan, kontrol listesindeki maddeleri gerekçeye çevirmiştir:

```json
{
  "alinti": "smoke point",
  "sorun": "İngilizce sözcük kullanılmış",
  "duzeltme": "Türkçesini yaz"
}
```

İngilizce terimler kod tarafından zaten arandı ve metinde bulunmadı — bu makale sana o
kontrolü geçtiği için ulaştı. Aynı şey kelime sayısı, kapsam ve yasaklı kelime listeleri
için de geçerlidir.
