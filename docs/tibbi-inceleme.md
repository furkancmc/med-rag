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
- düşük kan şekeri belirtisi, kanlı ishal: bugün hekime (kan şekeri belirtisi bayılma/nöbet ile acil; ayrıntı: sonraki bölüm)
- yanık: nefes yolu belirtisi acil; kimyasal/elektrik, geniş ve yüz/boğaz/genital acil; el/ayak/su toplamış ya da 5 yaş altı: bugün (19.10.2026 doğrulamasıyla güncellendi)
- sağ alt karın ağrısı ya da ateşle karın ağrısı: bugün hekime; ateş/şiddetli ağrı/kusma ile sağ alt ağrı ve şiddetli karın ağrısı: acil
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

## Web kaynaklı doğrulama (19.10.2026)

**Bu bölüm hekim onayı değildir.** Tabloların ve kuralların internetteki otoriter kaynaklarla satır satır karşılaştırılmasıdır. Kaynaklar `WebSearch`/`WebFetch` ile toplandı (özetler üzerinden; bazı sitelerin PDF'leri bot koruması nedeniyle indirilemedi), karşılaştırmayı `deepseek-v4.1-flash` yaptı (`glm-5.3` hız sınırı nedeniyle çalışmadı), sonuçlar elle gözden geçirildi. Ham sonuçlar ve ayrıntılı alıntılar `scratch/` altında tutuldu (repoya alınmadı); kaynak bağlantıları aşağıdadır.

### Kaynaklar
- MedlinePlus laboratuvar testi sayfaları (kamu malı) ve MedlinePlus ansiklopedi: <https://medlineplus.gov/lab-tests/>, <https://medlineplus.gov/ency/article/003468.htm>
- Meritus Health 2018 kritik değer çağrı listesi: <https://www.meritushealth.com/files/Laboratory-Critical-Values-updated-August-2018.pdf>; Chicago Üniversitesi Hastanesi kritik değer listesi: <https://edge.sitecorecloud.io/unichicagomc-81nbqnb3/media/pdfs/adult-pdfs/research/critical_value_list.pdf>
- ADA/CDC glukoz ve HbA1c eşikleri: <https://www.cdc.gov/diabetes/diabetes-testing/index.html>; KDIGO AKI evreleme: <https://qxmd.com/calculate/definition_17/kdigo-aki-staging>
- NCEP ATP III: <https://www.nhlbi.nih.gov/files/docs/guidelines/atp3xsum.pdf>; Cleveland Clinic CBC ve klorür sayfaları; Mayo Clinic Laboratories
- Belirtiler: NICE NG143 (ateş), AAP 2021 febril bebek kılavuzu, CDC Hear Her ve ACOG (gebelik), AHA ve stroke.org (kalp/inme), Meningitis Now ve NHS (menenjit), Mayo Clinic ve NHS (yanık, baş travması, kanlı kusma/dışkı, apandisit, testis torsiyonu), 988 Lifeline ve Poison Help (kendine zarar, zehirlenme), ADA (hipoglisemi)

### Tahlil tablosu (34 test)

Sonuç: LLM karşılaştırması yalnızca LDL üst sınırını farklı buldu (gerekçe aşağıda); diğer aralıklar dış kaynaklarla çelişmedi. Aralıklar laboratuvara göre değiştiği için dış kaynaklarla birebir aynı olmaları beklenmez ve olmadılar (örn. hematokrit üst sınırı bizde %50,3, MedlinePlus'ta %55: bizim değer daha temkinli). MedlinePlus lab sayfaları sayısal aralık vermediğinden çoğu satır için yalnızca aşağıdaki dış aralıklarla karşılaştırma yapılabildi. Kritik eşikler: 11 test kurum listeleriyle uyumlu, 22 test için kaynak bulunamadı (kurum listelerinde yok), 1 test farklı (aşağıda).

| Test | Kayıt aralığı | Dış kaynak aralıkları | Kritik eşik | Kritik eşik doğrulaması | Birim çarpanı |
|---|---|---|---|---|---|
| Hemoglobin | E 13.8-17.2 / K 12.1-15.1 g/dL | MedlinePlus 13-18 / 12-16; Cleveland Clinic 13-17 / 11,5-15,5; Mayo Labs 13,2-16,6 / 11,6-15,0 | <7 / >20 | uyumlu | kaynak yok |
| Hematokrit | E 40.7-50.3 / K 36.1-44.3 % | MedlinePlus ve Cleveland Clinic %40-55 / %36-48 | <21 / >60 | uyumlu | uyumlu |
| Lökosit (akyuvar) | 4.5-11 10^3/µL | MedlinePlus 4,5-11 (10^3/µL) | <2 / >30 | uyumlu | uyumlu |
| Trombosit | 150-450 10^3/µL | MedlinePlus ve Cleveland Clinic 150-400; birçok laboratuvar 150-450 | <20 / >1000 | uyumlu | uyumlu |
| Eritrosit (alyuvar) | E 4.7-6.1 / K 4.2-5.4 10^6/µL | - | - | - | uyumlu |
| MCV (ortalama alyuvar hacmi) | 80-100 fL | MedlinePlus 80-100 fL | - | - | kaynak yok |
| Açlık kan şekeri (glukoz) | 70-99 mg/dL | CDC: açlık <=99 normal, 100-125 prediyabet, >=126 diyabet | <54 / >400 | uyumlu | uyumlu |
| HbA1c (glikozile hemoglobin) | 4-5.6 % | CDC/ADA: <5,7 normal, 5,7-6,4 prediyabet, >=6,5 diyabet | >12 | kaynak yok | uyumlu |
| Total kolesterol | <200 mg/dL | NCEP ATP III: <200 istenen | - | - | kaynak yok |
| LDL kolesterol | <129 mg/dL | NCEP ATP III: <100 optimal, 100-129 optimale yakın | - | - | uyumlu |
| HDL kolesterol | E >40 / K >50 mg/dL | NCEP ATP III: <40 düşük, >=60 yüksek | - | - | kaynak yok |
| Trigliserid | <149 mg/dL | - | >1000 | kaynak yok | kaynak yok |
| Kreatinin | E 0.74-1.35 / K 0.59-1.04 mg/dL | MedlinePlus 0,6-1,3 mg/dL | >4 | kaynak yok | kaynak yok |
| Üre | 13-51 mg/dL | - | >170 | farklı | kaynak yok |
| BUN (kan üre azotu) | 6-24 mg/dL | MedlinePlus 6-20 mg/dL | >80 | uyumlu | kaynak yok |
| Ürik asit | E 3.4-7 / K 2.4-6 mg/dL | - | - | - | kaynak yok |
| ALT (SGPT) | E 7-55 / K 7-45 U/L | MedlinePlus 4-36 U/L (laboratuvara göre 7-55 de kullanılıyor) | >1000 | uyumlu | uyumlu |
| AST (SGOT) | E 8-48 / K 8-43 U/L | MedlinePlus 8-33 U/L (laboratuvara göre 8-48 de kullanılıyor) | >1000 | uyumlu | uyumlu |
| GGT (gama GT) | E 8-61 / K 5-36 U/L | - | - | - | uyumlu |
| ALP (alkalen fosfataz) | 40-129 U/L | MedlinePlus 20-130 U/L | - | - | kaynak yok |
| Total bilirubin | 0.1-1.2 mg/dL | MedlinePlus 0,1-1,2 mg/dL | >10 | kaynak yok | kaynak yok |
| Albümin | 3.5-5 g/dL | MedlinePlus 3,4-5,4 g/dL | <2 | kaynak yok | uyumlu |
| TSH | 0.4-4 mIU/L | tipik yetişkin 0,4-4,0 mIU/L | - | - | kaynak yok |
| Serbest T4 (sT4) | 0.8-1.8 ng/dL | MedlinePlus 0,8-1,9; Cleveland Clinic 0,9-1,7 ng/dL | - | - | kaynak yok |
| Ferritin | E 24-336 / K 11-307 ng/mL | Mayo Labs: E 24-336, K 11-307 ng/mL | - | - | kaynak yok |
| Demir (serum) | E 65-175 / K 50-170 µg/dL | - | - | - | uyumlu |
| B12 vitamini | 200-900 pg/mL | 180-914 ve 200-700 pg/mL (kaynaklara göre) | - | - | kaynak yok |
| Folat (folik asit) | >4 ng/mL | - | - | - | kaynak yok |
| D vitamini (25-OH) | 20-100 ng/mL | - | >150 | kaynak yok | kaynak yok |
| CRP | 0-5 mg/L | - | >100 | kaynak yok | uyumlu |
| Sodyum | 135-145 mmol/L | MedlinePlus 135-145 | <125 / >155 | uyumlu | uyumlu |
| Potasyum | 3.6-5.2 mmol/L | MedlinePlus 3,7-5,2 | <3 / >6 | uyumlu | uyumlu |
| Klor | 98-107 mmol/L | 96-106 mmol/L (Cleveland Clinic) | - | - | kaynak yok |
| Kalsiyum (total) | 8.6-10.3 mg/dL | MedlinePlus 8,5-10,2 mg/dL | <7 / >12 | uyumlu | kaynak yok |

Notlar ve kararlar:
- **Üre kritik eşiği (170 mg/dL):** Meritus listesi BUN için >100 mg/dL verir (üre ~214). Bizim BUN 80 / üre 170 daha erken uyarır; temkinli taraf olduğu için **değiştirilmedi**.
- **LDL üst sınırı 129:** NCEP ATP III 100-129 aralığını 'optimale yakın' sayar, <100 optimaldir. 129 sınırı korundu; açıklamada hedefin kişiye göre değiştiği belirtilir.
- **Trombosit üst sınırı 450:** MedlinePlus/Cleveland Clinic 400, birçok laboratuvar 450 kullanır; değişmedi.
- **BUN üst sınırı 24:** MedlinePlus 20; Mayo Labs 24. Değişmedi (laboratuvara bağlı).
- **Birim çarpanları:** kaynaklarda açık çarpan tablosu bulunamadığından 'kaynak yok' çıktı; standart dönüşümlerle elle kontrol edilmişti (bkz. yukarıdaki bölüm).
- **Kaynağı bulunamayan kritik eşikler:** D vitamini 150, folat, demir, bilirubin (yetişkin), TSH/FT4; bunlar klinik pratikte nadiren 'panik değer' listelerinde yer alır. Eşikler temkinli bırakıldı ve kaynak yok olarak işaretli kalır.

### Belirti kuralları

| Kural grubu | Uyumlu | Kaynak yok | Farklı bulunan (karşılaştırma anındaki kural; çoğu aşağıdaki değişikliklerle giderildi) |
|---|---|---|---|
| gebelik | 3 | 2 | - |
| ates | 4 | 6 | - |
| gogus_solunum | 10 | 2 | Aksi halde göğüs ağrısı → today; Aksi halde nefes darlığı → today |
| norolojik | 5 | 0 | - |
| cocuk_sivi | 3 | 0 | - |
| kanama_gi | 8 | 1 | Ateşle karın ağrısı → today; Sağ alt karın ağrısı/apandisit olasılığı → today; Şiddetli karın ağrısı → today |
| zehir_yanik_seker | 4 | 0 | geniş/yüz-el-ayak veya 5 yaş altı çocukta yanık → today; düşük kan şekeri belirtisi → today |

İlk turda kuralların çoğu 'kaynak yok' çıktı; eksik kaynaklar (menenjit/sepsis, apandisit, kendine zarar, zehirlenme, sarılık, kanlı idrar, yanık, baş travması, GI kanama, hemoptizi, hipoglisemi) toplanıp ikinci tur koşuldu. Aciliyeti **yukarı çeken** değişiklikler (hepsi testli):
- göğüs ağrısı **baskı/sıkışma/ezilme** tarifiyle: acil (AHA)
- siyah/kanlı dışkı + baş dönmesi/bayılma/halsizlik: acil (MedlinePlus, Mayo)
- çok miktarda ya da durmayan kanlı balgam: acil (Mayo, NHS)
- kimyasal ya da elektrik yanığı: acil; geniş ya da yüz/boğaz/genital yanık: acil (Mayo, NHS); el/ayak/su toplamış/5 yaş altı yanık: bugün
- sağ alt karın ağrısı + ateş/şiddetli ağrı/kusma: acil (Cleveland Clinic, NHS); şiddetli karın ağrısı: acil (NHS); ateşle karın ağrısı: bugün
- düşük kan şekeri + bayılma/nöbet/yutamama/bilinç değişikliği: acil (ADA)

Kaynakla **farklı bırakılan** ve gerekçesi: yalnızca 'göğüs ağrısı' ya da 'nefes darlığı' diye tarif edilen, baskı/efor/terleme/yayılım/ani başlangıç içermeyen şikâyetler 'bugün' kalır. AHA, kalp krizi belirtisi olan baskı/sıkışma gibi tariflerde 911 der ve emin olunmasa bile aramayı önerir; bu nedenle bu tarifler artık acil sayılıyor, ancak her göğüs ağrısını (batma, harekete bağlı vb.) acil saymak aşırı triyaj üretir. LLM katmanı bağlama göre yukarı çekebilir.

Hâlâ **kaynakla doğrulanamayanlar** (kural temkinli bırakıldı): 3 aydan büyük bebekte ateş 'bugün', 5 yaş altı yüksek ateş 'bugün', 5 yaş altı herhangi ateş 'birkaç gün içinde', 65 yaş üstü ateş 'bugün', 3 günden uzun ateş 'bugün' (NICE yalnızca <3 ay kırmızı ve 3-6 ay >=39°C amber der; AAP 8-60 gün), gebelikte hafif karın ağrısı/durmayan kusma 'bugün', kanlı ishal, kanlı idrar ve sarılık 'bugün' (kaynaklar hekime başvuruyu önerir, seviye belirtmez), dudak morarması.

### Sınırlar
- Karşılaştırmayı bir LLM yaptı ve web özetleri üzerinden çalıştı; birincil kılavuz PDF'lerinin çoğuna erişilemedi (NICE 403, Merck ve ABIM tabloları indirilemedi).
- Kritik değer listeleri kurumlara özgüdür; 'tek doğru' liste yoktur.
- Bu doğrulama klinik onay yerine geçmez; yayına almadan önce hekim ya da klinik biyokimya uzmanı incelemesi gerekir.
