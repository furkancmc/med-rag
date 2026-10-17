# İlerleme B (Veri)
Yapıldı: önceki yama uygulandı (net, rawstore, report, textutil, europepmc, openfda, drugs, download refactor).
Not: ODS (ods.od.nih.gov) bu makineden Cloudflare 403 veriyor; nihods enjekte edilebilir get ile yazılır.
Sırada: nihods, curated(~400), parse/build/chunk (metadata, dedupe, wiki temizlik, yeni kaynaklar), CLI, store int8+artımlı,
index CLI, config, workflowlar, testler, gerçek doğrulama, tek commit.
Yapıldı: nihods, curated_extra, parse/chunk/build, ingest CLI fetch, store int8+artımlı, index CLI, config. Sırada: testler, workflow, gerçek doğrulama.
Yapıldı: testler (113 geçti), ruff temiz, workflowlar. Sırada: gerçek doğrulama (scratch data_dir), commit.
Gerçek veri çekme tamam (scratch): medlineplus 1017, wiki tr 443/en 547, europepmc 1558 makale, openfda 233 ilaç, nihods 403 (Cloudflare). build=32753 chunk. Embedding gerçek doğrulaması ERTELENDİ (kullanıcı kararı: qwen3-embedding/rerank çağrısı yok); kod+sahte servis testleriyle bitti.

## CDC kaynagi (17.10.2026)
Yapildi: ingest/cdc.py (CDC Content Services syndication API; www.cdc.gov dogrudan 403 verir), parse_cdc_page, build, fetch --sources cdc, workflow metni, tests/test_data_cdc.py (7 test). Gercek cekim (scratchpad): 97 konu sorgusundan 67 konu, 128 sayfa. Eksik konular CDC kutuphanesinde yok; onek disi ad eslesmesi yedegi var.
Kontrol edildi, zaten vardi: Europe PMC, openFDA (doz yok), Vikipedi ~550 konu, parca meta verisi, int8 artimli embedding deposu, haftalik fetch-data.yml, 429 geri cekilme (net.py). Embedding cagrisi yapilmadi.
