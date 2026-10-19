# OCR ölçümü: bozulmuş (telefon fotoğrafı taklidi) görseller

48 tahlil raporu (4 düzen) ve 45 ilaç kutusu; her görsele hafif/orta/ağır düzeyde 1-4 bozulma (perspektif, gölge, parlama, buruşma, bulanıklık, düşük ışık, kırpma) + JPEG sıkıştırma uygulandı. Sentetik görsellerdir; gerçek fotoğraf doğruluğu bunun altında olabilir.

## Tahlil raporu

| Model | Düzey | Görsel | Değer doğru | Birim doğru | Kaçan satır | Uydurma satır | Ort. süre (sn) |
|---|---|---|---|---|---|---|---|
| ocr:deepseek-ocr-2 | hafif | 16 | 100% | 92% | 0 | 0 | 14.0 |
| ocr:deepseek-ocr-2 | orta | 16 | 100% | 93% | 0 | 0 | 13.0 |
| ocr:deepseek-ocr-2 | ağır | 16 | 41% | 39% | 94 | 4 | 9.3 |
| ocr:deepseek-ocr-2 | tümü | 48 | 80% | 74% | 94 | 4 | 12.1 |
| ocr:dots-ocr | hafif | 16 | 100% | 92% | 0 | 0 | 18.9 |
| ocr:dots-ocr | orta | 16 | 99% | 95% | 1 | 0 | 22.2 |
| ocr:dots-ocr | ağır | 16 | 49% | 46% | 75 | 12 | 14.6 |
| ocr:dots-ocr | tümü | 48 | 82% | 77% | 76 | 12 | 18.6 |
| chat:qwen3-vl-30b | hafif | 16 | 100% | 95% | 0 | 0 | 22.5 |
| chat:qwen3-vl-30b | orta | 16 | 98% | 95% | 3 | 0 | 35.9 |
| chat:qwen3-vl-30b | ağır | 16 | 54% | 52% | 59 | 33 | 27.2 |
| chat:qwen3-vl-30b | tümü | 48 | 84% | 80% | 62 | 33 | 28.5 |
| chat:gemma-4-31b | hafif | 16 | 100% | 100% | 0 | 0 | 15.6 |
| chat:gemma-4-31b | orta | 16 | 100% | 99% | 0 | 0 | 13.7 |
| chat:gemma-4-31b | ağır | 16 | 52% | 52% | 74 | 3 | 18.9 |
| chat:gemma-4-31b | tümü | 48 | 84% | 83% | 74 | 3 | 16.1 |

## İlaç kutusu

| Model | Düzey | Görsel | Marka | Etken madde | Güç | Ort. süre (sn) |
|---|---|---|---|---|---|---|
| qwen3-vl-30b | hafif | 15 | 100% | 60% | 100% | 0.7 |
| qwen3-vl-30b | orta | 15 | 100% | 93% | 80% | 0.8 |
| qwen3-vl-30b | ağır | 15 | 87% | 60% | 87% | 0.7 |
| qwen3-vl-30b | tümü | 45 | 96% | 71% | 89% | 0.7 |
| gemma-4-31b | hafif | 15 | 100% | 100% | 100% | 2.9 |
| gemma-4-31b | orta | 15 | 100% | 100% | 80% | 2.9 |
| gemma-4-31b | ağır | 15 | 93% | 80% | 87% | 3.2 |
| gemma-4-31b | tümü | 45 | 98% | 93% | 89% | 3.0 |

İstek hatası olan görsel sayısı (toplam): 3. Ayrıntı: `scratch/ocr/results.json` (repoya alınmaz).

## Ağır düzey: yeniden ölçüm (API hız sınırı hataları olmadan, 2 işçi)

İlk koşuda ağır düzeyin son görselleri API 429 hatalarından etkilenmiş olabilirdi; bu yüzden yalnızca ağır düzey tekrar koşuldu. Sonuç ilk koşuyla aynı seviyede kaldı: ağır bozulmada düşüş gerçektir (hız sınırı kaynaklı değil). Satırlar `hafif`/`orta` için 0 görsel gösterir, çünkü bu koşuda yalnız ağır düzey vardı.

## Tahlil raporu

| Model | Düzey | Görsel | Değer doğru | Birim doğru | Kaçan satır | Uydurma satır | Ort. süre (sn) |
|---|---|---|---|---|---|---|---|
| ocr:deepseek-ocr-2 | hafif | 0 | - | - | 0 | 0 | 0.0 |
| ocr:deepseek-ocr-2 | orta | 0 | - | - | 0 | 0 | 0.0 |
| ocr:deepseek-ocr-2 | ağır | 16 | 41% | 39% | 94 | 4 | 21.8 |
| ocr:deepseek-ocr-2 | tümü | 16 | 41% | 39% | 94 | 4 | 21.8 |
| ocr:dots-ocr | hafif | 0 | - | - | 0 | 0 | 0.0 |
| ocr:dots-ocr | orta | 0 | - | - | 0 | 0 | 0.0 |
| ocr:dots-ocr | ağır | 16 | 48% | 46% | 77 | 11 | 15.0 |
| ocr:dots-ocr | tümü | 16 | 48% | 46% | 77 | 11 | 15.0 |
| chat:qwen3-vl-30b | hafif | 0 | - | - | 0 | 0 | 0.0 |
| chat:qwen3-vl-30b | orta | 0 | - | - | 0 | 0 | 0.0 |
| chat:qwen3-vl-30b | ağır | 16 | 58% | 56% | 54 | 31 | 15.1 |
| chat:qwen3-vl-30b | tümü | 16 | 58% | 56% | 54 | 31 | 15.1 |
| chat:gemma-4-31b | hafif | 0 | - | - | 0 | 0 | 0.0 |
| chat:gemma-4-31b | orta | 0 | - | - | 0 | 0 | 0.0 |
| chat:gemma-4-31b | ağır | 16 | 50% | 50% | 79 | 2 | 22.9 |
| chat:gemma-4-31b | tümü | 16 | 50% | 50% | 79 | 2 | 22.9 |

## İlaç kutusu

| Model | Düzey | Görsel | Marka | Etken madde | Güç | Ort. süre (sn) |
|---|---|---|---|---|---|---|
| qwen3-vl-30b | hafif | 0 | - | - | - | 0.0 |
| qwen3-vl-30b | orta | 0 | - | - | - | 0.0 |
| qwen3-vl-30b | ağır | 15 | 93% | 73% | 93% | 0.7 |
| qwen3-vl-30b | tümü | 15 | 93% | 73% | 93% | 0.7 |
| gemma-4-31b | hafif | 0 | - | - | - | 0.0 |
| gemma-4-31b | orta | 0 | - | - | - | 0.0 |
| gemma-4-31b | ağır | 15 | 93% | 80% | 87% | 3.7 |
| gemma-4-31b | tümü | 15 | 93% | 80% | 87% | 3.7 |

İstek hatası olan görsel sayısı (toplam): 4. Ayrıntı: `scratch/ocr/results_*.json` (repoya alınmaz).
