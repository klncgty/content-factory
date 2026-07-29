# İç Link Kuralları

> Sayısal sınırlar `brands/oleart/seo.yaml: internal_linking` içinde config olarak
> tutulur. Bu dosya LinkerAgent'ın *nasıl* link kuracağını (mekanizma ve üslup)
> açıklar — bkz. ARCHITECTURE.md §5 (gerekçeli tasarım kararı).

## Mekanizma
- **Yeni makale içinde:** doğal, gövde-içi markdown linkleri (ör.
  `[erken hasat zeytinyağı](/blog/erken-hasat-zeytinyagi-nedir/)`) — bağlantı metni
  (anchor text) cümlenin doğal bir parçası olmalı, zorlama "buraya tıklayın" tarzı
  ifadeler kullanılmamalı.
- **Eski makalelerde:** gövde metni **değiştirilmez**. Yalnızca `related_articles`
  frontmatter alanına yeni makalenin slug'ı eklenir (oleart.co bunu "İlgili Yazılar"
  widget'ı olarak render eder). Bu, zaten yayınlanmış/onaylanmış içeriği yeniden
  LLM'e düzenletmenin riskini (ton kayması, faktüel hata) ortadan kaldırır.

## Sayılar (bkz. `seo.yaml` — kanonik)
- Makale başına 2-5 ilgili makale önerisi
- Gövde içi link sayısı, makalenin doğal akışını bozmayacak kadar (genellikle 2-4)

## Eşleştirme Kriteri (v1)
Hedef/ikincil anahtar kelime ve kategori (`scope.yaml groups[].id`) örtüşmesi — bkz.
`StateStore.find_related_articles`. Embedding-tabanlı benzerlik Faz 3'te değerlendirilir.

## Ürün Sayfalarına Linkleme
Mümkün olduğunda ilgili ürün sayfasına da (bkz. `products.md`, `kitchen_products.md`)
doğal bir link verilmeli — bu hem kullanıcı deneyimini hem de dönüşümü destekler, ama
her paragrafta zorlama satış linki eklenmemeli (bkz. `tone.md`: "satış odaklı değil").
