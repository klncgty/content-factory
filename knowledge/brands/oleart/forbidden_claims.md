# Yasaklı İfadeler ve İddialar

> **Kanonik kaynak `brands/oleart/brand.yaml`** (`forbidden_claims`, `forbidden_words`
> alanları) — EditorAgent buraya değil, doğrudan `brand.yaml`'a karşı deterministik
> kontrol yapar. Bu dosya aynı listeyi WriterAgent'ın prompt bağlamına, *neden*
> yasaklandığı açıklamasıyla birlikte verir. Liste `brand.yaml` ile tutarlı tutulmalıdır
> — `tests/test_knowledge.py::test_forbidden_claims_matches_brand_yaml` bunu doğrular.

## Sağlık/Tedavi İddiaları (kesinlikle yasak)
- "Hastalığı tedavi eder"
- "Kanseri önler / tedavi eder"
- "İlaç yerine geçer"
- Kaynak gösterilmeyen klinik/istatistiksel sağlık iddiaları

**Neden:** Zeytinyağı ve ahşap ürünler için kanıtsız sağlık/tedavi iddiaları Türkiye
reklam mevzuatına (Ticaret Bakanlığı Reklam Kurulu düzenlemeleri) aykırı olabilir ve
markayı hukuki riske sokar. Sağlıkla ilgili genel/bilinen bilgiler (ör. "zeytinyağı
Akdeniz mutfağının temel bir bileşenidir") sorun değildir — sorun olan, *tedavi edici*
veya *kesin* iddialardır.

## Abartılı Pazarlama Dili
- "Mucize"
- "Kesin çözüm"
- "%100 garanti"
- "En iyi", "eşsiz", "rakipsiz" gibi kanıtsız üstünlük ifadeleri

**Neden:** Marka sesi (bkz. `tone.md`) abartısız ve güven veren olmalı; bu ifadeler hem
inandırıcılığı zedeler hem de tüketiciyi yanıltıcı reklam sayılabilir.

## Diğer Yasaklar
- Rakip marka adı geçirme
- Uydurma istatistik veya kaynak (bkz. `sources.md`)
- Emin olunmayan bilginin "kesinmiş gibi" yazılması
