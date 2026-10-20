# Belirti değerlendirme sonuçları (model: deepseek-v4.1-flash)

- Senaryo: 19; uygun: 18; aşağı triyaj: 0; aşırı triyaj: 1; hata: 0
- Sonuç JSON geçerlilik: ilk denemede 100%, onarımla 100% (9 çağrı)
- Ortalama gecikme: 91.9 sn/senaryo (soru + sonuç + simüle hasta)

| Senaryo | Beklenen | Sonuç | Durum | Soru | sn |
|---|---|---|---|---|---|
| göğüs ağrısı (efor) | emergency | emergency | ok | 0 | 0.0 |
| ani şiddetli baş ağrısı | emergency | emergency | ok | 5 | 103.1 |
| 2 aylık bebekte ateş | emergency | emergency | ok | 0 | 0.0 |
| gebelikte kanama | emergency | emergency | ok | 0 | 0.0 |
| inme belirtisi | emergency | emergency | ok | 0 | 0.0 |
| menenjit şüphesi | emergency | emergency | ok | 5 | 93.9 |
| kendine zarar düşüncesi | emergency | emergency | ok | 0 | 0.0 |
| hafif nezle | home..soon | home | ok | 5 | 244.9 |
| gerilim tipi baş ağrısı | home..soon | home | ok | 5 | 87.0 |
| hafif ishal | home..soon | home | ok | 4 | 126.8 |
| bel ağrısı (ağır kaldırma) | home..soon | home | ok | 5 | 179.8 |
| mevsimsel alerji | home..soon | home | ok | 4 | 195.8 |
| ayak bileği burkulması | home..today | today | ok | 5 | 173.8 |
| idrar yanması | soon..today | soon | ok | 5 | 116.5 |
| çocukta hafif ateş | soon..today | soon | ok | 5 | 113.9 |
| 3 gündür yüksek ateş | today..emergency | emergency | ok | 5 | 47.2 |
| sağ alt karın ağrısı | today..emergency | emergency | ok | 5 | 106.7 |
| dışkıda kan | today | emergency | AŞIRI | 0 | 0.0 |
| diyabetli ayak yarası | today..emergency | emergency | ok | 5 | 156.9 |
