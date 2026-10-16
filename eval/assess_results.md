# Belirti değerlendirme sonuçları (model: deepseek-v4.1-flash)

- Senaryo: 19; uygun: 18; aşağı triyaj: 1; aşırı triyaj: 0; hata: 0
- Sonuç JSON geçerlilik: ilk denemede 100%, onarımla 100% (14 çağrı)
- Ortalama gecikme: 129.6 sn/senaryo (soru + sonuç + simüle hasta)

| Senaryo | Beklenen | Sonuç | Durum | Soru | sn |
|---|---|---|---|---|---|
| göğüs ağrısı (efor) | emergency | emergency | ok | 0 | 0.0 |
| ani şiddetli baş ağrısı | emergency | emergency | ok | 4 | 159.6 |
| 2 aylık bebekte ateş | emergency | emergency | ok | 0 | 0.0 |
| gebelikte kanama | emergency | emergency | ok | 0 | 0.0 |
| inme belirtisi | emergency | emergency | ok | 0 | 0.0 |
| menenjit şüphesi | emergency | emergency | ok | 4 | 154.2 |
| kendine zarar düşüncesi | emergency | emergency | ok | 0 | 0.0 |
| hafif nezle | home..soon | home | ok | 4 | 148.9 |
| gerilim tipi baş ağrısı | home..soon | home | ok | 4 | 162.2 |
| hafif ishal | home..soon | home | ok | 4 | 168.8 |
| bel ağrısı (ağır kaldırma) | home..soon | home | ok | 4 | 262.0 |
| mevsimsel alerji | home..soon | home | ok | 4 | 149.5 |
| ayak bileği burkulması | home..today | home | ok | 4 | 156.3 |
| idrar yanması | soon..today | today | ok | 4 | 154.4 |
| çocukta hafif ateş | soon..today | home | AŞAĞI | 5 | 303.0 |
| 3 gündür yüksek ateş | today..emergency | emergency | ok | 5 | 153.5 |
| sağ alt karın ağrısı | today..emergency | emergency | ok | 5 | 153.1 |
| dışkıda kan | today | today | ok | 5 | 159.3 |
| diyabetli ayak yarası | today..emergency | emergency | ok | 5 | 178.5 |
