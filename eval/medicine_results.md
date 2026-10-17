# İlaç kutusu okuma ölçümü (17.10.2026)

Yöntem: Pillow ile 10 sentetik ilaç kutusu görseli (marka, etken madde, güç, form), her biri temiz ve gürültülü
(3° eğik, JPEG kalite 60, piksel gürültüsü) olmak üzere 20 görsel. Model: `qwen3-vl-30b` (`VisionService.medicine`).
Sentetik görseller gerçek telefon fotoğrafının yerini tutmaz; sonuçlar üst sınır sayılmalıdır.

| Ölçüt | Doğru |
|---|---|
| Marka adı | 20/20 |
| Etken madde | 19/20 |
| Güç | 18/20 |

Hatalar: BEPANTHOL temiz görselde etken madde "deksantenol" okundu (doğrusu dekspantenol, bir harf eksik). Güç
alanında "5 %" yerine "5 % krem" döndü (form güce karışmış; ölçüt harfiyen eşleşme aradığı için hata sayıldı, bilgi doğru).
