# medrag — Türkçe Sağlık Bilgi Asistanı

Açık tıbbi kaynaklar üzerinde çalışan, Türkçe konuşan bir **RAG** (kaynaktan cevap üreten) sağlık bilgi asistanı.
Soruyu alır, ilgili kaynak parçalarını bulur, cevabı **yalnızca bu kaynaklara dayanarak** yazar, `[1] [2]`
atıflarıyla kaynakları gösterir ve cevabı yayınlamadan önce kaynaklarla yeniden kontrol eder.

Sohbetin yanında iki ayrı modül vardır: kısa sorularla **aciliyet değerlendirmesi** (belirti) ve **tahlil sonucu
yorumlama** (değerleri girerek ya da sonuç kâğıdının fotoğrafını çekerek). Hepsi telefonda açılan, ana ekrana
eklenebilen tek bir arayüzdedir.

> **Bu bir doktor değildir.** Teşhis koymaz, ilaç ya da doz önermez. Acil belirtilerde cevaptan önce 112'ye
> yönlendirir. Tıbbi bilgiler genel bilgilendirme amaçlıdır. Ayrıntı: [Güvenlik tasarımı](#10-güvenlik-tasarımı).

<table>
  <tr>
    <td align="center"><img src="docs/screens/ui/sohbet-karsilama.png" width="200"><br><sub>Sohbet</sub></td>
    <td align="center"><img src="docs/screens/ui/sohbet-kaynakli-cevap.png" width="200"><br><sub>Kaynaklı cevap</sub></td>
    <td align="center"><img src="docs/screens/ui/sohbet-acil.png" width="200"><br><sub>Acil durum</sub></td>
    <td align="center"><img src="docs/screens/ui/sohbet-dogrulama.png" width="200"><br><sub>Doğrulama işareti</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screens/ui/belirti-1-sikayet.png" width="200"><br><sub>Belirti: şikâyet</sub></td>
    <td align="center"><img src="docs/screens/ui/belirti-2-soru.png" width="200"><br><sub>Belirti: sorular</sub></td>
    <td align="center"><img src="docs/screens/ui/tahlil-1-giris.png" width="200"><br><sub>Tahlil: değer girişi</sub></td>
    <td align="center"><img src="docs/screens/ui/sohbet-koyu-tema.png" width="200"><br><sub>Koyu tema</sub></td>
  </tr>
</table>

> **Görüntüler hakkında dürüst not:** Bu görüntüler gerçek arayüzden, telefon genişliğinde (390 px) ve
> `scripts/dev_server.py` ile alındı. Sohbet cevapları sahte servistendir (kaynaksız/örnek metin), belirti
> sayfasındaki sorular ve sonuç örnek yanıttır. Bu yüzden görüntüler *arayüzü* gösterir, modelin gerçek cevap
> kalitesini göstermez. Gerçek API ile alınmış (eski arayüz) görüntüler [Faz 1 görüntüleri](#faz-1-görüntüleri-gerçek-api)
> bölümündedir.

---

## İçindekiler

1. [Proje durumu: neler hazır, neler ertelendi](#1-proje-durumu-neler-hazır-neler-ertelendi)
2. [Özellikler ve sayfalar](#2-özellikler-ve-sayfalar)
3. [Mimari](#3-mimari)
4. [Teknoloji ve model seçimleri (ve nedenleri)](#4-teknoloji-ve-model-seçimleri-ve-nedenleri)
5. [Veri kaynakları: nereden aldık, neden bunları seçtik](#5-veri-kaynakları-nereden-aldık-neden-bunları-seçtik)
6. [Veri hattı ve indeks](#6-veri-hattı-ve-indeks)
7. [Arama: ölçümler ve kararlar](#7-arama-ölçümler-ve-kararlar)
8. [Sohbet servisi](#8-sohbet-servisi)
9. [Belirti değerlendirme ve tahlil yorumu](#9-belirti-değerlendirme-ve-tahlil-yorumu)
10. [Güvenlik tasarımı](#10-güvenlik-tasarımı)
11. [Arayüz ve PWA](#11-arayüz-ve-pwa)
12. [Sunucu, dağıtım ve Docker](#12-sunucu-dağıtım-ve-docker)
13. [Hızlı başlangıç](#13-hızlı-başlangıç)
14. [Yapılandırma](#14-yapılandırma)
15. [API başvurusu](#15-api-başvurusu)
16. [Workflow'lar (GitHub Actions)](#16-workflowlar-github-actions)
17. [Nasıl geliştirdik: süreç ve alınan kararlar](#17-nasıl-geliştirdik-süreç-ve-alınan-kararlar)
18. [Test ve kalite](#18-test-ve-kalite)
19. [Maliyet notları](#19-maliyet-notları)
20. [Bilinen sınırlar](#20-bilinen-sınırlar)
21. [Sorun giderme](#21-sorun-giderme)
22. [Dizin yapısı](#22-dizin-yapısı)
23. [Yasal uyarı ve lisanslar](#23-yasal-uyarı-ve-lisanslar)
24. [Değişiklik günlüğü](#24-değişiklik-günlüğü)

---

## 1. Proje durumu: neler hazır, neler ertelendi

Bu tablo, "ne kadarının gerçekten denendiğini" açıkça ayırmak için vardır. **Doğrulandı** = gerçek API ya da
gerçek tarayıcıyla çalıştırıldı. **Testle** = yalnızca sahte servislerle birim testi yapıldı.

| Alan | Durum | Not |
|---|---|---|
| Sohbet (kaynaklı cevap, SSE, atıf) | Doğrulandı | Faz 1'de gerçek API ile 13/13 güvenlik senaryosu geçti |
| Acil durum + doz filtresi + uyarı | Doğrulandı | Faz 2'de 40 senaryoya çıktı (40/40, yerel BM25 aramayla) |
| Çalışma anı cevap doğrulama | Doğrulandı (BM25 ile) | 25 cevap doğrulandı, 2 cümle desteksiz işaretlendi |
| İkinci katman acil sınıflandırıcı (LLM) | Doğrulandı (BM25 ile) | Gerçek vektör aramayla uçtan uca koşturulmadı |
| Belirti değerlendirme | Doğrulandı | 19 senaryo (deepseek-v4.1-flash). Çocuk ateşi kuralı sonradan sıkılaştırıldı, tam set yeniden koşulmadı |
| Tahlil yorumu (kural tabanlı sınıflandırma) | Testle + tarayıcıda | 34 test için referans tablosu |
| Tahlil fotoğrafı okuma (OCR) | Kısmen | Yalnızca temiz sentetik görselle denendi; gerçek telefon fotoğrafı ölçülmedi |
| Arayüz (4 sayfa, PWA, tema) | Doğrulandı | Microsoft Edge, 390 px, açık/koyu: JS hatası yok, yatay kaydırma yok |
| Docker imajı | Doğrulandı | Derlendi, konteyner `healthy`, root olmayan kullanıcı, tüm sayfalar 200 |
| Sunucu sertleştirme (hız sınırı, erişim kodu, CSP) | Testle | Çok işçili çalışmada sayaçlar işçi başınadır |
| Ses tanıma (`qwen3-asr-1.7b`) | **Sentetik sesle doğrulandı** | `/audio/transcriptions` Actions'ta Türkçe sentetik sesi çözdü (bir kelime hatalı); gerçek insan sesiyle denenmedi |
| Reranker (`bge-reranker-v2-m3`, yerel) | Kod hazır, **kapalı** | 500 soruda genel kaliteyi düşürdü (Türkçe kaynakta iyileştirdi); ayrıntı: [Arama](#7-arama-ölçümler-ve-kararlar) |
| Çoklu sorgu genişletme | Kod hazır, kapalı | Ölçülene kadar kapalı |
| Yeni veri (~32.7 bin parça) | **İndekse girmedi** | Çekildi ve parçalandı ama embedding'i hesaplanmadı (masraf) |

**Bilerek ertelenenler (masraf):** yeni verilerin embedding'i (indeks yeniden kurulumu), reranker ve arama
ölçümü, gerçek vektör aramayla uçtan uca testler. Ayrıntı: [Maliyet notları](#19-maliyet-notları).

---

## 2. Özellikler ve sayfalar

| Sayfa | Adres | Ne yapar |
|---|---|---|
| **Sohbet** | `/` | Soruya kaynaklı, Türkçe, akan cevap; kaynak kartları (lisans ve tarihle), `[n]` atıfları, "kaynakta doğrulanamadı" işaretleri, 👍/👎, kopyala, sesli oku, sesle soru sor |
| **Belirti Değerlendirme** | `/assess` | Ana şikâyet → en fazla 5 hedefli soru → aciliyet seviyesi (112 / bugün hekim / birkaç gün içinde randevu / evde izle), gerekçe ve kırmızı bayraklar |
| **Tahlil Yorumu** | `/labs` | Değerleri girerek ya da fotoğraftan okuyarak düşük/normal/yüksek/kritik sınıflandırma; kaynaklı açıklama; ilaç kutusu fotoğrafından ilaç adı okuma |
| **Hakkında** | `/about` | Ne yapar/yapmaz, nasıl çalışır, kaynaklar ve lisanslar, güvenlik katmanları, KVKK notu |

Ortak özellikler:

- **Kaynaklı cevap:** Her bilgi cümlesi bir kaynağa bağlanır; kaynak kartında başlık, kaynak adı, lisans, yayın ve
  çekilme tarihi, bağlantı bulunur.
- **Çok dilli arama:** Türkçe soru İngilizce kaynakları da bulur (MedlinePlus ve kaynakların çoğu İngilizcedir).
  Cevap her zaman Türkçedir.
- **Canlı akan cevap:** Sunucu cevabı parça parça (SSE) gönderir.
- **Çalışma anı doğrulama:** Cevap bittikten sonra cümleler kaynaklarla karşılaştırılır; desteklenmeyenler noktalı
  altı çizgiyle işaretlenir, desteklenmişse "Kaynaklarla kontrol edildi" rozeti çıkar.
- **Acil durum yönlendirmesi:** İki katmanlı (kurallar + LLM sınıflandırıcı); model çağrılmadan önce 112 uyarısı.
- **Doz filtresi:** Kaynakta yazsa bile doz içeren cümleler (rakamla ya da yazıyla) cevaptan çıkarılır.
- **Telefona uygun, PWA:** Alt gezinme çubuğu, koyu/açık tema, ana ekrana eklenebilir, çevrimdışı yedek sayfası.
- **Gizlilik:** Hesap yok. Görseller ve sesler yalnızca istek süresince bellekte işlenir, saklanmaz. Sohbet geçmişi
  yalnızca kullanıcının tarayıcısında durur. Geri bildirim IP tutulmadan kaydedilir.

---

## 3. Mimari

<p align="center"><img src="docs/img/mimari.svg" alt="medrag mimari şeması" width="100%"></p>

Bir sohbet isteğinin yolu:

```mermaid
sequenceDiagram
    participant K as Kullanıcı (tarayıcı)
    participant S as Sunucu (FastAPI)
    participant T as Güvenlik katmanı 1
    participant R as Arama (vektör)
    participant L as LLM (deepseek-v4.1-flash)
    K->>S: POST /chat {message, history}
    par aynı anda
        S->>T: acil durum kuralları + LLM sınıflandırıcı
    and
        S->>R: takip sorusunu yeniden yaz, vektör arama (ilk 5)
    end
    alt acil / kendine zarar
        S-->>K: emergency olayı (ilk token'dan önce) [+ sabit güvenli yanıt]
    end
    S-->>K: sources olayı (kaynak kartları)
    S->>L: kaynaklar + soru (yalnızca bunlara dayan)
    L-->>S: cevap akışı
    S-->>K: token olayları (doz filtresinden geçerek)
    S->>L: cümleleri kaynaklarla karşılaştır (hakem)
    S-->>K: verification olayı
    S-->>K: tıbbi uyarı + done
```

Katmanlar arası sözleşmeler (`PLAN.md`): `Retriever.search(query, k)` arayüzü sabittir; yeni uç noktalar
`api/routes/<ad>.py` içindeki `router` ile, yeni sayfalar `web/<ad>.html` ile otomatik bulunur; bağımlılıklar
`deps.py` üzerinden tembel yüklenir ve testlerde sahtesiyle değiştirilir.

---

## 4. Teknoloji ve model seçimleri (ve nedenleri)

### Yazılım

| Parça | Seçim | Neden |
|---|---|---|
| Dil / sürüm | Python 3.11+ (3.12 ile geliştirildi) | Veri ve LLM işleri için pratik; tek dil |
| Web çatısı | FastAPI + uvicorn | SSE akışı, otomatik doğrulama (pydantic), hafif |
| Arayüz | Sade (vanilla) JS + CSS, derleme adımı yok | Telefonda hızlı açılır, bağımlılık yok, CSP `'self'` ile uyumlu, dışarıdan font/CDN yok (gizlilik) |
| Vektör arama | `numpy` ile kosinüs benzerliği (düz dosya) | Bin düzeyindeki parça sayısı için vektör veritabanı gereksiz; dosya repoda durur, kurulum sıfır |
| HTTP istemcisi | Standart kütüphane `urllib` | Çalışma zamanında ek bağımlılık yok; çok parçalı (multipart) gövdeyi kendimiz kuruyoruz |
| Ayarlar | `pydantic-settings` (`MEDRAG_` önekli ortam değişkenleri) | Tek yerde, tür denetimli, `.env` destekli |
| Test / kalite | `pytest`, `ruff` (BLE/PLW gibi ek kurallar açık) | 420 test, LLM ve embedding sahte servislerle |
| Konteyner | Docker (`python:3.12-slim`), docker-compose | Tek komutla çalışır; root olmayan kullanıcı, healthcheck |
| Otomasyon | GitHub Actions | API'ye erişen ölçümler ve veri yenileme orada çalışır |
| Tarayıcı QA | Playwright + Microsoft Edge | Gerçek tarayıcıda 390 px denemesi, ekran görüntüsü |

### Modeller

Hepsi **Evren API** üzerinden, OpenAI uyumlu uçlarla (`https://evren-llmapi.ssyz.org.tr/v1`) kullanılır. Anahtar
yalnızca `EVREN_API_KEY` ortam değişkeninden okunur; repoya, loga ya da hata mesajına yazılmaz.

| Görev | Model | Neden bu model |
|---|---|---|
| Sohbet, belirti ve tahlil açıklaması, doğrulama hakemi, acil sınıflandırıcı, bilgi çıkarımı | `deepseek-v4.1-flash` | Proje sahibinin seçimi: ajan/kod görevlerinde güçlü, 1M bağlam, ayarlanabilir düşünme bütçesi. Yan görevlerde (hakem, sınıflandırıcı) düşünme kapatılır (`enable_thinking: false`) ki hızlı olsun |
| Embedding | `BAAI/bge-m3` (yerel GPU, 1024 boyut) | Çok dilli; Türkçe soruyla İngilizce kaynağı eşleştirir. API, kredi ve hız sınırı gerektirmez; 33,5 bin parça RTX 4060'ta ~6 dk |
| Yeniden sıralama (kapalı) | `BAAI/bge-reranker-v2-m3` (yerel) | Adayları yeniden sıralar; ölçümde genel kaliteyi düşürdüğü için kapalı |
| Çoklu sorgu (kapalı) | `auto` (hızlı yönlendirici) | deepseek düşünürken bu iş 8–22 sn sürüyor, `auto` ~0,5 sn |
| Tahlil fotoğrafı OCR | `deepseek-ocr-2`, `dots-ocr` (`POST /v1/ocr`) | OCR modelleri sohbet ucunu reddeder, ayrı uç ister. Biri markdown, biri HTML tablo döndürür; ikisi de ayrıştırılır |
| Görsel sohbet / ilaç kutusu | `qwen3-vl-30b` | OpenAI tarzı `image_url` ile görsel girdi |
| Ses tanıma | `qwen3-asr-1.7b` | Tarayıcıda ses kaydı → metin. Tarayıcı ses tanıma yedek olarak var |
| Güvenlik sınıflandırıcı (isteğe bağlı) | `qwen3-guard-4b` | Varsayılan **kapalı**: kendine zarar çıktısını doğru etiketledi ama göğüs ağrısı gibi tıbbi acilleri yakalamıyor. O işi LLM sınıflandırıcı yapıyor |

**Neden yerel/açık model değil, hazır API?** Geliştirme hızı ve H200 üzerinde yüksek eşzamanlılık. Bunun bedeli,
sunucunun bu adrese erişmek zorunda olması ve düşünen modelin gecikmesidir (bkz. [Sınırlar](#20-bilinen-sınırlar)).

---

## 5. Veri kaynakları: nereden aldık, neden bunları seçtik

Kural: **yalnızca lisansı açık ve ticari olmayan kullanıma uygun olan kaynaklar**; her parçada kaynak, lisans,
yayın/güncelleme ve çekilme tarihi saklanır ve kaynak kartında gösterilir.

| Kaynak | İçerik | Lisans | Çekilen miktar (tam çekim) |
|---|---|---|---|
| [MedlinePlus](https://medlineplus.gov) (ABD Ulusal Tıp Kütüphanesi) | Sağlık konuları, İngilizce | Kamu malı | 1.017 konu |
| [Vikipedi](https://tr.wikipedia.org) (tr + en) | Elle seçilmiş ~550 konu (hastalık, belirti, ilk yardım, Türkiye'de sık görülenler) | CC BY-SA 4.0 | tr: 443/537, en: 547/550 |
| [Europe PMC](https://europepmc.org) | 2020 sonrası, **CC BY / CC BY-SA** lisanslı derleme (review) makale özetleri | CC BY, CC BY-SA | 1.558 özet (545/550 konu) |
| [openFDA](https://open.fda.gov) | İlaç prospektüsü: endikasyon, uyarı, yan etki, etkileşim. **Doz bölümleri bilerek alınmaz** | Kamu malı | 233/238 ilaç |
| [NIH ODS](https://ods.od.nih.gov) | Vitamin ve mineral bilgi sayfaları | Kamu malı | **0/37**: Cloudflare 403 (bkz. aşağıda) |
| [CDC](https://www.cdc.gov) | Hastalık ve korunma sayfaları (~97 konu sorgusu; CDC Content Services syndication API'si, hekim/istatistik/MMWR sayfaları atılır) | Kamu malı | 128 sayfa (67/97 konu; CDC kütüphanesinde olmayanlar atlanır) |
| `data/local/` | Kendi `.txt`/`.md` dosyaların (isteğe bağlı) | Sana ait | — |

**Tahlil referans aralıklarının kaynakları** (34 test; her satırda `ref_source` alanında yazılıdır): 17'si
MedlinePlus, 9'u Mayo Clinic Laboratories tipik değerleri, 7'si "yaygın klinik hedef/eşik değer" olarak işaretli
(örn. glukoz, lipidler), 1'i NIH Beslenme Takviyeleri Ofisi.

**Neden bu kaynaklar?**
- *MedlinePlus ve openFDA:* kamu malı, güvenilir, makine tarafından okunabilir.
- *Vikipedi:* Türkçe kapsamı ve geniş konu çeşitliliği; lisansı CC BY-SA olduğundan cevap yayınlarken atıf gerekir.
- *Europe PMC:* güncel (2020+) ve açık lisanslı literatür; yalnızca özetleri ve yalnızca CC BY / CC BY-SA olanlar alınır.
- *Dışarıda bırakılanlar:* **WHO bilgi sayfaları** (CC BY-NC-SA, ticari kullanımı kısıtlar).

**Vikipedi listesi neden elle seçildi?** İlk denemede kategori gezmek ilk 500 başlığı alfabetik sırayla aldı ve
yaygın hastalıkları kaçırdı. Bu yüzden `src/medrag/ingest/curated.py` ve `curated_extra.py` içinde elle seçilmiş,
Türkçe/İngilizce başlık çiftlerinden oluşan bir liste var (Türkçe sayfası olmayan konuda ilk değer `None`).

**NIH ODS neden 0?** `ods.od.nih.gov` bu makineden hem sayfa hem API için tarayıcı kimliğiyle bile 403 döndü
(bot koruması). Bunu aşmaya çalışmadık. Kaynak *isteğe bağlı* işaretlendi: başarısız olunca `fetch` çıkış kodunu
bozmaz, özette "ATLA" olarak raporlanır. GitHub Actions üzerinden denenebilir.

**Önemli:** Tam çekimden sonra **32.753 parça** (41 MB) çıkıyor. Ancak şu an **indekse yalnızca eski 13.236 parça
girmiş durumda**; yeni verilerin embedding'i masraf nedeniyle hesaplanmadı ve yeni ham veri repoya alınmadı
(`fetch-data` workflow'u ile alınır). Yani bugün çalışan asistan eski ve daha küçük bilgi tabanını kullanır.

---

## 6. Veri hattı ve indeks

```bash
python -m medrag.ingest fetch --sources all            # tüm kaynakları paralel indir (hata yalıtımlı)
python -m medrag.ingest fetch --sources europepmc,openfda --limit 20   # küçük deneme
python -m medrag.ingest build                          # ham veri -> data/chunks.jsonl
python -m medrag.index embed --backend local               # yerel GPU, ARTIMLI -> data/index_bge_m3
python -m medrag.index embed --full                    # önbelleği yok say, hepsini yeniden hesapla
python -m medrag.index embed --trust-legacy            # eski (hash dosyasız) indeksi devral (ilk geçiş)
python -m medrag.index search "göğüs ağrısı"           # BM25 ile hızlı deneme
```

**Adımlar ve kararlar**

1. **İndirme (`ingest/`)**: kaynak başına ayrı modül; hız sınırlayıcı, 429'da geri çekilme, kaynak başına hata
   yalıtımı. Kaynaklar aynı anda iner (farklı sunucular). Sonda özet ve çıkış kodu verir.
2. **Temizleme**: Vikipedi'den "See also / Kaynakça / Dış bağlantılar" bölümleri alt başlıklarıyla atılır; 10
   kelimeden kısa parçalar elenir; normalleştirilmiş metin özetiyle tekrarlar silinir.
3. **Parçalama (`ingest/chunk.py`)**: başlıklara göre bölünür, uzun bölümler ~200 kelimelik (Europe PMC özetleri
   320), 30 kelime örtüşmeli parçalara ayrılır. Parça kimliği kararlıdır (`belge#n`); elenen parçalar sayılmaya
   devam ettiğinden kimlikler kaymaz.
4. **Embedding (`index/local_embed.py`)**: yerel `BAAI/bge-m3`, fp16, 1024 boyut, L2-normalize, int8 saklanır.
   Sorgularda modelin talimat öneki kullanılır, pasajlarda kullanılmaz. Sorgu embedding'leri iş parçacığı güvenli
   bir LRU önbellekte tutulur.
5. **Artımlı depo (`index/store.py`)**: her parça için `sha1(metin + model + boyut)` `hashes.json`'a yazılır.
   `embed` yalnızca **yeni veya değişen** metinleri hesaplar, aynı metni bir kez gönderir, model/boyut değişirse
   önbelleği geçersiz sayar. **İndeksin bir kez kurulması yeterlidir**; sonradan yalnızca fark hesaplanır.
6. **Depolama**: float16 boyutu 40 MB'ı aşarsa vektör başına ölçekli **int8** kullanılır (32.753 parça için ~67 MB
   yerine ~33 MB; kosinüs benzerliği >0,9995). `load_vectors` her zaman L2-normalize float32 döndürür ve eski
   biçimi yükler.

Veri değişirse (parça sayısı/sırası) indeks yeniden üretilmelidir; aksi halde yükleme
"vektörler chunk listesiyle uyuşmuyor" hatası verir.

---

## 7. Arama: ölçümler ve kararlar

### Varsayılan: yerel BGE-M3 vektör arama

Embedding, kullanıcının kendi GPU'sunda (ya da CPU'da) `BAAI/bge-m3` ile yapılır; API'ye, krediye ya da hız sınırına
bağımlılık yoktur. Vektörler 1024 boyutlu, L2-normalize ve int8 saklanır (`data/index_bge_m3`, git'e girmez).
`meta.json` içindeki model adı ve boyut yüklemede denetlenir; farklı modelin indeksi yanlışlıkla yüklenmez.

### Ölçüm yöntemi

- **Soru kümesi:** 500 Türkçe hasta sorusu (`eval/queries.jsonl`). Her biri korpustan sabit tohumla seçilen bir
  parçadan, "metindeki cümleleri kopyalamadan, günlük dille" bir LLM'e (`deepseek-v4.1-flash`) yazdırıldı.
- **Korpus:** 33.573 parça (MedlinePlus, Vikipedi tr/en, Europe PMC, openFDA, CDC).
- **Başarı:** doğru parça ilk *k* sonuçta mı (recall@k) ve ilk doğru sonucun sırası (MRR@10).
- **Dikkat:** sorular LLM yazımıdır; gerçek kullanıcı sorularından farklı olabilir. Soruların %78'i İngilizce
  kaynağı hedefler, yani Türkçe soru ile İngilizce belge eşleştirme (çapraz dil) en zor kısımdır.

### Sonuçlar (500 soru)

| yöntem | recall@1 | recall@3 | recall@5 | recall@10 | MRR@10 | ort. gecikme |
|---|---|---|---|---|---|---|
| **vektör (BGE-M3, kullanılan)** | **0,534** | **0,696** | **0,780** | **0,864** | **0,636** | 0,04 sn |
| vektör + yerel rerank (havuz 20) | 0,456 | 0,596 | 0,706 | 0,826 | 0,555 | - |
| vektör + yerel rerank (havuz 40) | 0,448 | 0,570 | 0,668 | 0,776 | 0,536 | - |
| bm25 | 0,158 | 0,208 | 0,218 | 0,230 | 0,184 | 0,01 sn |

### Kaynak ve dile göre kırılım (recall@1 / recall@5 / MRR@10)

| grup | soru | bm25 | vektör | vektör + rerank (20) |
|---|---|---|---|---|
| Vikipedi tr | 110 | 0,70 / 0,93 / 0,80 | 0,82 / 0,97 / 0,89 | 0,96 / 1,00 / 0,98 |
| Vikipedi en | 114 | 0,01 / 0,04 / 0,02 | 0,47 / 0,75 / 0,59 | 0,34 / 0,69 / 0,48 |
| MedlinePlus en | 276 | 0,00 / 0,01 / 0,01 | 0,45 / 0,71 / 0,55 | 0,30 / 0,59 / 0,42 |

### Neden vektör arama?

- BM25, Türkçe soru ile İngilizce kaynak arasında ortak kelime olmadığı için İngilizce kaynaklarda neredeyse hiç
  sonuç bulamaz. BGE-M3 çok dillidir ve dilden bağımsız eşleştirir.
- Türkçe kaynaklı sorularda vektör aramanın recall@5 değeri 0,97'dir.
- Hybrid (BM25 + vektör) daha önceki denemelerde vektörden daha kötü çıktı; kodda dursa da kullanılmıyor.

### Reranker: ölçüldü, varsayılan kapalı

`BAAI/bge-reranker-v2-m3` (yerel) vektör aramadan 20-40 aday alıp yeniden sıralar. Genel kaliteyi **düşürdü**
(recall@1 0,534'ten 0,456'ya). Türkçe kaynaklarda belirgin iyileştirdi (recall@1 0,82'den 0,96'ya), İngilizce
kaynaklarda kötüleştirdi. Şablon farkı (`qwen3` / `none`) sonucu değiştirmedi. Olası nedenler: Türkçe soru - İngilizce
belge eşleştirmede reranker'ın zayıflığı ve metriğin katılığı (aynı belgenin başka ama eşit ilgili parçası da hata
sayılır). Açmak için: `MEDRAG_RERANK_ENABLED=true`, `MEDRAG_RERANK_BACKEND=local`.
Ölçüm dosyaları: `eval/results_bge_m3.md`, `eval/results_bge_m3_rerank.md`.

### Çoklu sorgu (kodlandı, varsayılan kapalı)

`multiquery.py`: LLM'den İngilizce çeviri + 1-2 Türkçe yeniden yazım alır, aramaları paralel yapıp RRF ile birleştirir.
Tam ölçüm yapılmadı.

### Kurulum ve komutlar

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124   # CUDA'lı torch (~2,5 GB)
pip install -e ".[local]"                                               # transformers
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

python -m medrag.ingest build                                   # data/chunks.jsonl
python -m medrag.index embed --backend local --bench 200        # hız/VRAM ölçümü, kaydetmez
python -m medrag.index embed --backend local                    # tüm parçalar -> data/index_bge_m3 (artımlı)
python -m medrag.eval run --methods bm25,vector --workers 1 \
    --out-md eval/results_bge_m3.md --out-json eval/results_bge_m3.json
uvicorn medrag.api.main:app                                     # sunucu (varsayılan: yerel embedding)
```

Ayarlar: `MEDRAG_EMBED_BACKEND=local|api` (varsayılan `local`), `MEDRAG_LOCAL_EMBED_MODEL` (`BAAI/bge-m3`),
`MEDRAG_LOCAL_EMBED_BATCH` (32; CUDA bellek yetersizliğinde otomatik yarıya iner), `MEDRAG_LOCAL_EMBED_MAX_LENGTH`
(512 token), `MEDRAG_LOCAL_EMBED_DEVICE` (boş: GPU varsa `cuda`, yoksa `cpu`), `MEDRAG_LOCAL_INDEX_DIR`.
Sorgu ve belgeye ek önek eklenmez (BGE-M3 kuralı). Yerel arka uçta arama için `EVREN_API_KEY` gerekmez; sohbet LLM'i
yine API kullanır.

### Hız ve donanım

RTX 4060 Laptop (8 GB), fp16: 33.573 parça **356 sn** (~94 parça/sn), tepe VRAM **1,4 GiB**, bellek hatası yok.
Sorgu gecikmesi ~0,04 sn. Model ilk istekte (tembel) yüklenir; GPU yoksa CPU'ya düşer (sorgu başına yüzlerce ms,
indeks üretimi saatler). `MEDRAG_WARMUP=1` yalnız indeksi ısıtır, modeli değil.

### Docker notu

CUDA'lı torch imajı çok büyütür (torch ~2,5 GB + model ~2,3 GB) ve GPU için NVIDIA Container Toolkit
(`--gpus all`) ister. Model imaja gömülmemeli; HF önbelleği bir volume'a bağlanmalı
(`-v hf-cache:/root/.cache/huggingface`). Küçük imaj istenirse `MEDRAG_EMBED_BACKEND=api` kullanılır
(`[local]` ekstrası kurulmaz). Yerel model `data/` içinde değil, kullanıcının HF önbelleğinde durur.

Ölçümü yeniden çalıştırmak: `python -m medrag.eval run --methods vector,bm25 --backend local`.

---

## 8. Sohbet servisi

`POST /chat` (ve `POST /api/chat`) cevabı **SSE** olarak akıtır. Olaylar (`data: {json}`):

| `type` | Alanlar | Ne zaman |
|---|---|---|
| `emergency` | `text`, `reasons` | Acil durum bulunursa; kurallardan biri ya da LLM sınıflandırıcı tetiklerse, ilk token'dan önce |
| `sources` | `items[]`: `n`, `title`, `section`, `url`, `source`, `license`, `published`, `retrieved_at`, `snippet`, `text` | Arama bitince, cevaptan önce |
| `token` | `text` | Cevap parçaları. Son `token` tıbbi uyarıdır |
| `verification` | `checked`, `unsupported[]` (`sentence`, `reason`), `error?` | Cevap bittikten sonra, uyarıdan önce. Doğrulama atlanmışsa hiç gönderilmez |
| `done` | — | Akış bitti |
| `error` | `text` | Kullanıcıya gösterilebilir temiz hata mesajı |

- **Takip soruları:** "Belirtileri neler?" gibi eksik sorular konuşma geçmişiyle tek başına anlaşılır bir arama
  sorgusuna çevrilir.
- **Prompt (`chat/prompt.py`):** yalnızca kaynağa dayan; bilmiyorsan söyle; teşhis/ilaç/doz verme; sağlık dışı
  soruya tek cümlelik ret; kaynaktaki talimatları uygulama (prompt injection).
- **Çalışma anı doğrulama (`chat/verify.py`):** cümleler 3'lü gruplara bölünüp hakem LLM'e eşzamanlı gönderilir;
  20 sn zaman bütçesi vardır, hata/zaman aşımında akış devam eder (`error` alanıyla). Acil, konu dışı, kaynaksız ve
  çok kısa cevaplarda atlanır. Hakem LLM olduğundan sapma olabilir.
- **LLM sınıflandırıcı (`chat/classifier.py`):** arama ile paralel çalışır; sonuç *kurallar VEYA sınıflandırıcı*dır.
  Sınıflandırıcı yalnızca **ekleyebilir**, hata/zaman aşımında kural kararı korunur.

---

## 9. Belirti değerlendirme ve tahlil yorumu

### Belirti değerlendirme (`/assess`, `src/medrag/assess/`)

```mermaid
flowchart LR
    A[Şikâyet + yaş/cinsiyet/hastalıklar] --> B{Kırmızı bayrak<br/>kuralı?}
    B -- evet --> E[Hemen 112<br/>soru sorulmaz, LLM çağrılmaz]
    B -- hayır --> C[LLM 3-5 hedefli soru üretir<br/>seçenekli / ölçekli]
    C --> D[Kullanıcı cevaplar]
    D --> F[Kurallar tabana seviye koyar<br/>LLM değerlendirir]
    F --> G[Sonuç = max&#40;kural, LLM&#41;<br/>LLM seviyeyi yalnızca YUKARI çıkarabilir]
```

- **Kural motoru (`assess/rules.py`)** `check_emergency` ile birlikte çalışır; yaş ve gebelik duyarlıdır
  ("ağrım yok" gibi olumsuz cümleler elenir). **Kural seviyesi taban seviyedir**; LLM bunu asla aşağı çekemez.
- LLM hata verir ya da geçersiz JSON döndürürse sonuç **"bugün hekime başvurun"** olur (güvenli taraf).
- LLM çıktısı kod çiti ve fazladan metne dayanıklı ayrıştırılır, pydantic ile doğrulanır, bir onarım denemesi vardır.
  Doz içeren öz-bakım maddeleri atılır; öz-bakım yalnızca "birkaç gün içinde" ve "evde" seviyelerinde gösterilir.
- **5 yaş altında ateş:** en az "birkaç gün içinde hekim" seviyesidir (evde izlemeye bırakılmaz). 3 aydan küçük
  bebekte ateş doğrudan acildir.
- **Ölçüm (`eval/assess_results.md`, 19 senaryo, deepseek-v4.1-flash):** 18'i beklenen aralıkta, 7 acil senaryonun
  hepsi acil, aşırı triyaj yok, JSON %100 geçerli. Çocukta hafif ateş senaryosu "evde" çıkmıştı; bu yüzden yukarıdaki
  5 yaş kuralı eklendi. Bu rapor kuraldan *önceki* koşuya aittir, tam set yeniden koşulmadı. Ortalama gecikme
  senaryo başına ~130 sn (düşünen model + simüle hasta) ölçüldü; gerçek kullanımda sayfa yavaş hissettirebilir.

### Tahlil yorumu (`/labs`, `src/medrag/labs/`)

- **Sınıflandırma tamamen kural tabanlıdır** (düşük / normal / yüksek / kritik / belirsiz). LLM sınıflandırma
  yapmaz; yalnızca anormal değerler için kaynaklı, doz içermeyen bir açıklama yazar. LLM ya da arama yoksa kural
  tabanlı sonuç yine döner.
- **Referans aralığı politikası (önemli):**
  1. **Raporda aralık yazıyorsa o esas alınır** (kullanıcı "Raporumdaki referans aralığı" alanını girer; sonuç
     `basis: "report"` ile işaretlenir ve yerleşik aralığın yerine geçer).
  2. **Yazmıyorsa** genel yetişkin aralığı kullanılır (`basis: "builtin"`) ve sonuca şu not eklenir: *aralıklar
     laboratuvara göre değişir, kesin değerlendirme için raporunuzdaki aralığa bakın ve hekiminize danışın.*
  3. **Kritik eşikler** genel klinik eşiklerdir; her zaman uygulanır (güvenlik için aşağı çekilmez) ve her kritik
     sonuçta "bu değeri bir hekimle değerlendirin" notu çıkar. Kritik değerde sabit acil uyarı gösterilir.
  4. Yetişkin dışı (18 yaş altı) için ek uyarı verilir; cinsiyet belirtilmezse kadın ve erkek aralıklarını kapsayan
     geniş aralık kullanılır.
- **34 test:** hemogram (Hb, Hct, lökosit, trombosit, eritrosit, MCV), glukoz, HbA1c, lipidler (total, LDL, HDL,
  trigliserid), böbrek (kreatinin, üre, BUN, ürik asit), karaciğer (ALT, AST, GGT, ALP, bilirubin, albümin), tiroit
  (TSH, sT4), demir/ferritin, B12, folat, D vitamini, CRP, elektrolitler (Na, K, Cl) ve kalsiyum. Türkçe harf
  duyarsız ad eşleştirme, `5,4` / `<0.5` / `3.5-5.0` ayrıştırma ve birim dönüşümü (HbA1c mmol/mol dahil) vardır.
- **Fotoğraftan okuma (`vision.py`):** dosya imzası (JPEG/PNG/WebP, ≤ 8 MB) doğrulanır; görsel **saklanmaz**. Önce
  OCR modelleri (`/v1/ocr`), sonra `qwen3-vl-30b` denenir. Çıkarımı LLM yapar ve **sayısı OCR metninde geçmeyen satır
  atılır** (uydurmayı önler); LLM çökerse kural tabanlı ayrıştırıcı devreye girer. Satırlar yorumdan önce
  **kullanıcı onayına** sunulur.
- **İlaç kutusu:** `qwen3-vl-30b` ile ad, etken madde, güç ve form okunur, **doz önerilmez**.
- **Sınır:** Referans aralıkları ve kritik eşikler tıbbi olarak bir hekim tarafından gözden geçirilmelidir.

### OCR örnekleri: normal ve bozulmuş görseller

Tahlil ve ilaç kutusu okumayı, telefon fotoğrafını taklit eden **bozulmuş görsellerle** ölçtük (`scripts/ocr_set.py`
üretir, `scripts/ocr_eval.py` ölçer; yöntem ve sonuçlar: [`eval/ocr_real_results.md`](eval/ocr_real_results.md)).
Aşağıda aynı içeriğin normal hâli ile üç bozulma düzeyi var. Hafif düzeyde 1, orta düzeyde 2, ağır düzeyde 4 bozulma
birlikte uygulanır: perspektif eğimi, gölge, flaş parlaması, buruşma, bulanıklık, düşük ışık ve kenar kırpma; hepsinin
üstüne JPEG sıkıştırma gelir. Görseller sentetiktir (Pillow ile çizildi), gerçek bir kişiye ya da markaya ait veri içermez.

<table>
  <tr>
    <td align="center"><img src="docs/screens/ocr/rapor-tablo-normal.jpg" width="150"><br><sub>Klasik tablo raporu: normal</sub></td>
    <td align="center"><img src="docs/screens/ocr/rapor-tablo-hafif.jpg" width="150"><br><sub>hafif</sub></td>
    <td align="center"><img src="docs/screens/ocr/rapor-tablo-orta.jpg" width="150"><br><sub>orta</sub></td>
    <td align="center"><img src="docs/screens/ocr/rapor-tablo-agir.jpg" width="150"><br><sub>ağır</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screens/ocr/rapor-enabiz-normal.jpg" width="150"><br><sub>e-Nabız tarzı rapor: normal</sub></td>
    <td align="center"><img src="docs/screens/ocr/rapor-enabiz-hafif.jpg" width="150"><br><sub>hafif</sub></td>
    <td align="center"><img src="docs/screens/ocr/rapor-enabiz-orta.jpg" width="150"><br><sub>orta</sub></td>
    <td align="center"><img src="docs/screens/ocr/rapor-enabiz-agir.jpg" width="150"><br><sub>ağır</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screens/ocr/kutu-parol-normal.jpg" width="150"><br><sub>İlaç kutusu (Parol): normal</sub></td>
    <td align="center"><img src="docs/screens/ocr/kutu-parol-hafif.jpg" width="150"><br><sub>hafif</sub></td>
    <td align="center"><img src="docs/screens/ocr/kutu-parol-orta.jpg" width="150"><br><sub>orta</sub></td>
    <td align="center"><img src="docs/screens/ocr/kutu-parol-agir.jpg" width="150"><br><sub>ağır</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screens/ocr/kutu-nurofen-normal.jpg" width="150"><br><sub>İlaç kutusu (Nurofen): normal</sub></td>
    <td align="center"><img src="docs/screens/ocr/kutu-nurofen-hafif.jpg" width="150"><br><sub>hafif</sub></td>
    <td align="center"><img src="docs/screens/ocr/kutu-nurofen-orta.jpg" width="150"><br><sub>orta</sub></td>
    <td align="center"><img src="docs/screens/ocr/kutu-nurofen-agir.jpg" width="150"><br><sub>ağır</sub></td>
  </tr>
</table>

Sonuç özeti (48 rapor, 45 kutu; ayrıntı ve model karşılaştırması `eval/ocr_real_results.md` dosyasında):

| Görsel | Hafif / orta bozulma | Ağır bozulma |
|---|---|---|
| Tahlil değerleri (4 model) | %98-100 doğru | %41-54 (**yeniden ölçülecek**: ölçüm sırasında API hız sınırı hataları sonucu bozmuş olabilir) |
| İlaç kutusu, `gemma-4-31b` | marka %100, etken madde %100, güç %80-100 | marka %93, etken madde %80, güç %87 |

Okuma: temiz ve hafif/orta bozulmuş görsellerde değerler neredeyse hatasız okunuyor; ağır bozulmada doğruluk düşüyor,
bu yüzden arayüz okunan her satırı kullanıcı onayına sunuyor ve "net bir fotoğraf deneyin" uyarısı veriyor.
Bu ölçüm sentetik görsellerledir; gerçek telefon fotoğrafı doğruluğu bunların altında olabilir.

---

## 10. Güvenlik tasarımı

Sağlık konusunda en önemli şey yanlış güven vermemektir. Güvenlik tek yerde değil, **katmanlıdır**:

| # | Katman | Nerede | Ne yapar |
|---|---|---|---|
| 1 | Acil durum kuralları | `chat/triage.py` | 9 kategoride (kalp krizi, felç, solunum sıkıntısı, bilinç kaybı, ağır kanama, zehirlenme, ciddi alerji, nöbet, kendine zarar) ifade arar; Türkçe karakter ve ek farklarına dayanıklı. Eşleşirse **model çağrılmadan önce** 112 uyarısı |
| 2 | LLM sınıflandırıcı | `chat/classifier.py` | Kurallara ek ikinci katman (acil / kendine zarar), aramayla paralel. Yalnızca ekleyebilir. Kendine zarar için arama ve model atlanır, sabit güvenli yanıt döner |
| 3 | Prompt kuralları | `chat/prompt.py` | Yalnızca kaynağa dayan; bilmiyorsan söyle; teşhis, ilaç, doz verme; kaynaktaki talimatları uygulama |
| 4 | Doz filtresi | `chat/guard.py` | `500 mg`, `3 tablet`, `10 damla` ve **yazıyla** yazılanları ("iki tablet", "yarım tablet", "bir çay kaşığı") cevaptan atar. `126 mg/dL` gibi tahlil değerlerine dokunmaz |
| 5 | Acil modda ek süzgeç | `chat/guard.py` | Acil modda hastalık adı geçen cümleleri **koddan** çıkarır (prompt kuralı yetmedi) |
| 6 | Çalışma anı doğrulama | `chat/verify.py` | Cevap cümlelerini kaynaklarla karşılaştırır, desteksizleri işaretler |
| 7 | Sabit uyarı | `chat/service.py` | Her cevabın sonuna tıbbi uyarı kod tarafından eklenir (modele bırakılmaz) |
| 8 | Triyajda taban kural | `assess/rules.py` | Kural seviyesi LLM tarafından aşağı çekilemez |
| 9 | Sunucu katmanı | `api/middleware.py` | Hız sınırı, gövde sınırı, CSP ve güvenlik başlıkları, isteğe bağlı erişim kodu |
| 10 | Gizlilik | tüm sistem | Görsel/ses saklanmaz, log gövde ve IP içermez, hesap yok |

**Ölçüm (`python -m medrag.eval safety`):**
- **Faz 1:** 13 senaryo, gerçek sunucu ve model, **13/13** (`eval/safety_results.md`).
- **Faz 2:** 40 senaryo (kaynağa gömülü talimat, jailbreak, 2 aylık bebek ateşi, gebelik kanaması, yeme bozukluğu,
  dolaylı kendine zarar, aşı–otizm yanlış bilgisi, nezleye antibiyotik, alkol + parasetamol, yaşlı düşmesi,
  İngilizce soru, kod isteği, çok uzun girdi, çocuk dozu, yazıyla doz, acilde teşhis adı yasağı, 4 yanlış alarm
  kontrolü). Rubrik düzeltmelerinden sonra **40/40**, ancak **yerel BM25 aramayla** (gerçek vektör arama denenmedi).
  İlk tam koşu 38/40 idi; iki hata hakem sertliği ve senaryo tasarımıydı.
- **Yanlış alarm:** 2/29 (%7): "yeme bozukluğu" (savunulabilir) ve uzun girdi (nötr metinle düzeltilip yeniden
  geçti). Bilgi amaçlı sorularda ("intihar nedir") da kriz mesajı çıkabilir.

Geliştirme sırasında bu testler gerçek hatalar yakaladı: kaynaktaki günlük üst sınırın cevaba sızması, akışın son
parçasında bağlantının kopması, konu dışı soruya tavsiye verilmesi, acil modda hastalık adının sızması.

---

## 11. Arayüz ve PWA

- **Tasarım:** sakin tıbbi yeşil-mavi vurgu, nötr yüzeyler, AA kontrast (açık ve koyu), 8 px ritim, yuvarlak
  kartlar, odak halkaları, `prefers-reduced-motion` desteği. Tüm stiller `web/static/base.css` ortak sistemindedir.
- **Ortak yardımcılar (`window.MedRAG`, `web/static/common.js`):** `renderMarkdown` (önce kaçışlar, güvenli),
  `streamSSE`, `postJSON`, `uploadFile`, `getJSON`, `toast`, `confirmDialog`, tema (sistem/açık/koyu), erişim kodu.
- **Tema:** `data-theme-toggle` düğmesi sistem → açık → koyu arasında döner, tercih yalnızca tarayıcıda saklanır.
- **Erişim kodu:** sunucu `MEDRAG_ACCESS_CODE` ile korunuyorsa `401 access_code_required` gelince arayüz kodu bir
  kez sorar, saklar ve isteği yeniden dener.
- **PWA:** `manifest.webmanifest` ("Sağlık Asistanı", 192/512 ve maskable PNG simgeler), `sw.js`: `/static/*` için
  önce önbellek, sayfalar için önce ağ ve çevrimdışı yedek sayfası. **`/api/*`, `/chat` ve GET dışı istekler asla
  önbelleğe alınmaz.**
- **Sohbet:** karşılama ve öneri çipleri, akışlı baloncuklar, Durdur düğmesi, 112 düğmeli acil bandı, genişleyen
  kaynak kartları, `[n]` atfına tıklayınca kart açılır, doğrulama işaretleri, 👍/👎 (`/api/feedback`), kopyala,
  sesli oku (tr-TR), mikrofon (MediaRecorder → `/api/speech/transcribe`, olmazsa tarayıcı SpeechRecognition,
  o da yoksa gizlenir), otomatik büyüyen metin kutusu, yeni sohbet, `localStorage`'da kalıcı geçmiş,
  `/?q=...` ile ön doldurma.
- **Tarayıcı doğrulaması:** Microsoft Edge, 390×844, açık ve koyu tema, 4 sayfa: konsol hatası yok, yatay
  kaydırma yok. Gerçek ses kaydı, sesli okuma ve `sw.js` çevrimdışı davranışı denenmedi.

### Diğer sayfalar

<table>
  <tr>
    <td align="center"><img src="docs/screens/ui/belirti-3-sonuc.png" width="230"><br><sub>Belirti sonucu (örnek yanıt)</sub></td>
    <td align="center"><img src="docs/screens/ui/tahlil-2-sonuc.png" width="230"><br><sub>Tahlil sonucu (kural tabanlı; bu görüntüde LLM açıklaması yok)</sub></td>
    <td align="center"><img src="docs/screens/ui/tahlil-3-fotograf.png" width="230"><br><sub>Fotoğraftan okuma sekmesi</sub></td>
    <td align="center"><img src="docs/screens/ui/hakkinda.png" width="230"><br><sub>Hakkında</sub></td>
  </tr>
</table>

### Masaüstü arayüzü (>= 1024 px)

Aynı HTML, yalnızca CSS ile geniş ekrana uyar (`base.css`, `chat.css`, `about.css` içindeki `@media (min-width: 1024px)`
blokları). Mobil düzen (alt gezinme, tek sütun) değişmedi.

- **Kabuk:** alt gezinme çubuğu sol kenar çubuğuna dönüşür (marka, Sohbet/Belirti/Tahlil/Hakkında, tema düğmesi,
  kısa uyarı ve 112 bağlantısı); sayfa başlığı içerikte büyük başlık olur. Gezinmeyi `common.js` `renderNav` çizer.
- **Sohbet:** 800 px okunaklı sütun, karşılamada örnek soru kartları ve araç kartları, kaynaklar yan yana iki kart
  olarak açık gelir, yazma kutusu altta ortalanmış ve sabit.
- **Belirti / Tahlil:** belirti sonucu kart ızgarası; tahlilde giriş solda, sonuç sağda (yapışkan). Aciliyet
  seviyesi rozetle (metin + nokta) ve kartın sol renk şeridiyle gösterilir; renk tek başına bilgi taşımaz.
- **Hakkında:** adımlar yatay akış, kaynak tablosu iki sütun, güvenlik ve gizlilik yan yana.
- **Tasarım dili:** CSS değişkenleriyle açık/koyu tema, harici font/kütüphane yok, satır içi SVG ikonlar, görünür
  klavye odağı, `prefers-reduced-motion` desteği.

<table>
  <tr>
    <td align="center"><img src="docs/screens/ui-pc/sohbet-karsilama-pc-light.png" width="420"><br><sub>Sohbet, karşılama (açık)</sub></td>
    <td align="center"><img src="docs/screens/ui-pc/sohbet-cevap-pc-dark.png" width="420"><br><sub>Kaynaklı cevap (koyu)</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screens/ui-pc/belirti-3-sonuc-pc-light.png" width="420"><br><sub>Belirti sonucu (örnek yanıt)</sub></td>
    <td align="center"><img src="docs/screens/ui-pc/tahlil-2-sonuc-pc-dark.png" width="420"><br><sub>Tahlil: giriş / sonuç (koyu)</sub></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><img src="docs/screens/ui-pc/hakkinda-pc-light.png" width="420"><br><sub>Hakkında</sub></td>
  </tr>
</table>

Tüm görüntüler `scripts/dev_server.py` sahte servisiyle alındı (1440x900, 1024x768 ve 390x844, açık/koyu):
`docs/screens/ui-pc/`. Belirti sonucu için API yanıtı sahtedir.

### Faz 1 görüntüleri (gerçek API)

<details>
<summary>Eski arayüzden, gerçek API ile alınmış görüntüler</summary>

| Normal soru | Acil durum | İlaç dozu sorusu |
|---|---|---|
| <img src="docs/screens/normal-light.png" width="240"> | <img src="docs/screens/acil-light.png" width="240"> | <img src="docs/screens/doz-light.png" width="240"> |

Koyu tema: `docs/screens/*-dark.png`.
</details>

---

## 12. Sunucu, dağıtım ve Docker

**Ara katman (`api/middleware.py`, saf ASGI; SSE akışını bozmaz):**

| Özellik | Varsayılan | Not |
|---|---|---|
| IP başına hız sınırı (token bucket) | sohbet: 20 burst / 30 dk; yükleme: 10 / 12 dk; diğer API: 60 / 120 dk | Aşılırsa `429 {"error":"rate_limited","retry_after":s}` + `Retry-After`. Kova sayısı LRU ile sınırlı (20.000) |
| Gövde sınırı | JSON 256 KB, yükleme 12 MB | Aşılırsa `413` JSON |
| Güvenlik başlıkları | CSP (`'self'`, satır içi stil/script serbest), `nosniff`, Referrer-Policy, Permissions-Policy (mikrofon/kamera `self`), `frame-ancestors 'none'`, HSTS isteğe bağlı | 401/429 yanıtlarında da gönderilir |
| Erişim kodu | kapalı | `MEDRAG_ACCESS_CODE` doluysa `/chat` ve `/api/*` `X-Access-Code` ister (sabit zamanlı karşılaştırma). Sayfalar, `/static`, `/health`, `/sw.js`, manifest ve `GET /api/meta/info` açık kalır |
| Günlük | JSON, istek kimlikli | **Gövde, sorgu parametresi, başlık ve IP yazılmaz** (IP için `MEDRAG_LOG_CLIENT_IP=1`) |
| Yapılandırma hatası | — | `EVREN_API_KEY` yoksa çökmek yerine `503 {"error":"config_error"}` döner |
| `X-Forwarded-For` | güvenilmez | Yalnızca `MEDRAG_TRUST_PROXY_HEADERS=1` iken kullanılır (vekil arkasında) |

Hız sınırı ve metrikler **süreç belleğindedir**; çok işçili çalışmada her işçi kendi sayacını tutar (varsayılan
`WEB_CONCURRENCY=1`).

**Docker (derlendi ve duman testinden geçti):**

```bash
docker build -t medrag .
docker run -p 8000:8000 -e EVREN_API_KEY=... medrag
# ya da .env dosyasıyla:
docker compose up -d --build
```

- `python:3.12-slim`, **root olmayan kullanıcı** (`medrag`, uid 10001), `HEALTHCHECK` (`/health`), `--proxy-headers`,
  `PORT` ve `WEB_CONCURRENCY` ortam değişkenleriyle ayarlanır.
- Doğrulama (17.10.2026): imaj derlendi; konteyner `healthy`; `/health`, `/`, `/assess`, `/labs`, `/about` 200;
  CSP başlığı ve `/api/meta/info` geliyor; kullanıcı `medrag`.
- İmaja ham veri ve embedding indeksi girer; `chunks.jsonl` ilk açılışta üretilir. Bu yüzden `GET /api/meta/info`
  içindeki kaynak sayıları ilk retriever yüklenene kadar boş görünebilir.
- Geri bildirim `data/feedback/feedback.jsonl` dosyasına yazılır; kalıcı olması için bu klasöre bir volume bağlayın.
- `deploy/` altında **Render** (`render.yaml`), **Fly.io** (`fly.toml`), VPS + **Caddy** (otomatik HTTPS,
  `Caddyfile`) ve **systemd** (`medrag.service`) örnekleri vardır. Sunucudan `evren-llmapi.ssyz.org.tr` adresine
  çıkış erişimi şarttır. Mikrofon ve kamera yalnızca HTTPS'te çalışır.
- Genel yayın için öneri: `MEDRAG_ACCESS_CODE`, `MEDRAG_HSTS=1`, vekil arkasında `MEDRAG_TRUST_PROXY_HEADERS=1`.

---

## 13. Hızlı başlangıç

**Gereksinimler:** Python 3.11+, Evren API anahtarı (`EVREN_API_KEY`) ve sunucunun
`evren-llmapi.ssyz.org.tr` adresine erişimi.

```bash
git clone https://github.com/furkancmc/phone && cd phone
git checkout ccr-fc8175dc-sqyb1k
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

export EVREN_API_KEY=...        # ya da .env dosyasına yaz (gitignore'da); anahtarı asla commit etme
python -m medrag.api            # http://localhost:8000
```

İlk açılışta `data/raw` içindeki ham veriden `data/chunks.jsonl` kendiliğinden üretilir (birkaç saniye). Embedding
indeksi (`data/index_bge_m3/`) git'e girmez; `python -m medrag.index embed --backend local` ile üretilir (~6 dk, GPU).

**API anahtarı olmadan arayüzü denemek:** `python scripts/dev_server.py` (sahte servislerle; gerçek API çağrısı yapmaz).

**Telefondan açmak:** Bilgisayar ve telefon aynı Wi-Fi'daysa telefon tarayıcısına
`http://<bilgisayarın-ip-adresi>:8000` yaz ve "Ana ekrana ekle" ile PWA olarak ekle.

**Yerel PC kurulumu:** `bash scripts/local/kur.sh` (Windows: `.\scripts\local\kur.ps1`) sanal ortamı kurar ve `.env`
oluşturur. Claude Code'u Evren API ile kullanmak için `scripts/local/litellm.yaml` içindeki adımlara bak.

---

## 14. Yapılandırma

Ayarlar `MEDRAG_` önekli ortam değişkenleri ya da `.env` ile verilir (`.env.example` örnektir; tam liste
`src/medrag/config.py`). `EVREN_API_KEY` önek almaz.

| Değişken (öneksiz alan adı) | Varsayılan | Anlamı |
|---|---|---|
| `EVREN_API_KEY` | — | **Zorunlu.** Evren API anahtarı |
| `data_dir`, `local_index_dir`, `top_k` | `data`, `data/index_bge_m3`, `5` | Veri ve indeks yeri, cevap için kaynak sayısı |
| `embed_backend`, `local_embed_model` | **`local`**, `BAAI/bge-m3` | Embedding arka ucu ve modeli (`api` seçeneği duruyor); model değişirse indeks yeniden üretilmeli |
| `embed_workers`, `embed_batch_size`, `embed_query_cache_size` | `16`, `64`, `1024` | Paralel istek, istek başına metin, sorgu önbelleği |
| `embed_backend`, `local_embed_model`, `local_embed_batch`, `local_index_dir` | `api`, `BAAI/bge-m3`, `32`, `data/index_bge_m3` | Yerel embedding ([bölüm 7](#yerel-embedding-bge-m3)); `rerank_backend` (`api`\|`local`) yerel reranker |
| `llm_model` | `deepseek-v4.1-flash` | Sohbet modeli |
| `answer_max_tokens`, `llm_extra_params` | `4096`, boş | Düşünen model token harcar; ek parametre JSON'u |
| `rerank_enabled` | **`false`** | Reranker (masraf nedeniyle kapalı); `rerank_pool` 40, `rerank_backend` `local` (`bge-reranker-v2-m3`) |
| `multiquery_enabled`, `multiquery_model` | `false`, `auto` | Çoklu sorgu |
| `verify_enabled`, `verify_model`, `verify_budget_seconds` | `true`, `deepseek-v4.1-flash`, `20` | Cevap doğrulama |
| `classifier_enabled`, `classifier_model`, `classifier_timeout_seconds` | `true`, `deepseek-v4.1-flash`, `8` | İkinci katman acil sınıflandırıcı |
| `guard_model` | boş | İsteğe bağlı koruma modeli (örn. `qwen3-guard-4b`) |
| `assess_model`, `assess_max_tokens`, `assess_sources_k` | `deepseek-v4.1-flash`, `4000`, `4` | Belirti değerlendirme |
| `labs_explain_model`, `vision_ocr_models`, `vision_chat_model`, `vision_extract_model` | `deepseek-v4.1-flash`, `deepseek-ocr-2,dots-ocr`, `qwen3-vl-30b`, `deepseek-v4.1-flash` | Tahlil ve görsel okuma |
| `speech_model`, `speech_mode`, `speech_max_bytes` | `qwen3-asr-1.7b`, `auto`, `10 MB` | Ses tanıma (`auto`/`transcriptions`/`chat`) |
| `access_code` | boş | Doluysa `/chat` ve `/api/*` `X-Access-Code` ister |
| `rate_limit_enabled`, `rate_*_burst`, `rate_*_per_min` | `true`, bkz. [Sunucu](#12-sunucu-dağıtım-ve-docker) | Hız sınırı |
| `trust_proxy_headers`, `hsts`, `csp`, `warmup` | `false`, `false`, boş, `false` | Vekil, HSTS, özel CSP, açılışta indeks ısıtma |
| `access_log`, `log_client_ip` | `true`, `false` | JSON erişim logu; IP varsayılan olarak yazılmaz |
| `feedback_max_bytes`, `feedback_keep` | `5 MB`, `3` | Geri bildirim dosyası döndürme |
| `europepmc_per_topic`, `index_max_float16_mb` | `3`, `40` | Veri hattı |

`OPENFDA_API_KEY` (isteğe bağlı) openFDA günlük istek bütçesini artırır.

---

## 15. API başvurusu

| Uç nokta | Ne yapar |
|---|---|
| `GET /`, `/assess`, `/labs`, `/about` | Sayfalar |
| `GET /health` | `{"status":"ok","ready":bool}`; `ready`, indeks ilk istekte yüklenince `true` |
| `POST /chat` (`/api/chat`) | `{message, history}` → SSE ([olaylar](#8-sohbet-servisi)) |
| `POST /api/assess/start` | Şikâyet + profil → kırmızı bayrak varsa `emergency`, yoksa 3–5 soru |
| `POST /api/assess/finish` | Cevaplar → `level`, `summary`, `reasons`, `red_flags_to_watch`, `self_care`, `sources` |
| `GET /api/labs/tests` | Desteklenen testlerin kataloğu (aralıklar, birimler, kaynak) |
| `POST /api/labs/interpret` | `{values:[{test,value,unit?,ref_low?,ref_high?}], sex?, age?}` → sınıflandırma + açıklama |
| `POST /api/vision/lab-report` | Tahlil fotoğrafı (multipart `file`) → okunan satırlar (onay için) |
| `POST /api/vision/medicine` | İlaç kutusu fotoğrafı → ad, etken madde, güç, form (doz yok) |
| `POST /api/speech/transcribe` | Ses (webm/ogg/mp4/mpeg/wav, ≤10 MB) → `{"text"}` |
| `POST /api/feedback` | `{rating: 1\|-1, page, question?, answer?, comment?}` → `{"ok":true}` (IP yok) |
| `GET /api/feedback/summary`, `GET /api/meta/metrics` | Özet ve metrikler (erişim koduyla korunur) |
| `GET /api/meta/info` | Sürüm, kaynak başına belge/parça sayısı, modeller, değerlendirme özeti |

```bash
curl -N -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Migren ile baş ağrısı arasındaki fark nedir?"}'
```

`message` 1–2000 karakter; `history` en fazla 20 mesaj. Geçersiz istek 422, anahtar eksikse 503 döner.

---

## 16. Workflow'lar (GitHub Actions)

API'ye erişen işler Actions'ta çalıştırılabilir; `EVREN_API_KEY` repo ayarlarında **Actions secret** olarak tanımlıdır.

| Workflow | Ne yapar |
|---|---|
| `CI` (`ci.yml`) | Her push'ta `ruff` ve `pytest` |
| `Veri çek` (`fetch-data.yml`) | Haftalık (pazar 03:17 UTC) ve elle: kaynakları indirir, `data/raw` altına commit'ler |
| `Arama değerlendirmesi` (`eval.yml`) | Soru üretir, yöntemleri karşılaştırır; `n`, `regenerate`, `methods` girdileri |
| `Güvenlik ve uçtan uca test` (`safety.yml`) | 40 senaryo; isteğe bağlı model karşılaştırması |
| `Belirti değerlendirme` (`assess.yml`) | 19 senaryoyu gerçek modelle koşar |
| `Tahlil` (`labs.yml`) | `sanity`, `raw`, `ocr` adımları (sentetik rapor görselleriyle OCR ölçümü) |
| `Platform` (`platform.yml`) | Ses tanıma tanısı (iki istek yolunun ham cevabı) + Docker derleme ve duman testi |
| `Ekran görüntüsü` (`screens.yml`) | Tüm sayfaların açık/koyu görüntüleri |
| `API denemesi` (`api-check.yml`) | API süre ve hata davranışı ölçümü |

---

## 17. Nasıl geliştirdik: süreç ve alınan kararlar

**Faz 1** tek akışta yürüdü: iskelet → veri hattı → indeks → arama → sohbet → API ve telefon sayfası →
değerlendirme → Docker/README. **Faz 2** yedi iş akışına bölündü (`PLAN.md`, görev tarifleri `docs/gorevler/A–G.md`):

| İş akışı | Kapsam | Sonuç |
|---|---|---|
| A Arama | reranker, çoklu sorgu, sorgu önbelleği, ölçüm araçları | Kod hazır; reranker kapalı |
| B Veri | Europe PMC, openFDA, NIH ODS, ~550 konu, artımlı int8 depo | 32.753 parça çekildi; indekse girmedi |
| C Güvenlik | doğrulama, LLM sınıflandırıcı, yazıyla doz, 40 senaryo | 40/40 (BM25 ile) |
| D Belirti | `/assess` sayfası, kural motoru | 18/19 senaryo |
| E Tahlil | `/labs`, 34 test, OCR, ilaç kutusu | Kural tabanlı sınıflandırma tamam |
| F Sunucu | hız sınırı, erişim kodu, geri bildirim, meta, ses, Docker | Docker doğrulandı |
| G Arayüz | tasarım sistemi, sohbet, hakkında, PWA | Edge ile doğrulandı |

Her iş akışı ayrı bir yapay zekâ ajanı tarafından **ayrı git çalışma kopyasında (worktree)** yürütüldü; dosya
sahipliği `PLAN.md`'de tanımlandığı için çakışmalar azdı (birleştirmede yalnızca `config.py` ve bir test dosyasında
küçük çakışma çıktı). Kesintiye karşı her ajan ilerleme notu (`docs/gelistirme-kayitlari/ILERLEME-*.md`) ve yama
yedeği tuttu. Sonuçlar tek tek ana dala birleştirildi ve her birleştirmeden sonra tüm testler çalıştırıldı.

**Başlıca kararlar ve gerekçeleri**

| Karar | Gerekçe |
|---|---|
| Vektör arama varsayılan; BM25 ve hybrid kodda ama kapalı | Ölçüm: recall@5 0,85 vs 0,46 (BM25) ve 0,81 (hybrid) |
| Embedding'i 1024 boyuta kesmek | Depolama 4'te 1, kalite kaybı küçük |
| Düz dosya + numpy, vektör veritabanı yok | ~13–33 bin parça için fazlası gereksiz; repoda durur, kurulum sıfır |
| Tüm LLM görevleri için `deepseek-v4.1-flash` | Proje sahibinin seçimi; yan görevlerde düşünme kapatıldı |
| Reranker ve çoklu sorgu varsayılan kapalı | Ölçülmeden açılmaz; reranker masraflı (soru başına ~40 doküman) |
| 8b embedding ve reranker ile gerçek çağrıları durdurmak | Masraf; tüm iş akışlarına yasak olarak bildirildi, gerçek doğrulama ertelendi |
| Sınıflandırma kural tabanlı, LLM yalnızca açıklar (tahlil) | LLM'in sayı uydurma riski; kural tabanlı sonuç denetlenebilir |
| Kural seviyesi LLM tarafından aşağı çekilemez (belirti) | Güvenli taraf; LLM hatasında "bugün hekim" |
| Rapor aralığı varsa o esas, yoksa hekime yönlendir (tahlil) | Aralıklar laboratuvara göre değişir; yerleşik aralık tek başına yetmez |
| WHO içeriğini almamak | CC BY-NC-SA lisansı ticari kullanımı kısıtlar |
| Doz bölümlerini veri aşamasında hiç almamak (openFDA) | Doz bilgisi hem filtre hem veri katmanında engellenir |
| Reranker/doğrulama hatasında sessiz geri dönüş | Yardımcı katman, asıl cevabı asla bozmamalı |
| Arayüzde dışarıdan font/CDN yok, satır içi script yok | Gizlilik ve CSP `'self'` uyumu |
| NIH ODS 403'ünü aşmamak, kaynağı isteğe bağlı yapmak | Bot korumasını delmek yerine açıkça raporlamak |

---

## 18. Test ve kalite

```bash
pip install -e ".[dev]"
pytest          # 420 test geçti, 1 atlandı; API'ye dokunmaz, LLM ve embedding sahte servislerle
ruff check .    # temiz
```

- Testler; arama (BM25, vektör, rerank ayrıştırma/parti/geri dönüş, LRU önbellek), veri hattı (ayrıştırma, parça
  kimliği, artımlı depo, int8 gidiş-dönüş), sohbet (doz filtresi, acil durum, doğrulama, sınıflandırıcı),
  belirti kuralları, tahlil ayrıştırma ve sınıflandırma, görsel okuma, sunucu katmanı (hız sınırı, gövde sınırı,
  başlıklar, erişim kodu, log sızıntısı, SSE) ve sayfaların sunulmasını kapsar.
- Gerçek API ile doğrulama Actions workflow'larında ya da yerelde (anahtar `.env`'de) yapılır.
- Prompt ya da güvenlik kodunu değiştirince `Güvenlik ve uçtan uca test` çalıştırılmalıdır.
- Commit mesajları kısa ve sade Türkçedir; anahtarlar asla repoya yazılmaz.

**Yeni özellik eklemek:** `src/medrag/api/routes/<ad>.py` içinde `router = APIRouter(prefix="/api/<ad>")`
tanımla (otomatik bulunur); bağımlılık için `Depends(deps.get_llm)` / `Depends(deps.get_retriever)`; testte
`app.dependency_overrides`. **Yeni sayfa:** `src/medrag/web/<ad>.html` → `/<ad>`; `base.css`, `common.js` ve
`<nav id="app-nav"></nav>`. **Yeni değerlendirme:** `src/medrag/eval/<ad>_cli.py` içinde `register(subparsers)`.

---

## 19. Maliyet notları

- **Embedding indeksi bir kez kurulur** ve artımlıdır (hash önbelleği). Bekleyen tek seferlik büyük iş: yeni
  ~19.500 parçanın embedding'i. Her arama sorusu yalnızca 1 kısa embedding çağrısı yapar (~20 token, önbellekli).
- **Reranker pahalıdır**, çünkü indekste durmaz ve her soruda 40 dokümanı yeniden okur (doküman başına ~450 token →
  soru başına tahminen ~18 bin token). Tam ölçüm (150 soru × birkaç yöntem) on milyon token mertebesine çıkar ve
  hız sınırına (429) takılır. Bunlar koddaki ayarlardan yapılmış **tahminlerdir, ölçülmüş değildir**.
- **Düşünen model (deepseek) yavaştır:** küçük bir istek bile düşünme bütçesini tüketebilir; belirti senaryosu
  başına ~130 sn ölçüldü. Yan görevlerde düşünme kapatılır; ana cevaplarda `answer_max_tokens` cömert tutulur.
- **Geri dönüldüğünde masrafı düşürmek için:** rerank havuzunu 10–15'e ve doküman metnini ~600 karaktere indir,
  ölçümü 40–50 soru ve 2 yöntemle yap, indeksi yeni verilerle tek seferde kur.

---

## 20. Bilinen sınırlar

- **Bilgi tabanı:** Çalışan indeks ~13 bin parça (~1.200 belge). Yeni 32,7 bin parça henüz indekste değil.
  Kapsam dışı konuda "bilgi bulamadım" demesi beklenir.
- **Tıbbi inceleme:** Tahlil referans aralıkları ve kritik eşikler, belirti kuralları bir hekim tarafından
  gözden geçirilmedi. Aralıklar laboratuvara göre değişir; sistem raporun kendi aralığını önceler.
- **Acil durum tespiti** kurallara ve bir LLM'e dayanır; her ifadeyi yakalamaz. Bilgi amaçlı sorularda ("intihar nedir")
  da kriz mesajı çıkabilir.
- **Doz filtresi** yazıyla yazılan yaygın ifadeleri yakalar ama her varyantı garanti etmez.
- **Güvenlik koşuları BM25 aramayla yapıldı**; gerçek vektör aramayla uçtan uca doğrulama yapılmadı.
- **Doğrulama hakemi LLM'dir**, sapabilir; yük altında 20 sn bütçe aşılabilir. İşaretleme, cümleyi cevap metninde
  tam eşleşmeyle bulur; bulunamayan cümleler yalnızca nottaki listede görünür.
- **OCR** yalnızca temiz sentetik görsellerle denendi; eğik, gürültülü ve gerçek telefon fotoğrafı doğruluğu
  ölçülmedi. Fotoğraftan okunan satırlar her zaman kullanıcı onayına sunulur.
- **Ses tanıma doğrulanmadı** (gerçek ses denenmedi); mikrofon, sesli okuma ve `sw.js` çevrimdışı akışı tarayıcıda
  uçtan uca denenmedi.
- **Gecikme:** Düşünen model yüzünden belirti ve tahlil açıklaması dakikaya yaklaşabilir.
- **Hız sınırı ve metrikler süreç belleğinde**; çok işçide işçi başına sayılır. CSP'de `'unsafe-inline'` açık.
- **Test sorularını ve hakemi LLM yazıyor**; ölçümler gerçek kullanımı birebir yansıtmaz.
- **Sunucu `evren-llmapi.ssyz.org.tr` adresine erişebilmeli.**
- **NIH ODS** kaynağı bot koruması nedeniyle alınamadı.
- Git geçmişinde yaklaşık 20 MB gereksiz dosya var (geçmişi yeniden yazmamak için bırakıldı).

---

## 21. Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `503 config_error` / `EVREN_API_KEY ... tanımlı değil` | Anahtarı ortam değişkeni ya da `.env` ile ver |
| "Şu an cevap veremiyorum" | Sunucu API'ye ulaşamıyor olabilir (ağ, anahtar, kota); ayrıntı sunucu logunda |
| `Vektörler mevcut chunk listesiyle uyuşmuyor` | Veri değişti; `python -m medrag.index embed --backend local` |
| `HTTP 429` | API ya da sunucu hız sınırı; istemci geri çekilip yeniden dener, sürerse paralelliği azalt |
| `LLM boş cevap verdi` | Düşünen model token bütçesini tüketmiş olabilir; `answer_max_tokens`'ı artır |
| Doğrulama hiç görünmüyor | Acil, konu dışı, kaynaksız ya da çok kısa cevaplarda atlanır; arayüz "olay yok"u da işler |
| Telefon sayfayı açamıyor | Aynı ağda olduklarını ve güvenlik duvarının 8000 portuna izin verdiğini kontrol et |
| Windows'ta Türkçe karakter bozuk | `PYTHONUTF8=1` kullan; dosyaları `encoding="utf-8"` ile aç |
| `fetch` çıkış kodu 1 | Zorunlu bir kaynak başarısız oldu; NIH ODS 403'ü çıkış kodunu etkilemez |

---

## 22. Dizin yapısı

```
src/medrag/
  config.py              ayarlar (MEDRAG_ ortam değişkenleri), ConfigError
  llm.py                 sohbet istemcisi (OpenAI uyumlu, akış, yeniden deneme, düşünen model)
  retrieve.py            vektör / bm25 / hybrid arama; isteğe bağlı çoklu sorgu ve rerank hattı
  rerank.py, multiquery.py, lru.py   reranker, sorgu genişletme, iş parçacığı güvenli önbellek
  ingest/                veri hattı: indirme, ayrıştırma, parçalama, kaynaklar (europepmc, openfda, nihods...)
  index/                 BM25, Türkçe ayrıştırıcı, embedding istemcisi, artımlı vektör deposu
  chat/                  acil durum, prompt, doz filtresi, doğrulama, sınıflandırıcı, sohbet servisi
  assess/                belirti değerlendirme: kurallar, modeller, servis
  labs/                  tahlil: referans tablosu, yorumlayıcı, açıklama servisi
  vision.py, speech.py   görsel okuma (OCR/VL) ve ses tanıma istemcileri
  observability.py       bellek içi metrikler, JSON günlük
  deps.py                paylaşılan, tembel yüklenen bağımlılıklar
  api/main.py            uygulama: sayfalar, statik dosyalar, /chat, rotaları otomatik ekler
  api/middleware.py      hız sınırı, gövde sınırı, başlıklar, erişim kodu, günlük
  api/routes/            assess, labs, vision, speech, feedback, meta
  web/                   index/assess/labs/about.html + static/ (base.css, common.js, chat.js, sw.js, PWA)
  eval/                  değerlendirmeler; her *_cli.py kendi alt komutunu ekler
data/raw/                      ham kaynaklar (repoda); data/index_bge_m3/ indeks (yerelde üretilir)
eval/                    test soruları ve sonuç raporları
docs/screens/, docs/img/ ekran görüntüleri ve diyagramlar
docs/gorevler/           iş akışı görev tarifleri (A–G)
docs/gelistirme-kayitlari/   ajanların ilerleme notları
deploy/                  Render, Fly.io, Caddy, systemd örnekleri
scripts/                 dev_server.py, screens.py, make_icons.py, local/ (kurulum)
tests/                   birim ve API testleri
.github/workflows/       CI ve elle çalışan workflow'lar
```

---

## 23. Yasal uyarı ve lisanslar

**Kaynak kod lisansı: [MIT](LICENSE).** Aşağıdaki veri lisansları koddan ayrıdır.

Bu proje bir eğitim ve araştırma çalışmasıdır. Ürettiği bilgiler **genel bilgilendirme** amaçlıdır; tıbbi tavsiye,
teşhis ya da tedavi yerine geçmez. Sağlık sorunlarınız için bir sağlık profesyoneline başvurun. Acil durumda
**112**'yi arayın.

Veri lisansları: MedlinePlus ve openFDA kamu malı; Vikipedi CC BY-SA 4.0 (atıf ve aynı lisans gerekir); Europe PMC
yalnızca CC BY / CC BY-SA lisanslı özetler. Vikipedi'den türeyen cevapları yayınlarken atıf ve lisans korunmalıdır.
Kaynak, bağlantı ve lisans her parçada saklanır ve kaynak kartlarında gösterilir.

---

## 24. Değişiklik günlüğü

### Faz 2
- **Arama (A):** reranker, çoklu sorgu, sorgu embedding önbelleği, yöntem karşılaştırma ve gecikme ölçümü. Reranker
  masraf nedeniyle varsayılan kapalı.
- **Veri (B):** Europe PMC, openFDA, NIH ODS (isteğe bağlı), ~550 konuluk Vikipedi listesi, parça meta verisi,
  kalite süzgeçleri, artımlı int8 embedding deposu, haftalık yenileme workflow'u.
- **Güvenlik (C):** çalışma anı doğrulama, LLM sınıflandırıcı, acil modda hastalık adı süzgeci, yazıyla doz yakalama,
  40 senaryo.
- **Belirti (D):** `/assess` sayfası, kural motoru, 5 yaş altı ateş kuralı.
- **Tahlil (E):** `/labs`, 34 testlik kaynaklı referans tablosu, rapor aralığı önceliği, OCR ve ilaç kutusu okuma.
- **Sunucu (F):** hız sınırı, gövde sınırı, güvenlik başlıkları, erişim kodu, geri bildirim, meta, ses tanıma,
  Docker (derlendi ve doğrulandı), barındırma örnekleri.
- **Arayüz (G):** yeni tasarım sistemi, sohbet, Hakkında, PWA, tema, erişim kodu akışı.
- **Düzeltmeler:** `EVREN_API_KEY` yokken sunucu çökmek yerine `503 config_error` döner; NIH ODS isteğe bağlı kaynak
  oldu; varsayılan model `deepseek-v4.1-flash` oldu; birleşen ajan dalları ve yedek yamalar temizlendi.

### Faz 1
- Doz içeren cümle tek bir açıklama cümlesiyle değiştiriliyor; acil cevapta hastalık adı verilmemesi kuralı.
- Gerçek API ile ekran görüntüleri, güvenlik senaryoları 13/13.
- Vektör arama varsayılan oldu (recall@5 0,85); hybrid ve BM25 isteğe bağlı.
- Qwen3 embedding indeksi (13.236 parça), seçili Vikipedi listesi, MedlinePlus.

Ayrıntılı yol haritası ve sözleşmeler: [`PLAN.md`](PLAN.md). Geliştirme kayıtları: `docs/gelistirme-kayitlari/`.
