# Genel ilerleme özeti (17.10.2026)

Faz 2 iş akışlarının (A-G) tamamı ana dala birleşti. Ayrıntı: `ILERLEME-*.md` dosyaları ve `PLAN.md`.

- Model: `deepseek-v4.1-flash` (Evren API, OpenAI uyumlu). Anahtar `.env`'de, repoya girmez.
- Masraf kararı: `qwen3-embedding-8b` ve `qwen3-reranker-8b` çağrılmaz; sonradan varsayılan embedding
  yerel BGE-M3 oldu (bkz. README arama bölümü). `rerank_enabled` varsayılanı kapalı.
- Birleştirmeler: A b143fd5, B 684d7ce, C 62277d0, D 81ec7a1, E 650560e, F 86643d3, G 490cc07.
- Son durum: 420 test geçti, ruff temiz; Docker imajı derlendi, healthy, root değil.
- Anahtar yokken API 503 (`ConfigError`) döner; NIH ODS isteğe bağlı kaynak.

## Bekleyenler
- Tıbbi inceleme onayı: labs referans aralıkları, D'nin "çocukta hafif ateş" beklenen aralığı (`docs/tibbi-inceleme.md`).
- Kaynaklı uçtan uca testler (D/E) ve vektör aramayla güvenlik koşusu (C).
