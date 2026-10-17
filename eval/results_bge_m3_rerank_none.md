500 soru

| yöntem | recall@1 | recall@3 | recall@5 | recall@10 | mrr@10 |
|---|---|---|---|---|---|
| vector + rerank (havuz 20) | 0.456 | 0.596 | 0.706 | 0.826 | 0.555 |
| vector + rerank (havuz 40) | 0.448 | 0.570 | 0.668 | 0.776 | 0.536 |

Notlar:
- Kalite 4 paralel iş parçacığıyla ölçüldü. Gecikme ayrıca 0 soruda sırayla, her sorguda embedding/genişletme önbelleği boşaltılarak (soğuk) ölçüldü; chat'te göreceğin ek süre budur.
- Rerank: model `BAAI/bge-reranker-v2-m3`, şablon `none` (`-none`/`-qwen3` sonekli yöntemler şablonu zorlar), doküman başına en çok 1500 karakter, zaman aşımı 60 sn.
- Çoklu sorgu: model `deepseek-v4.1-flash`, orijinal sorgu ağırlığı 1.

Kaynak/dil kırılımı (recall@1 / recall@5 / mrr@10):

| grup | soru | vector + rerank (havuz 20) | vector + rerank (havuz 40) |
|---|---|---|---|
| medlineplus/en | 276 | 0.30 / 0.59 / 0.42 | 0.29 / 0.55 / 0.39 |
| wikipedia/en | 114 | 0.34 / 0.69 / 0.48 | 0.33 / 0.64 / 0.47 |
| wikipedia/tr | 110 | 0.96 / 1.00 / 0.98 | 0.96 / 0.99 / 0.98 |
