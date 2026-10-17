FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
# Yerel BGE-M3 için CPU torch. GPU gerekiyorsa CUDA'lı torch tabanlı bir imaj kullanın (README bölüm 7).
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install ".[local]" && useradd --create-home --uid 10001 medrag

# Ham veri imaja girer; chunk dosyası ilk açılışta üretilir. Embedding indeksi imajda YOK:
# `python -m medrag.index embed --backend local` ile üretilip /app/data/index_bge_m3 olarak bağlanır (volume).
COPY data/raw ./data/raw
COPY eval/results.md eval/safety_results.md ./eval/
# Geri bildirim, chunk dosyası ve model önbelleği yazılabilsin diye klasörler kullanıcıya verilir.
RUN mkdir -p /app/data/feedback /app/hf && chown -R medrag:medrag /app/data /app/hf

ENV MEDRAG_DATA_DIR=/app/data \
    MEDRAG_LOCAL_INDEX_DIR=/app/data/index_bge_m3 \
    HF_HOME=/app/hf \
    MEDRAG_EVAL_DIR=/app/eval \
    PORT=8000 \
    WEB_CONCURRENCY=1
# EVREN_API_KEY (sohbet LLM'i için) çalıştırırken verilir. Ters vekil arkasındaysanız MEDRAG_TRUST_PROXY_HEADERS=1 ekleyin.
USER medrag
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)"

CMD ["sh", "-c", "exec uvicorn medrag.api.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
