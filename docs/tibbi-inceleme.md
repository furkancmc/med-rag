# Tıbbi tutarlılık incelemesi (17.10.2026)

**Bu inceleme hekim onayı yerine geçmez.** Yapay zekâ gözden geçiricisi (`deepseek-v4.1-flash`, düşünmesiz mod) ve
bilinen kaynaklarla (MedlinePlus, Mayo Clinic Laboratories, ADA, KDIGO, AAP/NICE, ACOG, AHA/ASA) yapılan bir
çapraz kontroldür. Uygulama yayına alınmadan önce referans aralıklarını ve kritik eşikleri bir hekimin ya da klinik
biyokimya uzmanının onaylaması gerekir. İlke: şüphede daha temkinli taraf, yani aciliyet yukarı.

## Yöntem
1. `labs/reference.py` tablosu 12'şerli parçalarla modele gösterildi (aralık, kritik eşik, birim dönüşümü, eksik eşik).
2. `assess/rules.py` mantığı üç odakla incelendi (çocuk/bebek ateşi ve sıvı kaybı; göğüs, nefes, baş, gebelik;
   eksik kırmızı bayraklar).
3. Model çıktıları tek tek elle doğrulandı: bazı bulgular hatalıydı (aşağıda), bazıları yerinde.
4. Kural eksikleri 25 cümlelik bir yoklama betiğiyle ölçüldü: 11 cümle gerekenden düşük seviyede kalıyordu.

## Tahlil: yapılan değişiklikler (`labs/reference.py`)
| Test | Eski kritik | Yeni kritik | Gerekçe |
|---|---|---|---|
| Glukoz | <=40 / >=500 mg/dL | <=54 / >=400 | 54: ADA düzey 2 hipoglisemi; 500 çok gevşekti |
| HbA1c | >=15 % | >=12 % | ADA "çok yüksek" bölgesi; 15 gereğinden geç |
| Kreatinin | >=7,4 mg/dL | >=4,0 | KDIGO evre 3 eşiği |
| Total bilirubin | >=15 mg/dL | >=10 | yetişkinde belirgin sarılık; 15 geç |
| Sodyum | <=120 / >=160 mmol/L | <=125 / >=155 | ciddi hiponatremi/hipernatremi |
| Potasyum | <=2,5 / >=6,5 | <=3,0 / >=6,0 | >=6,0 ciddi hiperkalemi |
| Kalsiyum | <=6,5 / >=13 mg/dL | <=7,0 / >=12,0 | |
| ALT, AST | yok | >=1000 U/L | akut karaciğer hasarı |
| Albümin | yok | <=2,0 g/dL | |
| BUN / Üre | yok | >=80 / >=170 mg/dL | (üre = BUN x 2,14) |
| CRP | yok | >=100 mg/L | ağır enfeksiyon/sepsis şüphesi |

Bilerek **değiştirilmeyenler** (model daha temkinli öneriyordu): trigliserid kritik 1000 (500 üstü "yüksek" olarak
işaretlenir; pankreatit riski açıklamada geçer), hemoglobin 7,0, lökosit 2,0, trombosit 20, hematokrit 60 (yaygın
"panik değer" listeleriyle uyumlu; daha düşük eşik çok sayıda yanlış alarm üretirdi), D vitamini 150 (toksisite eşiği),
LDL üst sınırı 129 (kişiye göre hedef değişir; açıklamada belirtilir), TSH/serbest T4 (kritik eşik yok; tek başına acil
sayılmaz).

Modelin **yanlış** bulduğu iddialar (ters yön hatası): hemoglobin g/L çarpanı 0,1 ve mmol/L çarpanı 1,611 doğru
(kanonik = değer x çarpan); HbA1c mmol/mol dönüşümü (0,09148 x IFCC + 2,152) doğru; kalsiyum 4,008 ve D vitamini 0,4006
çarpanları standart değerlerle uyumlu. Birim dönüşümlerinde değişiklik yapılmadı.

Bilinen sınırlar: aralıklar yetişkinler içindir (18 yaş altında uyarı notu çıkar), gebelik, yaş ve laboratuvar yöntemine
göre değişen aralıklar kapsanmaz; kullanıcının rapordaki aralığı her zaman önceliklidir (kritik eşikler rapor aralığı
verilse de uygulanır).

## Belirti kuralları (`assess/rules.py`)
Çocukta hafif ateş: 5 yaş altı ateş zaten en az "birkaç gün içinde randevu" (soon); >=39 derece "bugün hekime"; 3 aydan
küçük bebek "acil". Bu davranış korundu (AAP/NICE ile uyumlu, güvenli tarafta).

Eklenen taban kurallar (hepsi yalnızca aciliyeti yukarı çeker):
- zehirlenme/aşırı doz/kimyasal yutma: acil
- kanlı kusma: acil
- ani başlayan nefes darlığı, "nefes almıyor", dudak/yüz morarması: acil
- göğüs ağrısı + nefes darlığı birlikte, kanlı balgam + nefes darlığı: acil
- bebek/2 yaş altı yeşil (safralı) kusma: acil
- gebelikte baş ağrısı + görme/şişlik belirtisi: bugün -> **acil** (preeklampsi)
- düşük kan şekeri belirtisi, kanlı ishal, sağ alt karın ağrısı ya da ateşle karın ağrısı: bugün hekime
- yanık: nefes yolu belirtisi acil; geniş/yüz/el/ayak/kimyasal/elektrik ya da 5 yaş altı: bugün
- bilinç bulanıklığı kalıpları genişletildi ("kafası karışık", "tepki vermiyor", "uyandırılamıyor" vb.)

Modelin önerip **alınmayanlar**: yaşlıda her ateşi acil yapmak (bugün + bilinç bulanıklığı varsa acil kalıyor), her göğüs
ağrısını acil yapmak (eforla/terle/yayılımla acil, diğer bugün), 3-36 ay ateşini acil yapmak (bugün). Bunlar aşırı triyaj
üretir; LLM katmanı bağlama göre yukarı çekebilir.

Kapsam dışı kalan, ileride eklenebilecekler: yaş+risk faktörüne göre göğüs ağrısı, antikoagülanla baş travması, immün
baskılanmış hastada ateş, seyahat öyküsü, çocuk istismarı belirtileri.

## Gerçek API ile uçtan uca sonuçlar (BM25 kaynak, deepseek-v4.1-flash)
- Belirti: 19 senaryo, 18 uygun, aşağı triyaj 0, aşırı triyaj 1 ("gerilim tipi baş ağrısı" -> bugün; güvenli yönde).
  JSON ilk denemede %100 geçerli. Ortalama gecikme ~57 sn/senaryo (düşünen model; soru + sonuç + simüle hasta).
- Tahlil: 10 senaryo (demir eksikliği, kan yağı, tiroit, kritik potasyum/kreatinin, karaciğer, vitamin, birim
  karışımı, bilinmeyen birim, hepsi normal, kritik sodyum): durumlar ve acil bayrağı hepsinde beklenen; açıklama
  24-82 sn; atıf [n] ve kaynak kartları var, dozsuz.
- Görsel okuma (sentetik rapor, iki OCR modeli x temiz/eğik/gürültülü): değer ve birim 12/12; ek 14 satırlık
  bayraklı (H/L) düzende her iki model 14/14. Süre 4-10 sn (satır çıkarımı düşünmesiz yapılınca ~10 kat hızlandı).
