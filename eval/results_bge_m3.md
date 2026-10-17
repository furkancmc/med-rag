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

## Eski Qwen3-Embedding-8B sonucuyla karşılaştırma (AYNI KOŞUL DEĞİL)

`eval/results.md` (Qwen3-8B, API): 150 soru, eski korpus. Bu ölçüm: 500 soru, yeniden üretilen 33.573
parçalık korpus (eski ölçümün korpusu farklıydı ve muhtemelen daha küçüktü; daha büyük korpus aday
sayısını artırıp aynı modeli bile düşürür). Ayrıca soru kümesi farklı ve kaynak dağılımı farklı
(burada soruların %78'i İngilizce kaynağı hedefliyor; Türkçe soru -> İngilizce belge çapraz dil zorluğu).
Kıyas yalnızca yön gösterir.

| | Qwen3-8B (eski, 150 soru) | BGE-M3 (yeni, 500 soru) |
|---|---|---|
| vector recall@1 | 0.647 | 0.534 |
| vector recall@5 | 0.847 | 0.780 |
| vector recall@10 | 0.940 | 0.864 |
| vector MRR@10 | 0.730 | 0.636 |
| bm25 recall@5 | 0.460 | 0.218 |

Yorum: aynı koşulda olmadığı için "BGE-M3 daha kötü" denemez; ancak korpus büyüdüğü halde fark ~6-8 puan
mertebesinde ve Türkçe-Türkçe grupta (wikipedia/tr) recall@5 0.97. BM25'in düşmesi korpusun İngilizce
ağırlıklı soru kümesinden kaynaklanır. Adil karşılaştırma için Qwen3-8B ile aynı 33.573 parça ve 500 soruyla
yeniden ölçüm gerekir (API embedding'i ~33,5 bin parça; bu görevde API kullanılmadı). 500 sorudan 2'sinin
hedef parça kimliği yeni korpusta yok (bulunamadı sayılır).

## Reranker (BAAI/bge-reranker-v2-m3, yerel) kısa deneme

100 soru (eşit aralıklı örnek), havuz 20, tamamı yerel. Varsayılan KAPALI kalır.

| yöntem | recall@1 | recall@5 | recall@10 | mrr@10 | ort. gecikme |
|---|---|---|---|---|---|
| vector | 0.510 | 0.770 | 0.840 | 0.617 | 0.05 sn |
| vector + bge-reranker (havuz 20) | 0.400 | 0.720 | 0.810 | 0.518 | 0.29 sn |

Türkçe hedefli sorularda reranker recall@1'i 0.82 -> 1.00 çıkardı, İngilizce hedeflilerde düşürdü
(0.45 -> 0.23 gibi). Bu ayarlarla kazanç yok; ayrıntılı ayar (doküman uzunluğu, havuz) denenmedi.

## Hız (embedding, RTX 4060 Laptop 8 GB)

- 200 parça: 120 parça/sn; tüm korpus: 33.573 parça, 356 sn (94 parça/sn, ~6 dk), VRAM tepe 1,4 GiB (grup 32).
- İlk çalıştırmada model indirme (~2,3 GB) ek ~6 dk sürdü.
