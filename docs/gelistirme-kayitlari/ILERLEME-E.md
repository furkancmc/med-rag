# Ilerleme E

- Tamamlandi: labs/ (reference 34 test, interpret, service), vision.py, routes labs+vision, web/labs.html, config blogu, eval/labs_cli.py, .github/workflows/labs.yml, testler. pytest 195 gecti, ruff temiz.
- Bulgu: OCR modelleri /v1/ocr ucunda: {"model","image":data-URI} -> {"text"} (deepseek-ocr-2 markdown tablo, dots-ocr HTML tablo); chat ucu OCR modellerini reddeder.
- Gercek API: yalnizca deepseek-v4.1-flash (cikarim + aciklama) ve onceden kisa OCR/qwen3-vl denemeleri. Embedding/reranker CAGRILMADI (kullanici karari); kaynakli aciklama sahte retriever ile denendi.
- ERTELENDI: gercek retriever (embedding) ile kaynakli aciklama dogrulamasi, labs-ocr olcumu (workflow), tarayicida labs.html gorsel kontrolu (node/playwright yok).
