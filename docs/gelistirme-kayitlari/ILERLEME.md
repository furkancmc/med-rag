# Genel ilerleme özeti (17.10.2026)

Faz 2 iş akışlarının (A-G) tamamı ana dala birleşti. Ayrıntı: `ILERLEME-*.md` dosyaları ve `PLAN.md`.

- Model: `deepseek-v4.1-flash` (Evren API, OpenAI uyumlu). Anahtar `.env`'de, repoya girmez.
- Masraf kararı: `qwen3-embedding-8b` ve `qwen3-reranker-8b` çağrılmaz; sonradan varsayılan embedding
  yerel BGE-M3 oldu (bkz. README arama bölümü). `rerank_enabled` varsayılanı kapalı.
- Birleştirmeler: A b143fd5, B 684d7ce, C 62277d0, D 81ec7a1, E 650560e, F 86643d3, G 490cc07.
- Son durum: 420 test geçti, ruff temiz; Docker imajı derlendi, healthy, root değil.
- Anahtar yokken API 503 (`ConfigError`) döner; NIH ODS isteğe bağlı kaynak.

## 19.10.2026 (Faz 3)
- Yeni soru seti `eval/queries_v2.jsonl` (695 soru + 60 kapsam dışı, belge düzeyinde hakem etiketi); reranker ikinci ölçüm: `eval/results_v2_rerank.md`.
- Varsayılanlar: `rerank_pool=10`, `rerank_doc_chars=600`; reranker GPU'da fayda, CPU'da yavaş (kapalı).
- OCR: bozulmuş 48 rapor + 45 kutu ölçüldü (`eval/ocr_real_results.md`); README'de örnek görseller.
- Tıbbi: tahlil tablosu ve belirti kuralları web kaynaklarıyla karşılaştırıldı; bazı kurallar yukarı çekildi (`docs/tibbi-inceleme.md`).

## Bekleyenler
- Hekim/klinik biyokimya incelemesi (web doğrulaması onun yerine geçmez).
- Vektör aramayla uçtan uca güvenlik koşusu (C) ve kaynaklı D/E testleri; gerçek telefon fotoğrafıyla OCR.
