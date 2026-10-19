# Çoklu sorgu çalışması (queries_v2)

200 soru (eşit aralıklı örnek). Genişletici: `deepseek-v4.1-flash`; RRF birleştirme. Metrikler `rerank_study.py` ile aynı.

| yöntem | doc@1 | doc@3 | doc@5 | mrr | ndcg@5 |
|---|---|---|---|---|---|
| vektör | 0.715 | 0.860 | 0.890 | 0.794 | 0.761 |
| çoklu sorgu | 0.810 | 0.910 | 0.940 | 0.864 | 0.840 |

## Kaynak/dil kırılımı (doc@1 / doc@5)

| grup | soru | vektör | çoklu sorgu |
|---|---|---|---|
| cdc/en | 4 | 0.50 / 1.00 | 1.00 / 1.00 |
| europepmc/en | 26 | 0.65 / 0.92 | 0.88 / 0.96 |
| medlineplus/en | 59 | 0.59 / 0.80 | 0.68 / 0.92 |
| openfda/en | 34 | 0.94 / 0.97 | 0.94 / 0.97 |
| wikipedia/en | 45 | 0.69 / 0.87 | 0.80 / 0.91 |
| wikipedia/tr | 32 | 0.81 / 0.97 | 0.84 / 0.97 |
