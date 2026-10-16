FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && useradd --create-home --uid 10001 medrag

# Ham veri ve embedding indeksi imaja girer; chunk dosyası ilk açılışta üretilir.
COPY data/raw ./data/raw
COPY data/index_qwen3 ./data/index_qwen3
COPY eval/results.md eval/safety_results.md ./eval/
# Geri bildirim ve chunk dosyası yazılabilsin diye data klasörü kullanıcıya verilir.
RUN mkdir -p /app/data/feedback && chown -R medrag:medrag /app/data

ENV MEDRAG_DATA_DIR=/app/data \
    MEDRAG_INDEX_DIR=/app/data/index_qwen3 \
    MEDRAG_EVAL_DIR=/app/eval \
    PORT=8000 \
    WEB_CONCURRENCY=1
# EVREN_API_KEY çalıştırırken verilir. Ters vekil arkasındaysanız MEDRAG_TRUST_PROXY_HEADERS=1 ekleyin.
USER medrag
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)"

CMD ["sh", "-c", "exec uvicorn medrag.api.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
