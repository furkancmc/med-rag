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
- [x] A Arama: ana dala commit edildi (b143fd5); rerank varsayılan kapalı; ölçüm ertelendi (8b yasağı)
  (A ana ağaç yedeği: checkpoints/ana-agac-A.patch)
- [x] B Veri: birleştirildi (684d7ce); veri scratchpad'da, repoya girmedi; embedding indeks kurulumu ERTELENDİ
- [x] C Güvenlik: birleştirildi (62277d0), 40 senaryo 40/40 (BM25)
- [x] D Belirti: birleştirildi (81ec7a1)
- [x] E Tahlil: birleştirildi (650560e)
- [x] F Sunucu: birleştirildi (86643d3); hız sınırı, erişim kodu, feedback, meta, speech, Docker; platform workflow Actions'ta doğrulanacak
- [x] G Arayüz: birleştirildi (490cc07); D/E sayfaları ortak başlığa, manifest ve tema düğmesine uyduruldu; Edge ile 390 px QA temiz (4 sayfa, açık/koyu)

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

## Git durumu
- Ana dal: A, D, E, C birleştirildi; 354 test geçti, ruff temiz. B ve G sürüyor, F başlıyor.
- Birleştirme sonrası her turda: pytest + ruff + git status + commit.

## Bekleyenler / geri dönülecekler
- Tüm iş akışları (A-G) birleşti. Test: 414 geçti, ruff temiz.
- ERTELENEN (8b embedding/rerank masrafı): yeni ~19.500 parça için indeks kurulumu (`index embed`, artımlı; ilk geçişte `--trust-legacy`), arama ve rerank ölçümü (A), retrieval-check, kaynaklı uçtan uca testler (D/E), vektör aramayla güvenlik koşusu (C).
- Rerank maliyeti: soru başına ~40 doküman x ~450 token; açarken pool 10-15 ve metin ~600 karakter öner.
- Tıbbi inceleme: labs referans aralıkları ve D'nin 'çocukta hafif ateş' beklenen aralığı (home..today) kullanıcı onayı bekliyor.
- Anahtar yoksa deps.get_retriever RuntimeError ile 500 veriyor; düzgün hata mesajı eklenebilir.
- Test: 407 geçti, 1 atlandı, ruff temiz (F birleşiminden sonra).

## 17.10.2026 son tur
- Düzeltildi: anahtar yokken 503 (`ConfigError`), NIH ODS isteğe bağlı kaynak, tahlilde rapor aralığı önceliği + hekim notu,
  5 yaş altı ateş kuralı, varsayılan model `deepseek-v4.1-flash`, worktree/yama temizliği.
- Docker imajı derlendi ve duman testinden geçti (healthy, root değil).
- README baştan yazıldı (mimari ve arama grafiği SVG, 12 arayüz görüntüsü `docs/screens/ui/`, model/teknoloji/kaynak/karar tabloları).
- PLAN.md devir notu güncellendi. Test: 420 geçti, ruff temiz.
