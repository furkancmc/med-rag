# İlerleme kaydı (checkpoint)

Oturum kesilirse buradan devam edilir. Her adım bitince bu dosya güncellenir.

## Çalışma kuralları (kullanıcı kararı, 17.10.2026)
- Model: `deepseek-v4.1-flash` (Evren API, `https://evren-llmapi.ssyz.org.tr/v1`, OpenAI uyumlu).
- (GÜNCEL, 17.10.2026) Ajanlar PARALEL çalışır, aynı anda 3-4 tane; her biri ayrı worktree'de (`.claude/worktrees`, phone içinde). Batch/eşzamanlılık yüksek.
- Sadece `phone` klasörü içinde çalışılır, dışarı çıkılmaz.
- Her adımda commit atılmaz; checkpoint bu dosyaya ve (gerekirse) `checkpoints/` yamalarına yazılır.
- Her adımda durum bildirilir.
- Anahtar asla repoya yazılmaz (`.env` gitignore'da).

## Durum
- [x] Repo ve görev tarifleri okundu (PLAN.md, docs/gorevler/A-G.md)
- [x] API anahtarı `phone/.env` içinde (gitignore'da), `MEDRAG_LLM_MODEL=deepseek-v4.1-flash`
- [x] Bağlantı testi başarılı (1.8 sn, model deepseek/deepseek-v4.1-flash, düşünme tokenları 'reasoning' alanında, kalan kredi ~1062)
- [~] A Arama: yama (checkpoints/agent-aefdbaf...) uygulandı, 124 test + ruff temiz; gerçek API doğrulaması sırada
  (A ana ağaç yedeği: checkpoints/ana-agac-A.patch)
- [ ] B Veri
- [ ] C Güvenlik
- [x] D Belirti: dal worktree-agent-a97069d27386b29fc, commit 81ec7a1, 113 test + ruff temiz; birleştirme bekliyor
- [x] E Tahlil: dal worktree-agent-a6c906b7fe71944a4, commit 650560e, 195 test + ruff temiz; birleştirme bekliyor
- [ ] F Sunucu
- [~] G Arayüz: ajan başlatıldı (a47ffd...), önceki CSS yaması ile başlıyor

## Notlar
- `config.py` `llm_model` varsayılanı `auto`; `deepseek-v4.1-flash` için `MEDRAG_LLM_MODEL` ile geçilebilir.

## Dalga 1 (paralel): B, C, D, E
- A: ana ağaçta, uncommitted (yama uygulandı, 124 test geçti, gerçek API retrieval-check çalıştı: rerank sırası 2.08 -> ~1.3, havuz 40 ~1.2 sn).
  Sorun: multiquery LLM `finish_reason=length` (deepseek düşünme tokenı yedi) -> multiquery için max_tokens yükseltilecek / model `auto` yerine düşünmesiz ayar.
- Ajanlar bitince bu dosyaya ve `checkpoints/` altına sonuç yazılır; F ve G sonraki dalga.

## KARAR (17.10.2026): 8b embedding/reranker kapalı
- Masraf nedeniyle `qwen3-embedding-8b` ve `qwen3-reranker-8b` ÇAĞRILMAZ. Tüm LLM işleri `deepseek-v4.1-flash`.
- `rerank_enabled` varsayılanı False. Embedding/rerank gerektiren işler (indeks yeniden kurma, arama ölçümü, retrieval-check) ERTELENDİ, sonra devam.
- A ölçümü durduruldu (eval/results.md güncellenmedi).
