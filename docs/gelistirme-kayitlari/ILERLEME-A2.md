# A akışı, ikinci tur (17.10.2026)

- Çoklu sorgu `finish_reason=length` sorunu: `multiquery_model` varsayılanı `deepseek-v4.1-flash`; `multiquery_extra_params`
  ile düşünme kapatılır (`enable_thinking=false`), `multiquery_max_tokens=3000`. Boş cevapta `complete_detailed`
  max_tokens'ı ikiye katlar (tavan 8192); `length` ile kesilmiş cevapta yarım son satır atılır (`trim_truncated`);
  hâlâ boşsa `QueryExpander` [] döner ve arama yalnızca orijinal sorguyla sürer. LLM isteği artık
  `multiquery_timeout` zaman aşımı ve 2 denemeyle gider. Rerank LLM değil `/v1/rerank` kullanır, başka LLM
  yedeği yoktur; bu yüzden ek düzeltme gerekmedi. `retrieval-check` ve `gen` aynı ayarları kullanır.
- Test seti 150 -> 500: `eval gen --n 500 --keep eval/queries.jsonl` mevcut 150 soruyu (sırayla, değişmeden;
  yalnızca `source`/`lang` alanı eklendi) korur, yeni sorular başka dokümanlardan, kaynak kotası
  (mevcut + yeni toplamına göre) gözetilerek `deepseek-v4.1-flash` ile 16 eşzamanlılıkla üretildi, tekrarlar
  ayıklandı. Dağılım: wikipedia/tr 110, wikipedia/en 114, medlineplus/en 276 (europepmc/openfda yerelde yok).
  eval.yml `regenerate` artık `--keep` ile çalışır.
- Karşılaştırma altyapısı (vektör, vektör+rerank, çoklu sorgu+rerank, gecikme) kodda hazır ve sahte servislerle
  testli (`tests/test_retrieval_multiquery.py`); ölçüm ÇALIŞTIRILMADI (qwen3 embedding/reranker masrafı).
