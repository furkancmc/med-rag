# Tıbbi inceleme, görsel ve uçtan uca doğrulama notu (17.10.2026)

- `docs/tibbi-inceleme.md`: referans aralıkları ve belirti kuralları için yapay zekâ + kaynak çapraz kontrolü (hekim onayı değildir).
- labs: kritik eşikler temkinli çekildi, ALT/AST/albümin/BUN/üre/CRP kritik eşikleri eklendi.
- assess: zehirlenme, kanlı kusma, ani nefes darlığı, safralı kusma, hipoglisemi, kanlı ishal, apandisit, yanık
  ve gebelikte preeklampsi için taban kurallar; bilinç bulanıklığı kalıpları genişledi.
- vision: OCR çıktısındaki H/L bayrakları, `**kalın**`, HTML/LaTeX birim artıkları temizleniyor; değer+birim aynı
  hücredeyse ayrılıyor. Satır çıkarımı düşünmesiz (`vision_extract_extra_params`), ~10 kat hızlı.
- eval: `labs-e2e` (gerçek LLM + BM25), `assess --bm25`, `eval/bm25_only.py`.
- platform.yml: HEAD isteği 405 döndüğü için CSP kontrolü `curl -D -` ile GET'e çevrildi. `gh run list`: platform
  workflow'u hiç çalıştırılmamış (yalnızca CI ve Veri çek koşuları var); ASR yerelde `/audio/transcriptions` ile
  doğrulandı (sentetik İngilizce ses birebir çözüldü; chat yolu 400 verir, kullanılmıyor).
- Not: `.venv` düzenlenebilir kurulumu ana klasörü gösterir; worktree'de test için `PYTHONPATH=src` gerekir.
