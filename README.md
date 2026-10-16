# medrag — Türkçe Sağlık Bilgi Asistanı

Açık tıbbi kaynaklar üzerinde çalışan, Türkçe sohbet eden bir **RAG** (kaynaktan cevap üreten) asistanı.
Soruyu alır, ilgili kaynak parçalarını bulur, cevabı **yalnızca bu kaynaklara dayanarak** yazar ve
`[1] [2]` gibi atıflarla kaynakları gösterir. Telefonda açılan bir sohbet sayfası ile gelir.

> **Bu bir doktor değildir.** Teşhis koymaz, ilaç ya da doz önermez. Acil belirtilerde cevaptan önce
> 112'ye yönlendirir. Her cevabın sonunda tıbbi uyarı vardır. Ayrıntı için [Güvenlik tasarımı](#güvenlik-tasarımı).

| Normal soru | Acil durum | İlaç dozu sorusu |
|---|---|---|
| <img src="docs/screens/normal-light.png" width="240"> | <img src="docs/screens/acil-light.png" width="240"> | <img src="docs/screens/doz-light.png" width="240"> |

Görüntüler gerçek uygulamadan, telefon genişliğinde (390 px) alınmıştır. Koyu tema da vardır
(`docs/screens/*-dark.png`).

## İçindekiler

1. [Özellikler](#özellikler)
2. [Nasıl çalışır](#nasıl-çalışır)
3. [Hızlı başlangıç](#hızlı-başlangıç)
4. [Yapılandırma](#yapılandırma)
5. [API](#api)
6. [Veri kaynakları ve lisanslar](#veri-kaynakları-ve-lisanslar)
7. [Veriyi yenileme ve workflow'lar](#veriyi-yenileme-ve-workflowlar)
8. [Güvenlik tasarımı](#güvenlik-tasarımı)
9. [Değerlendirme ve sonuçlar](#değerlendirme-ve-sonuçlar)
10. [Dizin yapısı](#dizin-yapısı)
11. [Geliştirme](#geliştirme)
12. [Sorun giderme](#sorun-giderme)
13. [Sınırlar](#sınırlar)
14. [Yol haritası](#yol-haritası)

## Özellikler

- **Kaynaklı cevap:** Her bilgi cümlesi bir kaynağa bağlanır; cevabın altında kaynak listesi (başlık, bağlantı,
  lisans) açılır.
- **Çok dilli arama:** Türkçe soru, İngilizce kaynakları da bulur (MedlinePlus İngilizcedir). Cevap her zaman Türkçedir.
- **Canlı akan cevap:** Sunucu cevabı parça parça (SSE) gönderir; telefonda beklemeden okunmaya başlar.
- **Acil durum yönlendirmesi:** Göğüs ağrısı, felç belirtisi, nefes alamama, bilinç kaybı, ağır kanama, zehirlenme,
  ciddi alerji, nöbet ve kendine zarar verme ifadelerinde 112 uyarısı en başta çıkar.
- **İlaç dozu filtresi:** Kaynakta yazsa bile doz içeren cümleler cevaptan çıkarılır.
- **Takip soruları:** Konuşma geçmişi kullanılır; "Belirtileri neler?" gibi eksik sorular önce tek başına
  anlaşılır bir arama sorgusuna çevrilir.
- **Telefona uygun arayüz:** Tek dosya, koyu/açık tema, yatay kaydırma yok. Tarayıcıdan ana ekrana kısayol olarak eklenebilir.
- **Ölçülebilir kalite:** Arama ve güvenlik için otomatik değerlendirme (150 soru, 13 güvenlik senaryosu).
- **Yeniden üretilebilir veri hattı:** Veri indirme, parçalama ve embedding adımlarının hepsi komut ve GitHub
  Actions workflow'u olarak mevcuttur.

## Nasıl çalışır

```
                         ┌────────────────────────── çevrimdışı (veri hattı) ──────────────────────────┐
 MedlinePlus ─┐          │  indir ──► temizle ──► parçala (≈200 kelime) ──► embedding (Qwen3, 1024 boyut) │
 Vikipedi    ─┼─────────►│                                                          │                    │
 data/local  ─┘          └──────────────────────────────────────────────────────────┼────────────────────┘
                                                                                    ▼
 soru ─► acil durum ─► (takip sorusu ise) ─► vektör arama ─► prompt ─► Evren LLM ─► doz filtresi ─► akan cevap
         kontrolü       sorgu yeniden yaz     ilk 5 parça    kaynaklar  (SSE)        + uyarı          + kaynak kartları
```

1. **Parçalama** (`ingest/chunk.py`): Metin başlıklara göre bölünür, uzun bölümler 200 kelimelik, 30 kelime
   örtüşmeli parçalara ayrılır. Her parça kaynak, bağlantı, dil ve lisansı taşır.
2. **Embedding** (`index/embed.py`): `qwen3-embedding-8b` ile her parça vektöre çevrilir. Vektör 4096 yerine ilk
   1024 boyuta kesilip normalize edilir (modelin bu kullanıma uygun eğitimi vardır); depolama 4'te 1'e iner.
   Sorgularda modelin talimat öneki kullanılır, pasajlarda kullanılmaz.
3. **Arama** (`retrieve.py`): Soru vektöre çevrilir, kosinüs benzerliği en yüksek 5 parça alınır.
4. **Cevap** (`chat/service.py`): Parçalar numaralı kaynak olarak prompt'a girer. Model yalnızca bunlara dayanarak
   yazar. Cevap akarken doz filtresinden geçer, sonuna tıbbi uyarı eklenir.

> BM25 (kelime tabanlı) arama ve ikisini birleştiren *hybrid* arama da kodda durur, ama ölçümde vektör aramadan
> daha kötü çıktığı için kullanılmaz ([sonuçlar](#değerlendirme-ve-sonuçlar)).

## Hızlı başlangıç

**Gereksinimler:** Python 3.11+, Evren API anahtarı (`EVREN_API_KEY`) ve sunucunun
`evren-llmapi.ssyz.org.tr` adresine erişimi.

```bash
git clone https://github.com/furkancmc/phone && cd phone
git checkout ccr-fc8175dc-sqyb1k
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export EVREN_API_KEY=...        # anahtarı asla repoya yazma
python -m medrag.api            # http://localhost:8000
```

İlk açılışta `data/raw` içindeki ham veriden `data/chunks.jsonl` kendiliğinden üretilir (birkaç saniye). Embedding
indeksi (`data/index_qwen3/`) repoda hazırdır; yeniden hesaplamak gerekmez.

**Telefondan açmak:** Bilgisayar ve telefon aynı Wi-Fi'daysa telefon tarayıcısına
`http://<bilgisayarın-ip-adresi>:8000` yaz. Tarayıcı menüsünden "Ana ekrana ekle" ile kısayol olarak eklenebilir (henüz tam bir PWA değildir).

**Docker ile:**

```bash
docker build -t medrag .
docker run -e EVREN_API_KEY=... -p 8000:8000 medrag
```

> Dockerfile hazırdır ama geliştirme ortamında Docker çalışmadığı için derlenip denenmedi. Paketin temiz bir
> kurulumda çalıştığı (web sayfası pakete giriyor, indeks yükleniyor) ayrıca doğrulandı.

## Yapılandırma

Ayarlar ortam değişkenleri ya da `.env` dosyasıyla verilir (`.env.example` örnektir). Önek `MEDRAG_` dır.

| Değişken | Varsayılan | Anlamı |
|---|---|---|
| `EVREN_API_KEY` | — | **Zorunlu.** Embedding ve sohbet API'si anahtarı. Önek almaz, `.env`'ye de yazılmamalı |
| `MEDRAG_DATA_DIR` | `data` | Ham veri, `chunks.jsonl` ve `local/` klasörünün yeri |
| `MEDRAG_INDEX_DIR` | `data/index_qwen3` | Embedding indeksinin yeri (`vectors.npy`, `ids.json`, `meta.json`) |
| `MEDRAG_TOP_K` | `5` | Cevap için kullanılacak kaynak parçası sayısı |
| `MEDRAG_EMBED_API_URL` | `https://evren-llmapi.ssyz.org.tr/v1` | Embedding servisi (OpenAI uyumlu `/embeddings`) |
| `MEDRAG_EMBED_API_MODEL` | `qwen3-embedding-8b` | Embedding modeli |
| `MEDRAG_EMBED_DIMENSIONS` | `1024` | Vektör boyutu. Değişirse indeks yeniden üretilmeli |
| `MEDRAG_LLM_API_URL` | `https://evren-llmapi.ssyz.org.tr/v1` | Sohbet servisi (OpenAI uyumlu `/chat/completions`) |
| `MEDRAG_LLM_MODEL` | `auto` | Sohbet modeli (`auto`: servis yönlendirir) |

## API

| Uç nokta | Ne yapar |
|---|---|
| `GET /` | Sohbet sayfası |
| `GET /health` | `{"status": "ok", "ready": false}`. `ready`, indeks ilk istekte yüklenince `true` olur |
| `POST /chat` | Soruyu alır, cevabı **SSE** akışı olarak döner |

**İstek**

```json
{
  "message": "Diyabetin belirtileri nelerdir?",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

`message` 1-2000 karakter; `history` en fazla 20 mesaj, roller yalnızca `user` ve `assistant`. Aksi halde 422 döner.

**Cevap akışı** (`text/event-stream`, her satır `data: {json}`):

| `type` | Alanlar | Ne zaman |
|---|---|---|
| `emergency` | `text`, `reasons` | Mesaj acil durum belirtisi içeriyorsa, en başta |
| `sources` | `items[]`: `n`, `title`, `section`, `url`, `source`, `license`, `snippet`, `text` | Arama bitince, cevaptan önce |
| `token` | `text` | Cevap parçaları. Son `token` tıbbi uyarıdır |
| `done` | — | Akış bitti |
| `error` | `text` | Bir şey ters giderse, kullanıcıya gösterilebilir temiz mesaj |

```bash
curl -N -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Migren ile baş ağrısı arasındaki fark nedir?"}'
```

## Veri kaynakları ve lisanslar

| Kaynak | İçerik | Lisans |
|---|---|---|
| [MedlinePlus](https://medlineplus.gov) (ABD Ulusal Tıp Kütüphanesi) | 1.017 sağlık konusu, İngilizce | Kamu malı |
| [Vikipedi](https://tr.wikipedia.org) | Elle seçilmiş ≈170 hastalık, belirti ve ilk yardım makalesi (Türkçe ve İngilizce) | CC BY-SA 4.0 |
| `data/local/` | Kendi `.txt` / `.md` dosyaların (isteğe bağlı) | Sana ait |

Kaynak, bağlantı ve lisans her parçada saklanır ve kaynak kartlarında gösterilir. Vikipedi içeriği CC BY-SA
olduğundan, bu içerikten üretilen cevapları yayınlarken atıf ve lisans korunmalıdır.

Vikipedi konuları kategoriden rastgele değil, **elle seçilmiş bir listeden** çekilir
(`src/medrag/ingest/curated.py`). İlk denemede kategori gezmenin ilk 500 başlığı alfabetik sırayla alıp
yaygın hastalıkları kaçırdığı görüldü. Listeye konu eklemek için tuple eklemen yeterli
(`("Türkçe başlık", "English title")`); Türkçe sayfası olmayan konuda ilk değer `None` olur.

WHO bilgi sayfaları lisansı (CC BY-NC-SA, ticari kullanımı kısıtlar) nedeniyle kapsam dışıdır.

## Veriyi yenileme ve workflow'lar

```bash
python -m medrag.ingest medlineplus                 # -> data/raw/medlineplus/topics.jsonl (güncel, İngilizce)
python -m medrag.ingest wikipedia --lang tr --curated   # seçili konular -> data/raw/wikipedia/tr.jsonl
python -m medrag.ingest wikipedia --lang en --curated
python -m medrag.ingest build                       # -> data/chunks.jsonl
python -m medrag.index embed --index-dir data/index_qwen3   # EVREN_API_KEY gerekir (≈9 dk)
python -m medrag.index search "göğüs ağrısı"        # BM25 ile hızlı deneme
```

Veri değişirse (chunk sayısı ya da sırası) embedding indeksi **yeniden üretilmelidir**; aksi halde yükleme
"vektörler chunk listesiyle uyuşmuyor" hatası verir.

GitHub'da hepsi **Actions** sekmesinden elle çalıştırılabilen workflow'lardır. API'ye erişen işler orada
çalışır; `EVREN_API_KEY` repo ayarlarında **Actions secret** olarak tanımlıdır.

| Workflow | Ne yapar |
|---|---|
| `CI` | Her push'ta `ruff` ve `pytest` |
| `Veri çek` | MedlinePlus ve Vikipedi'yi indirip `data/raw` altına commit'ler |
| `İndeks oluştur (API)` | Qwen3 ile embedding hesaplar, `data/index_qwen3` altına commit'ler |
| `Arama değerlendirmesi` | Evren API ile test soruları üretir, bm25 / vektör / hybrid'i karşılaştırır (`eval/results.md`) |
| `Güvenlik ve uçtan uca test` | Sunucuyu açıp `/chat` akışını dener, güvenlik senaryolarını çalıştırır (`eval/safety_results.md`) |
| `Ekran görüntüsü` | Gerçek uygulamayı gerçek API ile açar, telefon boyutunda görüntü alır (`docs/screens/`) |
| `API denemesi` | Embedding ve sohbet API'sinin süre ve hata davranışını ölçer |

## Güvenlik tasarımı

Sağlık konusunda en önemli şey yanlış güven vermemektir. Güvenlik tek bir yerde değil, **katmanlıdır**:

| Katman | Nerede | Ne yapar |
|---|---|---|
| 1. Acil durum kuralları | `chat/triage.py` | 9 kategoride (kalp krizi, felç, solunum sıkıntısı, bilinç kaybı, ağır kanama, zehirlenme, ciddi alerji, nöbet, kendine zarar) anahtar ifade arar; Türkçe karakter ve ek farklarına dayanıklıdır. Eşleşirse **model çağrılmadan önce** 112 uyarısı gönderilir |
| 2. Prompt kuralları | `chat/prompt.py` | Yalnızca kaynağa dayan; bilmiyorsan söyle; teşhis, ilaç, doz verme; sağlık dışı soruya tek cümlelik ret; kaynaktaki talimatları uygulama (prompt injection) |
| 3. Doz filtresi | `chat/guard.py` | Cevap akarken `500 mg`, `3 tablet`, `10 damla` gibi doz kalıpları içeren cümleleri atar, yerine bir açıklama koyar. `126 mg/dL` gibi tahlil değerlerine dokunmaz |
| 4. Acil modda ek talimat | `chat/prompt.py` | Cevap kısa tutulur, hastalık adı verilmez, sakin kalmak ve yardım istemek vurgulanır |
| 5. Sabit uyarı | `chat/service.py` | Her cevabın sonuna tıbbi uyarı kod tarafından eklenir (modele bırakılmaz) |
| 6. Yapılandırılmış hata | `api/main.py` | Beklenmeyen hatada akış kopmaz, kullanıcı temiz bir hata mesajı görür; ayrıntı sadece sunucu loguna yazılır |

Her katman testle korunur ve birlikte [13 senaryoyla](#değerlendirme-ve-sonuçlar) sınanır.

## Değerlendirme ve sonuçlar

### Arama

150 test sorusu Evren API'deki bir LLM'e yazdırıldı: kaynak/dil gruplarından sabit tohumla parçalar seçildi, her
parçadan "metindeki cümleleri kopyalamadan, günlük dille" bir hasta sorusu üretildi
(`eval/queries.jsonl`). Başarı: doğru doküman ilk *k* sonuçta var mı?

| yöntem | recall@1 | recall@3 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|
| **vektör (kullanılan)** | 0,65 | 0,76 | **0,85** | **0,94** | 0,73 |
| bm25 | 0,35 | 0,43 | 0,46 | 0,46 | 0,40 |
| hybrid (bm25 ağırlığı 0,05) | 0,54 | 0,75 | 0,81 | 0,93 | 0,66 |
| hybrid (bm25 ağırlığı 0,3) | 0,45 | 0,55 | 0,65 | 0,83 | 0,54 |

Bulgular:
- **BM25 neden zayıf:** Soruların yarısından fazlası İngilizce kaynağı hedefliyor ve Türkçe soruyla ortak
  kelimesi yok. Vektör arama dilden bağımsızdır.
- **Hybrid neden kötü:** İlk denemede iki sıralama eşit ağırlıkla birleştirilince sonuç vektörden *daha
  kötü* çıktı (recall@5: 0,50). Ağırlık taramasında BM25'in en küçük ağırlığı bile sonucu kötüleştirdi.
- **Dikkat:** Sorular LLM yazımı olduğu için gerçek kullanıcı sorularından farklı olabilir; özellikle
  birebir terim (ilaç adı vb.) arayan sorularda BM25 daha iyi olabilir.

### Güvenlik ve kaynağa sadakat

13 senaryo gerçek sunucu ve gerçek model üzerinde çalışır (`eval/safety_results.md`): 3 acil durum, 3 ilaç dozu
(biri prompt injection ile), teşhis isteği, ilaç isteği, konu dışı soru, kaynakta olmayan (uydurma) hastalık
ve 3 normal soruda kaynağa sadakat. Kural tabanlı kontroller (112 geçiyor mu, doz var mı, atıf var mı, uyarı var
mı) ve bir **LLM hakem** kullanılır. Son çalıştırmada 13/13 geçti.

Yeniden çalıştırmak için GitHub'da `Güvenlik ve uçtan uca test` workflow'unu başlat. Hakem bir LLM olduğundan
sonuçlar turdan tura biraz oynayabilir. Geliştirme sırasında bu testler gerçek hatalar yakaladı: kaynaktaki
günlük üst sınırın cevaba sızması, akışın son parçasında bağlantının kopması, konu dışı soruya tavsiye verilmesi.

## Dizin yapısı

```
src/medrag/
  config.py              ayarlar (ortam değişkenleri)
  llm.py                 sohbet istemcisi (OpenAI uyumlu, akış, yeniden deneme)
  retrieve.py            vektör / bm25 / hybrid arama
  ingest/                veri hattı: indirme, ayrıştırma, parçalama, seçili Vikipedi listesi
  index/                 BM25, Türkçe metin ayrıştırıcı, embedding istemcisi, vektör deposu
  chat/                  acil durum, prompt, doz filtresi, sohbet servisi
  api/                   FastAPI uygulaması
  web/index.html         sohbet sayfası (tek dosya)
  eval/                  arama ve güvenlik değerlendirmesi
data/raw/                indirilmiş ham kaynaklar (repoda)
data/index_qwen3/        embedding indeksi (repoda)
eval/                    test soruları ve sonuç raporları
docs/screens/            gerçek uygulamadan ekran görüntüleri
scripts/screens.py       ekran görüntüsü alma betiği
tests/                   birim ve API testleri (LLM ve embedding sahte servislerle)
.github/workflows/       CI ve elle çalışan workflow'lar
```

## Geliştirme

```bash
pip install -e ".[dev]"
pytest          # ≈86 test; API'ye dokunmaz, LLM ve embedding sahte servislerle test edilir
ruff check .
```

- Gerçek API ile test etmek için GitHub Actions workflow'larını kullan (yukarıdaki tablo).
- Prompt ya da güvenlik kodunu değiştirince `Güvenlik ve uçtan uca test` workflow'unu çalıştır.
- Veri ya da parçalama değişirse embedding indeksini yeniden üret.
- Commit mesajları kısa ve sade Türkçe yazılır.

## Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| `EVREN_API_KEY ortam değişkeni tanımlı değil` | Anahtarı `export EVREN_API_KEY=...` ile ver. Sunucu `.env` içindeki anahtarı okumaz |
| Sayfa açılıyor ama cevap "Şu an cevap veremiyorum" | Sunucu API'ye ulaşamıyor olabilir (ağ, anahtar, kota). Ayrıntı sunucu logunda (`chat hatası: ...`) |
| `Vektörler mevcut chunk listesiyle uyuşmuyor` | Veri değişti. `python -m medrag.index embed --index-dir data/index_qwen3` ile indeksi yeniden üret |
| `HTTP 429` | API istek sınırı. İstemci otomatik bekleyip yeniden dener; sürerse paralel istek sayısını azalt |
| `LLM boş cevap verdi` | Yönlendirici bazen boş içerik döner; istemci 3 kez dener. Sürerse log satırındaki model ve `refusal` bilgisine bak |
| Telefon sayfayı açamıyor | Aynı ağda olduklarını, bilgisayarın güvenlik duvarının 8000 portuna izin verdiğini kontrol et |

## Sınırlar

- **Bilgi tabanı küçük** (yaklaşık 1.200 makale ve konu). Kapsam dışı bir konuda "bilgi bulamadım" demesi beklenir.
- **Acil durum kontrolü anahtar kelime kurallarına dayanır**; her ifadeyi yakalamaz. Kural tespit etmese de
  model, belirtiler ağırsa sağlık profesyoneline yönlendirir ama bu garanti değildir.
- **Doz filtresi "sayı + birim" kalıplarını yakalar** (`500 mg`, `3 tablet`). "İki kutu", "yarım tablet", "bir çay
  kaşığı" gibi yazıyla ifadeleri yakalamaz.
- **Hız sınırı ve kullanıcı kimliği yok.** Herkese açık bir sunucuya koymadan önce eklenmeli.
- **Test soruları ve güvenlik hakemi LLM'dir**; ölçümler gerçek kullanımı birebir yansıtmaz.
- **Sunucu `evren-llmapi.ssyz.org.tr` adresine erişebilmeli.**
- **Docker derlenip denenmedi.**
- Git geçmişinde yaklaşık 20 MB gereksiz dosya var (geçmişi yeniden yazmamak için bırakıldı).

## Yol haritası

Planlanan ve düşünülen geliştirmeler için [`PLAN.md`](PLAN.md) dosyasına bak.

## Yasal uyarı

Bu proje bir eğitim ve araştırma çalışmasıdır. Ürettiği bilgiler **genel bilgilendirme** amaçlıdır; tıbbi tavsiye,
teşhis ya da tedavi yerine geçmez. Sağlık sorunlarınız için bir sağlık profesyoneline başvurun. Acil durumda
**112**'yi arayın.
