# BGE: Yerel embedding (BAAI/bge-m3)

- Yeni: `index/local_embed.py` (`LocalEmbedder`: fp16/GPU, CPU yedeği, uzunluğa göre sıralı grup, OOM'da grup yarıya iner),
  `rerank_local.py` (`LocalReranker`, bge-reranker-v2-m3, varsayılan kapalı), `config.active_embedding`, `store.check_meta`.
- Ayarlar: `MEDRAG_EMBED_BACKEND=api|local` (varsayılan api), `MEDRAG_LOCAL_EMBED_*`, `MEDRAG_RERANK_BACKEND`.
  İndeks klasörü ayrı: `data/index_bge_m3`; `data/index_qwen3` dokunulmadı. `load_vectors` model/boyutu meta'dan denetler.
- Komutlar: `python -m medrag.index embed --backend local [--bench N]`, `python -m medrag.eval run --backend local`.
- Sunucu: `load_retriever` arka uca göre kurar; yerel model ilk aramada yüklenir; yerel arka uçta API anahtarı şart değil.
- Bağımlılık: `pip install -e ".[local]"` (torch cu124 ayrıca kurulur). Test makinesi: torch 2.6.0+cu124, transformers 5.20.
- Ölçüm: 33.573 parça, 356 sn (94 parça/sn), VRAM tepe 1,4 GiB; 500 soru vektör recall@1/5/10 = 0,53/0,78/0,86, MRR 0,64;
  bm25 recall@5 0,22. Eski Qwen3 sonucuyla aynı koşul DEĞİL (bkz. `eval/results_bge_m3.md`).
- Reranker kısa deneme (100 soru): genel kalite düştü; kapalı kaldı.
- Testler: `tests/test_local_embed.py` (sahte embedder; gerçek GPU testi `-m gpu` + `MEDRAG_GPU_TEST=1`).
- Yapılmayanlar: aynı koşulda Qwen3 kıyası (API gerekir), Docker imajı/GPU imajı denemesi, `/api/meta/info` dışında arayüzde model adı değişikliği.
