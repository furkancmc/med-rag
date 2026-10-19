# Yol haritası

Açık tıbbi kaynaklar üzerinde RAG ile çalışan Türkçe sağlık bilgi asistanı. Embedding yerel BGE-M3 ile, cevap üretimi
Evren API (OpenAI uyumlu, sohbet: `deepseek-v4.1-flash`) ile yapılır.
Cevaplar yalnızca kaynaklara dayanır ve kaynak gösterir.

## Durum

**Faz 1 (temel sistem) tamamlandı:** iskelet, veri hattı (MedlinePlus, Vikipedi), indeks (BM25 + vektör),
arama, sohbet servisi (acil kontrol, atıf, doz filtresi), FastAPI + SSE, web arayüzü, değerlendirme, Docker.

**Faz 2 tamamlandı** (ayrıntı: `docs/gorevler/A-G.md`, kayıtlar: `docs/gelistirme-kayitlari/`):

| Akış | Kapsam |
|---|---|
| A Arama | reranker (ölçüldü, GPU'da küçük fayda), çoklu sorgu, 500 + 755 soruluk setler. Açık: çoklu sorgu ölçümü |
| B Veri | Europe PMC, openFDA, CDC, ~400 konulu Vikipedi, lisans/tarih alanları, embedding önbelleği, haftalık yenileme |
| C Güvenlik | çalışma anı cevap doğrulama, LLM acil sınıflandırıcı, yazıyla doz yakalama, 30+ güvenlik senaryosu |
| D Belirti | en fazla 5 soruluk değerlendirme, aciliyet seviyesi; kurallar kararı yalnızca yukarı çeker |
| E Tahlil | referans aralıkları, kural tabanlı sınıflandırma, fotoğraftan okuma (saklanmaz) |
| F Sunucu | hız/boyut sınırı, güvenlik başlıkları, erişim kodu, geri bildirim, metrik, Docker |
| G Arayüz | ortak tasarım sistemi, 4 sayfa, alt gezinme, tema, ses, PWA |
| H Belgeler | README ve değişiklik günlüğü her birleştirmede güncellenir |

**Faz 3 (19.10.2026) tamamlandı:** belge düzeyinde etiketli yeni soru seti (`eval/queries_v2.jsonl`), reranker ikinci ölçümü (varsayılan: havuz 10, 600 karakter; yalnız GPU'da önerilir), bozulmuş görsellerle OCR ölçümü ve README örnekleri, tahlil/belirti kurallarının web kaynaklarıyla doğrulanması (`docs/tibbi-inceleme.md`; hekim onayı değildir), git geçmişi temizliği.

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

## Devir notu (yeni oturumda devam etmek için) — güncel: 20.10.2026

- Çalışma dalı: `ccr-fc8175dc-sqyb1k`. Faz 1-3 tamamlandı (460 test geçiyor, ruff temiz). Genel durum ve karar günlüğü:
  `README.md` (bölüm 1 ve 17); ajan ilerleme notları `docs/gelistirme-kayitlari/` altında.
- Tüm LLM görevleri `deepseek-v4.1-flash` ile çalışır (`MEDRAG_LLM_MODEL`); embedding yerel BGE-M3 (33.573 parça indekslendi).
  Reranker varsayılan kapalı (GPU'da havuz 10 / 600 karakter faydalı, CPU'da yavaş).
- **Bekleyen işler (sırayla):**
  1. Hekim ya da klinik biyokimya uzmanı incelemesi: `labs/reference.py` ve `assess/rules.py`. Web kaynaklı doğrulama (`docs/tibbi-inceleme.md`) bunun yerine geçmez.
  2. Gerçek vektör aramayla güvenlik ve belirti senaryoları; `eval/safety_results.md` ve `eval/assess_results.md` son kural değişikliklerinden sonra yenilenmedi.
  3. OCR'ı gerçek telefon fotoğraflarıyla ölçmek; ağır bozulmada doğruluk %41-58 (perspektif düzeltme/ön işleme denenebilir).
  4. Ses tanıma (`qwen3-asr-1.7b`) gerçek sesle denemesi: `Platform` workflow'u.
  5. Çoklu sorgu ölçümü (kod hazır, kapalı); haftalık `data/raw` commit'leri `.git`'i büyütüyor (Git LFS ya da release asset düşünülebilir).
- Gerçek API testleri yerelde (anahtar `.env`'de, gitignore'da) ya da Actions'ta (`EVREN_API_KEY` secret) çalışır. Evren API aynı anda çok istekte 429 verir.
- Commit mesajları kısa, sade Türkçe; her güncelleme README'ye işlenir. Anahtarlar asla repoya yazılmaz.
