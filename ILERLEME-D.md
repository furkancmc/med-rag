# İlerleme D (belirti değerlendirme)

- assess/** (models, jsonx, rules, service), api/routes/assess.py, web/assess.html, eval/assess_cli.py + assess_cases.py, .github/workflows/assess.yml, tests/test_assess_core.py yapıldı.
- Gerçek API (deepseek-v4.1-flash) senaryo koşusu yapıldı: 19 senaryo, 18 uygun, 1 aşağı triyaj (çocukta hafif ateş: home; beklenen aralık sonradan home..today yapıldı). JSON geçerlilik %100.
- Not: o koşu gerçek embedding kullandı (kullanıcı kararından önce). Karardan sonra eval varsayılanı sahte (kaynaksız) retriever; `--real-retriever` ile gerçek.
- ERTELENDİ: gerçek embedding ile uçtan uca (kaynaklı) doğrulama.
