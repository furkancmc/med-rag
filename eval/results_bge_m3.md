# Yerel BGE-M3 arama ölçümü (RTX 4060 Laptop, fp16)

Komut: `python -m medrag.eval run --backend local --methods bm25,vector --workers 1`
Ham çıktı: `eval/results_bge_m3.json`. Embedding yerelde, API çağrısı yok.

500 soru, 33.573 parça (`data/raw` yeniden işlendi), indeks `data/index_bge_m3` (1024 boyut, int8).

| yöntem | recall@1 | recall@3 | recall@5 | recall@10 | mrr@10 | ort. gecikme (sn) | p95 gecikme (sn) |
|---|---|---|---|---|---|---|---|
| bm25 | 0.158 | 0.208 | 0.218 | 0.230 | 0.184 | 0.01 | 0.01 |
| vector (BGE-M3) | 0.534 | 0.696 | 0.780 | 0.864 | 0.636 | 0.04 | 0.04 |

Kaynak/dil kırılımı (recall@1 / recall@5 / mrr@10):

| grup | soru | bm25 | vector (BGE-M3) |
|---|---|---|---|
| medlineplus/en | 276 | 0.00 / 0.01 / 0.01 | 0.45 / 0.71 / 0.55 |
| wikipedia/en | 114 | 0.01 / 0.04 / 0.02 | 0.47 / 0.75 / 0.59 |
| wikipedia/tr | 110 | 0.70 / 0.93 / 0.80 | 0.82 / 0.97 / 0.89 |
