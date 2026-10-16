# Barındırma örnekleri

Ortak gereksinimler: `EVREN_API_KEY` ortam değişkeni (sır olarak girin), sunucudan
`https://evren-llmapi.ssyz.org.tr` adresine çıkış erişimi, en az 1 GB bellek.

- `render.yaml`: Render (Docker). Sırları panelden girin.
- `fly.toml`: Fly.io (`fly launch --no-deploy`, `fly secrets set EVREN_API_KEY=...`, `fly deploy`).
- `Caddyfile` + `docker-compose.yml`: kendi VPS'inizde otomatik HTTPS.
- `medrag.service`: Docker olmadan systemd ile çalıştırma.

Ters vekil arkasında `MEDRAG_TRUST_PROXY_HEADERS=1` açın; aksi halde hız sınırı tüm
kullanıcıları vekil IP'si olarak görür. Genel yayında `MEDRAG_ACCESS_CODE` ve `MEDRAG_HSTS=1`
önerilir. Mikrofon ve kamera yalnızca HTTPS'te çalışır.
