# Yasal / Regülasyon Kuralları

> **Bu dosya hukuki görüş değildir.** İçerik üretimini güvenli tarafta tutmak için
> konulmuş operasyonel kısıtlardır; nihai gözden geçirme bir hukuk danışmanı tarafından
> yapılmalıdır (bkz. `ROADMAP.md` Faz 0). Şüphe halinde kural nettir: **iddiayı yazma.**
>
> `forbidden_claims.md` ile örtüşür ama daha geniştir: reklam, etiketleme, coğrafi işaret
> ve tüketici mevzuatını kapsar.

## 1. Sağlık ve Beslenme Beyanları (en yüksek risk)

- Gıdalara ilişkin beslenme ve sağlık beyanları Türkiye'de **Türk Gıda Kodeksi Beslenme
  ve Sağlık Beyanları Yönetmeliği** kapsamındadır ve yalnızca izin verilen beyanlar,
  izin verilen koşullarla kullanılabilir.
- **Kesin kural:** Oleart içeriklerinde hastalık önleme/iyileştirme/tedavi iddiası
  **hiçbir biçimde** kullanılmaz. Dolaylı ima da buna dahildir ("kalbinizi koruyun",
  "bağışıklığınızı destekleyin" gibi).
- Sayısal sağlık iddiası ("%X azaltır", "Y kat daha faydalı") **yazılmaz.**
- Yazılabilir olan: zeytinyağının Akdeniz mutfağının temel bileşeni olduğu, tekli
  doymamış yağ asidi bakımından zengin olduğu gibi genel, yerleşik ve iddiasız bilgiler
  (bkz. `olive_oil.md` §7).

## 2. Etiket ve Niteleme İbareleri

- **"Organik":** Türkiye'de organik tarım mevzuatına tabi, **sertifikaya bağlı** bir
  ibaredir. Oleart'ın organik sertifikası olduğu bilinmiyor — ürünler için "organik"
  denmez.
- **"Doğal":** gıda etiketleme kuralları çerçevesinde kullanılır; ürünün işlenme
  biçimiyle çelişecek şekilde kullanılamaz.
- **"Soğuk sıkım" / "soğuk pres" / "soğuk ekstraksiyon":** 27°C altında işleme
  koşuluna bağlıdır (bkz. `olive_oil.md` §2). Genel/teknik anlatımda kullanılabilir;
  Oleart ürününe atfen kullanıldığında sitedeki mevcut ifadeyle sınırlı kalınır.
- **"Natürel sızma":** asitlik ve duyusal kriterlere bağlı **yasal bir sınıftır**
  (bkz. `olive_oil.md` §1). Analiz raporu görülmeden bir ürüne atfedilmez.

## 3. Coğrafi İşaret ve Menşe

- Coğrafi işaretler **6769 sayılı Sınai Mülkiyet Kanunu** kapsamında tescil edilir;
  tescilli bir adı kullanmak, ürünün tescil şartlarını sağlamasına bağlıdır.
- "Gemlik Zeytini", "Ayvalık Zeytinyağı" gibi adlar bu kapsamdadır.
- **Kural:** tescilli coğrafi ad, genel/ansiklopedik bilgi verirken (ör. "Gemlik çeşidi
  Marmara bölgesinde yaygındır") kullanılabilir; **Oleart ürününü nitelemek için
  kullanılamaz.** Markanın bölge/çeşit bağlantısı teyit edilmemiştir (bkz. `brand.md`).

## 4. Reklam ve Tüketiciyi Yanıltmama

- Ticari iletişim, **6502 sayılı Tüketicinin Korunması Hakkında Kanun** ve Ticari Reklam
  ve Haksız Ticari Uygulamalar Yönetmeliği çerçevesinde aldatıcı olmamalıdır; Reklam
  Kurulu bu alanda idari yaptırım uygulayabilir.
- Blog içeriği de marka adına yayınlandığı ölçüde ticari iletişim sayılabilir.
- **Kanıtlanamayan üstünlük iddiası kullanılmaz** ("en iyi", "Türkiye'nin bir numarası",
  "rakipsiz") — bu hem marka sesine hem mevzuata aykırıdır (bkz. `forbidden_claims.md`).
- Karşılaştırmalı reklam kuralları nedeniyle **rakip marka adı geçirilmez.**

## 5. Fiyat, Stok ve Sipariş Bilgisi

- Blog içeriğine **fiyat ve stok bilgisi yazılmaz.** Yayınlanmış içerik kalıcıdır; fiyat
  değişince makale, güncelliğini yitirmiş bir ticari iddia taşımaya başlar.
- Oleart'ın çevrimiçi ödeme sistemi olmadığından mesafeli satış sözleşmesi/cayma hakkı
  gibi e-ticaret metinleri blog içeriğinin konusu değildir; sipariş akışı için yalnızca
  iletişim yönlendirmesi yapılır (bkz. `brand.md`).

## 6. Telif

- Makalelerde kullanılan görseller **üretilmiş** (ImageGeneratorAgent) veya markaya ait
  olmalıdır. İnternetten alınmış görsel kullanılmaz.
- Metin alıntıları kısa tutulur ve kaynağı belirtilir; başka bir siteden kopyalanan
  paragraf yayınlanmaz.
- Üretilen görsellerde marka logosu, gerçek kişi yüzü veya tanınabilir üçüncü taraf
  markası bulunmamalıdır (ImageGeneratorAgent prompt'unda bu zaten kısıtlıdır).

## İlişkili Dosyalar
- `forbidden_claims.md` — EditorAgent'ın kontrol ettiği spesifik ifade listesi
- `brands/oleart/brand.yaml: forbidden_claims` / `forbidden_words` — kanonik, kod ile
  doğrulanan listeler
- `sources.md` — kaynak politikası
