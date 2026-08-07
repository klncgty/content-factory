## Marka Sesi

$tone

## Yazım Kuralları

$writing_rules

## Yasaklı Kelimeler/İfadeler (kesinlikle kullanma)

$forbidden_words

## Makale Planı

Başlık: $title
Hedef kelime: $target_keyword
Hedef kitle: $audience
Hedef uzunluk: yaklaşık $target_word_count kelime
Uzunluk sınırları (Editor bunları deterministik olarak denetler, ihlal reddedilir):
en az $min_word_count, en fazla $max_word_count kelime.

Bölüm başına bütçe: outline'daki her `##` bölümü **yaklaşık $words_per_section kelime**
olmalı. Bunu tutturmanın yolu yapıdır: her bölümde **en az 2 paragraf**, her paragrafta
**3-5 tam cümle** yaz. Tek cümlelik veya tek paragraflık bölüm yazma; bir bölümü kısa
geçersen makale alt sınırın altında kalır ve makale reddedilir.

Outline'daki bölümlerin HEPSİNİ yaz — bölüm atlama veya birleştirme.

Outline:
$outline

## Araştırma Notları (yalnızca bunlara dayan)

$key_facts

## Önceki Deneme Geri Bildirimi (varsa, mutlaka uygula)

Her satır `«metinden alıntı» — sorun. Düzeltme: ne yapılacağı` biçimindedir. Alıntı,
önceki taslakta **birebir** geçen ve düzeltilmesi gereken yerdir: o yeri metinde bul ve
yalnızca orayı, söylenen düzeltmeye göre değiştir. Geri bildirimdeki HER satırı uygula —
birini atlarsan makale aynı gerekçeyle yeniden reddedilir.

$feedback

## Reddedilen Önceki Taslak

$previous_draft

## Görev

Önceki taslak yoksa: yukarıdaki plana göre makalenin tam gövde metnini, düz markdown
olarak yaz.

Önceki taslak varsa: onu SIFIRDAN YAZMA, **revize et**. Yalnızca geri bildirimde
belirtilen yerlere dokun; geri bildirimde geçmeyen bölümleri, cümleleri ve genel
uzunluğu olduğu gibi koru. Bir bölümü kısaltman veya silmen gerekiyorsa, kaybolan
uzunluğu diğer bölümleri derinleştirerek telafi et — sonuç yine yukarıdaki kelime
sınırları içinde kalmalıdır. Çıktın, kısmi bir düzeltme değil, makalenin revize
edilmiş TAM gövdesi olsun.

Geri bildirim makalenin KISA olduğunu söylüyorsa: önceki taslağı olduğu gibi temel al,
hiçbir cümleyi silme veya özetleme; her `##` bölümüne araştırma notlarına dayanan yeni
paragraflar ekleyerek genişlet. Çıktının kelime sayısı önceki taslaktan AZ OLAMAZ.
