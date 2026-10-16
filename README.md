# medrag

Açık tıbbi kaynaklar üzerinde çalışan, Türkçe sohbet eden bir RAG asistanı.
Soruya önce ilgili kaynak parçalarını bulur, sonra cevabı yalnızca bu kaynaklara dayanarak
yazar ve [1] [2] gibi atıflarla kaynakları gösterir.

**Teşhis koymaz, ilaç ya da doz önermez, doktorun yerini tutmaz.** Acil belirtilerde (göğüs ağrısı,
felç belirtisi, nefes alamama, kendine zarar vb.) cevaptan önce 112'ye yönlendirir. Her cevabın sonuna
tıbbi uyarı eklenir.

## Nasıl çalışır

```
soru ──► acil durum kontrolü ──► vektör arama ──► prompt ──► Evren LLM ──► akan cevap + kaynaklar
          (kural tabanlı)         (Qwen3)          kaynak     (SSE)
                                                   atıfı
```

- **Veri:** MedlinePlus (İngilizce, kamu malı, 1.017 konu) ve elle seçilmiş Vikipedi makaleleri
  (Türkçe ve İngilizce, CC BY-SA). Kaynak ve lisans her parçada saklanır. Kendi `.txt`/`.md`
  dosyalarını `data/local/` altına koyabilirsin.
- **Arama:** `qwen3-embedding-8b` vektörleri. Türkçe soru İngilizce kaynağı da bulabilir.
  150 test sorusunda doğru doküman ilk 5'te %85, ilk 10'da %94 oranında bulundu (`eval/results.md`).
  BM25 tek başına %46, BM25 ile birleştirme (hybrid) vektörden daha kötü çıktığı için kullanılmıyor;
  kodu (`Retriever.search(mode="hybrid")`) duruyor. Test soruları LLM ile yazıldığı için gerçek kullanıcı
  sorularından farklı olabilir.
- **Cevap:** Evren API'deki sohbet modeli (`model: auto`).

## Kurulum ve çalıştırma

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export EVREN_API_KEY=...            # anahtarı asla repoya yazma
python -m medrag.api                # http://localhost:8000
```

Telefonda açmak için aynı ağdaki bilgisayarın adresini kullan (`http://<bilgisayar-ip>:8000`).
Docker ile:

```bash
docker build -t medrag .
docker run -e EVREN_API_KEY=... -p 8000:8000 medrag
```

Sunucunun `evren-llmapi.ssyz.org.tr` adresine erişebilmesi gerekir.

## Veriyi yenileme

Her adım bir komuttur; GitHub Actions'ta da hazır workflow'ları var (Actions sekmesinden elle çalışır).

```bash
python -m medrag.ingest medlineplus          # MedlinePlus -> data/raw/medlineplus/topics.jsonl
python -m medrag.ingest wikipedia --lang tr --curated   # seçili konular (src/medrag/ingest/curated.py)
python -m medrag.ingest build                # -> data/chunks.jsonl
python -m medrag.index embed --index-dir data/index_qwen3   # EVREN_API_KEY gerekir
```

| Workflow | Ne yapar |
|---|---|
| `Veri çek` | MedlinePlus ve Vikipedi'yi indirip `data/raw` altına commit'ler |
| `İndeks oluştur (API)` | Qwen3 ile embedding hesaplar, `data/index_qwen3` altına commit'ler |
| `Arama değerlendirmesi` | Evren API ile test soruları üretir, bm25 / vector / hybrid'i karşılaştırır (`eval/results.md`) |
| `Güvenlik ve uçtan uca test` | `/chat` akışını dener, güvenlik ve kaynağa sadakat senaryolarını çalıştırır (`eval/safety_results.md`) |

`EVREN_API_KEY` GitHub'da repo ayarlarındaki Actions secret'ı olarak tanımlıdır.

## Geliştirme

```bash
pytest          # API'ye dokunmayan testler; LLM ve embedding sahte (mock) servislerle test edilir
ruff check .
```

Dizin yapısı: `src/medrag/ingest` (veri hattı), `index` (BM25, embedding, vektör deposu),
`retrieve.py` (hybrid arama), `chat` (acil durum, prompt, servis), `api` (FastAPI), `web` (sohbet sayfası),
`eval` (arama ve güvenlik değerlendirmesi).

## Sınırlar

- Bilgi tabanı küçük (yaklaşık 1.200 makale/konu). Kapsam dışı bir konuda "yeterli bilgi yok" demesi beklenir.
- Acil durum kontrolü anahtar kelime kurallarına dayanır; her cümleyi yakalamaz.
- Kullanıcı başına hız sınırı yok. Herkese açık bir sunucuya koymadan önce eklenmeli.
- Kaynak dosyaları CC BY-SA içerir; yayınlarken atıf ve lisans korunmalıdır.
