# medrag

Türkçe sağlık bilgi asistanı: açık tıbbi kaynaklar üzerinde RAG, kaynak gösteren cevaplar. Python 3.11, FastAPI.

## Komutlar (Windows, venv: `.venv`)
- Test: `.venv/Scripts/python -m pytest -q` (gerçek model/GPU testleri `MEDRAG_GPU_TEST=1` ister)
- Lint: `.venv/Scripts/ruff check .`
- Sunucu: `.venv/Scripts/python scripts/dev_server.py`

## Yapı
- `src/medrag/`: `ingest` (veri), `index` (BM25 + vektör), `retrieve.py`, `rerank*.py`, `chat` (servis, acil, doğrulama),
  `assess` (belirti), `labs` (tahlil), `vision.py`, `api` (routes + middleware), `web` (HTML/statik), `config.py`, `deps.py`
- `tests/` birim testleri (LLM, embedding, ağ sahte), `eval/` değerlendirme ve sonuç raporları (`queries_v2.jsonl`: belge düzeyinde etiketli soru seti)
- `scripts/agents/run_task.py`: Evren API modelleriyle toplu "ajan" görevi (JSONL, devam edilebilir, `.env`'den anahtar); `scripts/ocr_set.py`, `ocr_eval.py`, `rerank_study.py`: ölçüm betikleri
- `docs/gorevler/` eski iş akışı tarifleri, `docs/gelistirme-kayitlari/` ilerleme kayıtları: gerekmedikçe okuma

## Kurallar
- Ayarlar `MEDRAG_` önekli ortam değişkenleri (`config.py`); gizli anahtarlar `.env`'de, asla commit edilmez.
- Sözleşmeler: `Retriever.search(query, k)` imzası sabit; yeni uç nokta `api/routes/<ad>.py` içinde `router`; sayfa `web/<ad>.html`.
- Ürün kuralları: yalnızca kaynağa dayan, teşhis/reçete/doz yok, acil belirtide 112. Kural tabanlı güvenlik kararı LLM'i yalnızca yukarı çeker.
- Embedding varsayılanı yerel BGE-M3, rerank kapalı (GPU'da pool 10 / 600 karakter faydalı, CPU'da yavaş); ücretli 8b modelleri çağırma.
- Evren API: aynı anda çok istek 429 verir (`glm-5.3` özellikle); toplu işlerde `deepseek-v4.1-flash`, düşük eşzamanlılık. Testler için `PYTHONPATH=src` gerekebilir.
- Commit mesajları Türkçe, kısa; Claude eş-yazar/trailer satırı ekleme.
- Büyük dosyalar (`docs/teknik-detaylar.md` ~60 KB, `eval/safety_results.md`) için tamamını okuma; `grep` ile ilgili bölümü bul.
