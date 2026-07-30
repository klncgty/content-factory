# İçerik Kapsamı — EN KRİTİK DOSYA

> **Kanonik kaynak `brands/oleart/scope.yaml`'dır.** `ScopeGuard` (deterministik
> pre-check + LLM post-check) her zaman `scope.yaml`'a karşı çalışır — bu dosya değil.
> Bu dosya, aynı kapsamı agent'ların prompt bağlamına insan-okunur biçimde vermek
> içindir. **Buradaki liste `scope.yaml` ile birebir tutarlı olmalıdır** —
> `tests/test_knowledge.py::test_content_scope_matches_scope_yaml` bunu otomatik
> doğrular; `scope.yaml`'ı güncelleyip burayı unutursan test kırılır.

Oleart Content Factory **yalnızca** aşağıdaki konularda içerik üretebilir. Bu kapsamın
dışındaki hiçbir konu — ne kadar ilgili görünürse görünsün — işlenmez.

## Zeytin ve Zeytinyağı
- Zeytinyağı
- Trilye zeytini
- Trilye zeytinyağı
- Zeytin
- Zeytin ağacı
- Zeytin yetiştiriciliği
- Zeytin hasadı
- Soğuk sıkım
- Erken hasat
- Natürel sızma zeytinyağı
- Zeytinyağının kullanım alanları
- Zeytinyağının saklanması
- Zeytinyağı ile yapılan tarifler
- Zeytin çeşitleri

## Zeytin Ağacından Ahşap Ürünler

Tekil ve çoğul biçimler ayrı ayrı listelenir: eşleşme birebir alt dize aramasıdır ve
Türkçe eklemeli bir dil olduğu için yalnızca "kesme tahtaları" yazılıyken "kesme tahtası"
geçen bir başlık bu grupla eşleşmiyor, "zeytin ağacı" ifadesi üzerinden yanlışlıkla
zeytinyağı grubuna düşüyordu.

- Zeytin ağacı kesme tahtaları
- Zeytin ağacı kesme tahtası
- Zeytin ağacı sunum tahtaları
- Zeytin ağacı sunum tahtası
- Zeytin ağacı mutfak gereçleri
- Zeytin ağacı kaşıklar
- Zeytin ağacı kaşığı
- Zeytin ağacı spatulalar
- Zeytin ağacı spatulası
- Zeytin ağacı servis ürünleri
- Zeytin ağacı servis ürünü
- Zeytin ağacı bakım rehberleri
- Ahşap kesme tahtası
- Ahşap mutfak gereçleri

## Kapsam Dışı Örnekler (reddedilir)
- Zeytinyağı bağlamı olmadan genel sağlık/diyet tavsiyeleri
- Ayçiçek yağı, kanola yağı gibi diğer yağ türleri
- Zeytin/ahşapla ilgisiz genel mutfak ürünleri
- Genel yaşam tarzı, seyahat, moda içerikleri
- Zeytinyağı temel malzeme değilse, Oleart ürünleriyle ilgisi olmayan tarifler

## Neden Bu Kadar Katı?
Oleart bir zeytin/zeytinyağı ve zeytin ağacından ahşap ürün markasıdır — kapsam dışı
içerik hem SEO otoritesini sulandırır hem de marka güvenilirliğini zedeler. Bu yüzden
kapsam kontrolü tek bir agent'ın "iyi niyetine" bırakılmaz; ScopeGuard'ın iki bağımsız
katmanıyla (bkz. ARCHITECTURE.md §2) mimari seviyede garanti edilir.
