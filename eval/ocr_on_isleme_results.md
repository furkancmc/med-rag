# OCR ölçümü: bozulmuş (telefon fotoğrafı taklidi) görseller

48 tahlil raporu (4 düzen) ve 45 ilaç kutusu; her görsele hafif/orta/ağır düzeyde 1-4 bozulma (perspektif, gölge, parlama, buruşma, bulanıklık, düşük ışık, kırpma) + JPEG sıkıştırma uygulandı. Sentetik görsellerdir; gerçek fotoğraf doğruluğu bunun altında olabilir.

## Tahlil raporu

| Model | Düzey | Görsel | Değer doğru | Birim doğru | Kaçan satır | Uydurma satır | Ort. süre (sn) |
|---|---|---|---|---|---|---|---|
| ocr:dots-ocr | hafif | 16 | 100% | 92% | 0 | 0 | 10.6 |
| ocr:dots-ocr | orta | 16 | 99% | 95% | 1 | 0 | 9.7 |
| ocr:dots-ocr | ağır | 16 | 49% | 47% | 74 | 12 | 9.8 |
| ocr:dots-ocr | tümü | 48 | 82% | 77% | 75 | 12 | 10.0 |
| chat:qwen3-vl-30b | hafif | 16 | 100% | 97% | 0 | 0 | 16.5 |
| chat:qwen3-vl-30b | orta | 16 | 98% | 95% | 3 | 0 | 11.7 |
| chat:qwen3-vl-30b | ağır | 16 | 52% | 51% | 65 | 24 | 18.4 |
| chat:qwen3-vl-30b | tümü | 48 | 83% | 81% | 68 | 24 | 15.5 |
| chat:gemma-4-31b | hafif | 16 | 100% | 100% | 0 | 0 | 17.0 |
| chat:gemma-4-31b | orta | 16 | 100% | 98% | 0 | 0 | 14.2 |
| chat:gemma-4-31b | ağır | 16 | 43% | 42% | 90 | 3 | 14.9 |
| chat:gemma-4-31b | tümü | 48 | 81% | 80% | 90 | 3 | 15.4 |

## İlaç kutusu

| Model | Düzey | Görsel | Marka | Etken madde | Güç | Ort. süre (sn) |
|---|---|---|---|---|---|---|
| qwen3-vl-30b | hafif | 15 | 100% | 60% | 100% | 0.8 |
| qwen3-vl-30b | orta | 15 | 100% | 93% | 80% | 0.9 |
| qwen3-vl-30b | ağır | 15 | 93% | 73% | 93% | 0.9 |
| qwen3-vl-30b | tümü | 45 | 98% | 76% | 91% | 0.9 |

İstek hatası olan görsel sayısı (toplam): 4. Ayrıntı: `scratch/ocr/results_*.json` (repoya alınmaz).
