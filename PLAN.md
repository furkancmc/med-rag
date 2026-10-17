# Yol haritası

Açık tıbbi kaynaklar üzerinde RAG ile çalışan Türkçe sağlık bilgi asistanı. Embedding ve cevap üretimi
Evren API (OpenAI uyumlu; embedding: `qwen3-embedding-8b`, sohbet: `auto`, H200 üzerinde) ile yapılır.
Cevaplar yalnızca kaynaklara dayanır ve kaynak gösterir.

## Faz 1 — Temel sistem (tamamlandı)

- [x] 1. İskelet: pyproject, ayarlar, CI, README
- [x] 2. Veri hattı: MedlinePlus + seçili Vikipedi (tr/en) indirme, ayrıştırma, parçalama
- [x] 3. İndeks: `qwen3-embedding-8b` (1024 boyut), BM25 (düz dosya)
- [x] 4. Arama: vektör (ölçümle seçildi), BM25 ve hybrid isteğe bağlı; recall@k ölçümü
- [x] 5. Sohbet servisi: prompt, acil durum kontrolü, Evren LLM, [1] [2] atıfları, doz filtresi
- [x] 6. FastAPI (SSE akış) ve telefona uygun web sayfası
- [x] 7. Arama değerlendirmesi (150 soru) ve güvenlik senaryoları (13/13)
- [x] 8. Dockerfile, README, gerçek API ile ekran görüntüleri

## Faz 2 — Gelişmiş özellikler (devam ediyor)

Hedef: daha doğru arama, daha geniş ve güncel bilgi tabanı, "doktor gibi" yapılandırılmış değerlendirme,
çalışma anında doğrulanan cevaplar, yeni sayfalar ve modern arayüz, üretime hazır sunucu.
İşler paralel ajanlarla yürütülür; her iş akışının dosya sahipliği aşağıda tanımlıdır.

### A. Arama: reranker ve sorgu genişletme
- [ ] Reranker katmanı: vektör aramadan 30-50 aday, yeniden sıralayıp ilk 5. Evren API'de rerank uç noktası
      varsa onu, yoksa sohbet modeliyle paralel puanlama (H200 için yüksek eşzamanlılık) kullan.
- [ ] Çoklu sorgu: soru + İngilizce çevirisi + 1-2 yeniden yazım ile arama, sonuçları birleştir.
- [ ] `Retriever.search(query, k)` arayüzü korunur (sohbet servisi değişmeden faydalanır).
- [ ] Değerlendirme: vektör / vektör+rerank / çoklu sorgu+rerank karşılaştırması, gecikme ölçümü.
- [ ] Test setini 150'den 500 soruya çıkar (yüksek eşzamanlılıkla üretim).
- Kabul: recall@1 ve MRR'de ölçülebilir artış; sonuç `eval/results.md`'de.

### B. Veri: güncel ve kaliteli kaynaklar
- [ ] Europe PMC: 2020 ve sonrası, CC BY lisanslı derleme (review) makalelerinin özetleri (seçili konular).
- [ ] openFDA ilaç prospektüsleri (kamu malı): endikasyon, uyarı, yan etki, etkileşim. Doz bölümleri alınmaz.
- [ ] CDC (kamu malı) hastalık ve korunma sayfaları.
- [ ] Seçili Vikipedi listesini genişlet (≈400 konu; Türkiye'de sık görülen hastalıklar dahil).
- [ ] Her parçada kaynak, lisans, yayın/güncelleme ve çekilme tarihi.
- [ ] Embedding önbelleği: metin özeti (hash) ile sadece yeni/değişen parçalar yeniden hesaplanır.
- [ ] Haftalık otomatik yenileme workflow'u; yüksek ama kaynakların sınırlarına saygılı eşzamanlılık.
- Kabul: yeni kaynaklar indeksli, lisanslar kartlarda görünür, değerlendirme yeniden çalıştırılmış.

### C. Güvenlik ve doğrulama
- [x] Çalışma anında cevap doğrulama: akış bitince cevap cümleleri kaynaklarla karşılaştırılır,
      desteklenmeyenler `verification` olayıyla işaretlenir.
- [x] Acil durum için ikinci katman: kurallara ek LLM sınıflandırıcı (gecikme eklememek için paralel).
- [x] Acil modda hastalık adı geçen cümleleri koddan çıkar (prompt kuralı yetmedi).
- [x] Yazıyla yazılmış dozları yakala ("iki tablet", "yarım tablet", "bir çay kaşığı").
- [x] Güvenlik setini 13'ten 30+ senaryoya çıkar: kaynağa gömülü talimat (prompt injection), jailbreak,
      çocuk, gebelik, yeme bozukluğu, yanlış bilgi düzeltme, kendine zarar varyantları.
- Kabul: tüm senaryolar gerçek API ile geçer; yanlış alarm oranı raporlanır.

### D. Belirti değerlendirme (yeni sayfa)
- [ ] Kullanıcı ana şikâyetini yazar; asistan en fazla 5 hedefli soru sorar (seçenekli).
- [ ] Sonuç: aciliyet seviyesi (112 / bugün hekime / birkaç gün içinde randevu / evde izle), gerekçe,
      dikkat edilecek kırmızı bayraklar, kaynaklar.
- [ ] Kural tabanlı kırmızı bayraklar LLM kararını her zaman yukarı çeker (asla aşağı çekmez).
- Kabul: birim testler + gerçek API ile senaryo testleri.

### E. Tahlil yorumu ve görsel okuma (yeni sayfa)
- [ ] Sık tahliller için referans aralıkları tablosu (kaynaklı, birim dönüşümlü, yetişkin).
- [ ] Değerleri düşük/normal/yüksek sınıflandır (kural tabanlı), açıklamayı kaynaklı LLM yazsın.
- [ ] Tahlil sonucu fotoğrafından değer okuma ve ilaç kutusu fotoğrafından ilaç adı okuma (görsel model).
- [ ] Görseller saklanmaz, sadece istek süresince işlenir.

### F. Sunucu ve üretim hazırlığı
- [ ] Hız sınırı (IP başına), istek boyutu sınırı, güvenlik başlıkları (CSP vb.).
- [ ] İsteğe bağlı erişim kodu (barındırırken), geri bildirim (👍/👎) kaydı, metrik uç noktası.
- [ ] Sorgu embedding önbelleği, yapılandırılmış log (kişisel veri yazmadan).
- [ ] Docker: root olmayan kullanıcı, healthcheck; docker-compose; barındırma notları.

### G. Arayüz (modern ve sade)
- [ ] Ortak tasarım sistemi (`web/static/base.css`), ortak yardımcılar (`web/static/common.js`).
- [ ] Sayfalar: Sohbet, Belirti Değerlendirme, Tahlil Yorumu, Hakkında (kaynaklar, nasıl çalışır, uyarılar).
- [ ] Alt gezinme çubuğu (telefon), koyu/açık tema, erişilebilirlik.
- [ ] Sesle soru sorma ve sesli dinleme (tarayıcı), doğrulama işaretleri, geri bildirim butonları, PWA.
- Kabul: tüm sayfalar 390 px'te yatay kaydırmasız, JS hatasız; gerçek API ile ekran görüntüleri.

### H. Belgeler
- [ ] Her birleştirmeden sonra README ve değişiklik günlüğü güncellenir.

## Paralel çalışma düzeni

Her iş akışı ayrı bir ajan tarafından ayrı bir çalışma kopyasında (worktree) yürütülür, sonra ana dala
birleştirilir. Çakışmayı önlemek için dosya sahipliği:

| İş akışı | Sahip olduğu dosyalar |
|---|---|
| A. Arama | `retrieve.py`, `rerank.py` (yeni), `index/embed.py`, `eval/search_cli.py`, `eval/queries.py`, `eval/metrics.py`, `.github/workflows/eval.yml` |
| B. Veri | `ingest/**`, `index/store.py`, `index/__main__.py`, `.github/workflows/fetch-data.yml`, `build-index-api.yml` |
| C. Güvenlik | `chat/**`, `eval/safety.py`, `eval/safety_cli.py`, `.github/workflows/safety.yml` |
| D. Değerlendirme | `assess/**` (yeni), `api/routes/assess.py`, `web/assess.html` |
| E. Tahlil | `labs/**` (yeni), `vision.py` (yeni), `api/routes/labs.py`, `web/labs.html` |
| F. Sunucu | `api/middleware.py`, `api/routes/feedback.py`, `api/routes/meta.py`, `Dockerfile`, `docker-compose.yml` |
| G. Arayüz | `web/static/**`, `web/index.html`, `web/about.html`, PWA dosyaları |
| Ortak (ana oturum) | `README.md`, `PLAN.md`, `api/main.py`, `deps.py`, `config.py` (her akışın kendi bloğu), `pyproject.toml` |

## Modüller arası sözleşmeler

- **Arama:** `Retriever.search(query: str, k: int) -> list[Hit]` imzası korunur.
- **Bağımlılıklar:** `medrag.deps` içinde `get_settings()`, `get_retriever()`, `get_llm()`,
  `get_chat_service()`; testlerde `app.dependency_overrides` ile değiştirilir.
- **Yeni API uç noktaları:** `src/medrag/api/routes/<ad>.py` içinde `router = APIRouter(prefix="/api/<ad>")`;
  `api/main.py` bunları otomatik bulur.
- **Sayfalar:** `web/<ad>.html` dosyası `/<ad>` adresinden sunulur; statik dosyalar `/static/...`.
  Sayfalar `<nav id="app-nav"></nav>` yer tutucusu ve `/static/base.css`, `/static/common.js` kullanır.
- **`common.js` (window.MedRAG):** `renderMarkdown(text)`, `streamSSE(url, body, onEvent)`,
  `postJSON(url, body)`, `escapeHtml(s)`; gezinme çubuğunu `#app-nav` içine kendisi çizer.
- **Sohbet SSE olayları:** `emergency`, `sources`, `token`, `verification`
  (`{"type": "verification", "checked": n, "unsupported": [{"sentence": str, "reason": str}]}`),
  `done`, `error`.
- **Geri bildirim:** `POST /api/feedback` `{"rating": 1 | -1, "page": str, "question": str?, "answer": str?, "comment": str?}`.
- **Hakkında bilgisi:** `GET /api/meta/info` → `{"version", "sources": [{"source", "license", "documents", "chunks"}], "models": {...}, "eval": {...}}`.
- **Erişim kodu (isteğe bağlı):** `MEDRAG_ACCESS_CODE` tanımlıysa `/chat` ve `/api/*` istekleri `X-Access-Code`
  başlığı ister; yoksa `401 {"error": "access_code_required"}`. Sayfalar, statik dosyalar, `/health` ve
  `/api/meta/info` açıktır. `common.js` kodu bir kez sorar, tarayıcıda saklar ve her isteğe ekler.
- **Ses:** `POST /api/speech/transcribe` (multipart, alan adı `file`) → `{"text": str}`; model `qwen3-asr-1.7b`.
- **Görsel:** `POST /api/vision/lab-report` ve `POST /api/vision/medicine` (multipart, alan adı `file`).
- **`common.js` ek yardımcılar:** `toast(message)`, `uploadFile(url, file, fields)`.

## Evren API modelleri (GET /v1/models, 16.10.2026)

| Görev | Model |
|---|---|
| Embedding | `qwen3-embedding-8b` |
| Rerank | `qwen3-reranker-8b` (`POST /v1/rerank`) |
| Sohbet | `auto` (qwen3-vl-30b-a3b'ye yönlenir), `deepseek-v4-flash`, `deepseek-v4.1-flash`, `glm-5.3`, `qwen3.8-flash-next`, `mimo-v2.6-pro`, `gemma-4-31b` |
| Görsel sohbet | `qwen3-vl-30b` |
| OCR | `deepseek-ocr-2`, `dots-ocr` |
| Ses tanıma | `qwen3-asr-1.7b` |
| Güvenlik sınıflandırıcı | `qwen3-guard-4b` |

## Test düzeni

- Her iş akışı birim testleriyle gelir (LLM, embedding ve ağ sahte servislerle).
- API'ye dokunan doğrulamalar GitHub Actions workflow'larında gerçek API ile çalışır (bu geliştirme ortamı
  Evren API'ye erişemez): arama değerlendirmesi, güvenlik senaryoları, ekran görüntüleri.
- Birleştirme sonrası: `pytest`, `ruff`, ardından gerçek API workflow'ları.

## Eşzamanlılık

Evren API H200 üzerinde çalıştığı için istekler yüksek eşzamanlılıkla gönderilir (embedding ve LLM için
16 paralel istek varsayılan). Dış veri kaynaklarında (Vikipedi, Europe PMC, openFDA, CDC) yüksek ama
kaynağın kullanım sınırlarına saygılı eşzamanlılık ve 429'da geri çekilme kullanılır.

## Kurallar

- Sadece bulunan kaynaklara dayan, bilmiyorsan söyle.
- Teşhis, reçete, doz yok.
- Acil belirtide 112'ye yönlendir.
- Her yanıtta kısa tıbbi uyarı.
- Testlerde LLM ve embedding sahte servislerle; gerçek API testleri Actions'ta.
- Anahtarlar asla repoya yazılmaz.

## Devir notu (yeni oturumda devam etmek için) — güncel: 17.10.2026

- Çalışma dalı: `ccr-fc8175dc-sqyb1k`. Faz 2 iş akışları **A–G tamamlandı ve bu dala birleştirildi**
  (420 test geçiyor, ruff temiz). Ajan dalları ve yedek yamalar silindi; ajanların ilerleme notları
  `docs/gelistirme-kayitlari/` altında. Genel durum ve karar günlüğü: `ILERLEME.md` ve `README.md` (bölüm 1 ve 17).
- Tüm LLM görevleri `deepseek-v4.1-flash` ile çalışır (`MEDRAG_LLM_MODEL`). **`qwen3-embedding-8b` ve
  `qwen3-reranker-8b` ile gerçek çağrılar masraf nedeniyle durduruldu**; reranker varsayılan kapalı.
- **Ertelenen işler (sırayla):**
  1. Yeni ~19.500 parça için embedding indeksi: önce `Veri çek` ile ham veriyi repoya al, sonra
     `python -m medrag.index embed --trust-legacy` (ilk geçişte; sonra artımlı).
  2. Arama ölçümü (`python -m medrag.eval run`); rerank açılacaksa havuzu 10–15, metni ~600 karaktere indir.
  3. Gerçek vektör aramayla güvenlik ve belirti senaryoları; `eval/safety_results.md` 40 senaryoyla yenilenmeli.
  4. Ses tanıma (`qwen3-asr-1.7b`) gerçek sesle denemesi: `Platform` workflow'u.
  5. Tahlil OCR'ı gerçek telefon fotoğraflarıyla ölçmek.
- **Tıbbi inceleme bekleyen konular:** tahlil referans aralıkları/kritik eşikler (`labs/reference.py`) ve belirti kuralları
  bir hekim tarafından gözden geçirilmeli. Sistem raporda yazan referans aralığını önceler; yoksa hekime yönlendirir.
- Gerçek API testleri yerelde de çalışır (anahtar `phone/.env` içinde, gitignore'da) ya da Actions'ta
  (`EVREN_API_KEY` Actions secret).
- Commit mesajları kısa, sade Türkçe; her güncelleme README'ye işlenir. Anahtarlar asla repoya yazılmaz.
