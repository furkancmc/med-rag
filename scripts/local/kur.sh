#!/usr/bin/env bash
# Yerel kurulum (Linux/macOS): bash scripts/local/kur.sh
# Anahtarı dosyaya yazmaz; çalıştırırken ortam değişkeni olarak ister.
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m venv .venv
. .venv/bin/activate
pip install -q -e ".[dev]"
[ -f .env ] || cp .env.example .env
echo "Kurulum tamam. Başlatmak için:"
echo "  export EVREN_API_KEY=...   # anahtarını buraya yaz"
echo "  PYTHONPATH=src uvicorn medrag.api.main:app --host 0.0.0.0 --port 8000"
