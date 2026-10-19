# Reranker çalışması (queries_v2, belge düzeyinde hakem etiketli)

677 soru. Etiket: `deepseek-v4.1-flash` hakemi, vektör+BM25 adayları arasından 'soruyu doğrudan cevaplayan' parçaları işaretledi. `doc@k`: ilk k BELGEDE en az bir ilgili belge var; `chunk@k`: ilk k parçada hakemin işaretlediği bir parça var. Reranker: `BAAI/bge-reranker-v2-m3` (yerel). Aday havuzu vektör aramasının ilk P'si.

| yöntem | doc@1 | doc@3 | doc@5 | mrr | ndcg@5 | chunk@1 | chunk@5 |
|---|---|---|---|---|---|---|---|
| vektör | 0.744 | 0.882 | 0.907 | 0.817 | 0.783 | 0.662 | 0.883 |
| rerank havuz 8, 600 karakter | 0.771 | 0.886 | 0.907 | 0.833 | 0.800 | 0.713 | 0.885 |
| rerank havuz 10, 600 karakter | 0.770 | 0.892 | 0.910 | 0.833 | 0.804 | 0.712 | 0.889 |
| rerank havuz 15, 600 karakter | 0.770 | 0.889 | 0.905 | 0.830 | 0.790 | 0.709 | 0.877 |
| rerank havuz 20, 600 karakter | 0.768 | 0.886 | 0.905 | 0.828 | 0.785 | 0.706 | 0.882 |
| rerank havuz 40, 600 karakter | 0.758 | 0.883 | 0.913 | 0.825 | 0.774 | 0.697 | 0.882 |
| rerank havuz 8, 1000 karakter | 0.743 | 0.886 | 0.907 | 0.817 | 0.788 | 0.682 | 0.879 |
| rerank havuz 10, 1000 karakter | 0.740 | 0.885 | 0.905 | 0.814 | 0.788 | 0.679 | 0.876 |
| rerank havuz 15, 1000 karakter | 0.736 | 0.877 | 0.903 | 0.809 | 0.771 | 0.675 | 0.867 |
| rerank havuz 20, 1000 karakter | 0.731 | 0.874 | 0.903 | 0.806 | 0.762 | 0.671 | 0.864 |
| rerank havuz 40, 1000 karakter | 0.725 | 0.870 | 0.904 | 0.804 | 0.749 | 0.663 | 0.855 |
| rerank havuz 8, 1500 karakter | 0.736 | 0.888 | 0.905 | 0.813 | 0.784 | 0.669 | 0.879 |
| rerank havuz 10, 1500 karakter | 0.734 | 0.885 | 0.905 | 0.810 | 0.784 | 0.668 | 0.877 |
| rerank havuz 15, 1500 karakter | 0.727 | 0.877 | 0.900 | 0.804 | 0.764 | 0.659 | 0.864 |
| rerank havuz 20, 1500 karakter | 0.721 | 0.873 | 0.901 | 0.799 | 0.755 | 0.653 | 0.860 |
| rerank havuz 40, 1500 karakter | 0.709 | 0.869 | 0.903 | 0.793 | 0.738 | 0.641 | 0.854 |

## Dil/kaynak kırılımı (doc@1 / doc@5 / mrr)

| grup | soru | vektör | rerank havuz 15, 1000 karakter | rerank havuz 40, 1500 karakter |
|---|---|---|---|---|
| cdc/en | 90 | 0.77 / 0.93 / 0.84 | 0.82 / 0.94 / 0.88 | 0.80 / 0.96 / 0.87 |
| europepmc/en | 80 | 0.66 / 0.88 / 0.75 | 0.66 / 0.88 / 0.76 | 0.59 / 0.86 / 0.70 |
| medlineplus/en | 176 | 0.64 / 0.84 / 0.73 | 0.59 / 0.82 / 0.69 | 0.54 / 0.81 / 0.66 |
| openfda/en | 99 | 0.89 / 0.96 / 0.92 | 0.89 / 0.96 / 0.92 | 0.86 / 0.97 / 0.90 |
| wikipedia/en | 137 | 0.72 / 0.90 / 0.80 | 0.67 / 0.90 / 0.77 | 0.67 / 0.91 / 0.77 |
| wikipedia/tr | 95 | 0.87 / 0.99 / 0.92 | 0.92 / 0.99 / 0.95 | 0.94 / 0.99 / 0.96 |

## Gecikme (25 soru, tek tek, ısınmış model, 1000 karakter)

| cihaz | havuz | medyan ms | p95 ms |
|---|---|---|---|
| cuda | 8 | 89 | 102 |
| cuda | 15 | 160 | 184 |
| cuda | 40 | 428 | 482 |
| cpu | 8 | 7781 | 8965 |
| cpu | 15 | 13985 | 16908 |
| cpu | 40 | 39843 | 42688 |
