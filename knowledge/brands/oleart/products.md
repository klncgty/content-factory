# Oleart — Ürün Kataloğu

> Kaynak: oleart.co ana sayfası. **WriterAgent bu listede olmayan bir ürüne atıfta
> bulunamaz**; ürün adı/özellik/ölçü uyduramaz. LinkerAgent ürün yönlendirmesi yaparken
> de bu listeyi kullanır.

## 1. Zeytinyağı ve Zeytin (satışta)

### Zeytinyağı
- **Sitedeki tanım:** "Soğuk sıkım, doğal sızma zeytinyağı"
- **Sunum:** 5 litre
- **Fiyat (site):** 2500 TL / 5 litre

> **Terminoloji uyarısı:** site "doğal sızma" diyor; Türk Gıda Kodeksi'ndeki resmi terim
> **"natürel sızma zeytinyağı"**dır. Makalelerde teknik anlatım yapılırken resmi terim
> kullanılır (bkz. `style_guide.md`, `olive_oil.md`); ürüne atıf yapılırken sitedeki
> ifade korunabilir. Ürünün natürel sızma sınıfına girdiğine dair analiz raporu teyit
> edilmemiştir — makalede **ürüne özel asitlik/sınıf iddiası yazılmaz.**

### Sele Zeytini
- **Sitedeki tanım:** "Geleneksel yöntemle olgunlaştırılmış sele zeytini"
- **Fiyat (site):** 350 TL / kg

## 2. Zeytin Ağacından Ahşap Ürünler (henüz satışta değil)

Sitede bu bölüm **"Pek yakında :)"** olarak duruyor — yayınlanmış tek bir ahşap ürün yok.

**Kural:** ahşap ürün konulu makaleler (kesme tahtası, sunum tahtası, kaşık/spatula,
bakım rehberleri — hepsi `scope.yaml`'da izinli) yazılabilir, ancak:
- Somut bir Oleart ürününe atıf yapılamaz (ad, ölçü, fiyat, stok yok).
- "Oleart'ın kesme tahtaları şu özelliktedir" gibi bir cümle **uydurmadır.**
- Konu genel/faktüel düzeyde işlenir (bkz. `kitchen_products.md`, `olive_tree.md`);
  markadan söz edilecekse yalnızca "yakında" çerçevesinde ve abartısız.

## Fiyat Kullanımı
Fiyatlar bu dosyada **referans** olarak tutulur; **makale gövdesine yazılmaz.** Blog
içeriği kalıcıdır, fiyat değişir — güncelliğini yitirmiş fiyat iddiası hem okuyucuyu
yanıltır hem de tüketici mevzuatı açısından risklidir (bkz. `legal_rules.md`).

## Ürün Sayfası URL'leri
oleart.co tek sayfalık bir sitedir — ayrı ürün sayfası **yoktur**. Ürün yönlendirmesi
yapılacaksa hedef, ana sayfadaki ilgili bölüm çıpasıdır (`index.html`'deki gerçek
`id` değerleri):
- Zeytinyağı ve zeytin: `https://oleart.co/#yag`
- Zeytin ağacından ürünler: `https://oleart.co/#agac`
- Nasıl sipariş verebilirim: `https://oleart.co/#siparis`
- İletişim: `https://oleart.co/#iletisim`

> Site yapısı değişirse bu çıpalar güncellenmelidir. Emin olunmayan bir URL'ye link
> verilmez — kırık link üretilmemelidir (bkz. `internal_linking.md`).
