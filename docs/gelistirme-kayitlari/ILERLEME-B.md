# İlerleme B (Veri)
Yapıldı: önceki yama uygulandı (net, rawstore, report, textutil, europepmc, openfda, drugs, download refactor).
Not: ODS (ods.od.nih.gov) bu makineden Cloudflare 403 veriyor; nihods enjekte edilebilir get ile yazılır.
Sırada: nihods, curated(~400), parse/build/chunk (metadata, dedupe, wiki temizlik, yeni kaynaklar), CLI, store int8+artımlı,
index CLI, config, workflowlar, testler, gerçek doğrulama, tek commit.
Yapıldı: nihods, curated_extra, parse/chunk/build, ingest CLI fetch, store int8+artımlı, index CLI, config. Sırada: testler, workflow, gerçek doğrulama.
Yapıldı: testler (113 geçti), ruff temiz, workflowlar. Sırada: gerçek doğrulama (scratch data_dir), commit.
Gerçek veri çekme tamam (scratch): medlineplus 1017, wiki tr 443/en 547, europepmc 1558 makale, openfda 233 ilaç, nihods 403 (Cloudflare). build=32753 chunk. Embedding gerçek doğrulaması ERTELENDİ (kullanıcı kararı: qwen3-embedding/rerank çağrısı yok); kod+sahte servis testleriyle bitti.
