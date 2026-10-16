FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Ham veri ve embedding indeksi imaja girer; chunk dosyası ilk açılışta üretilir.
COPY data/raw ./data/raw
COPY data/index_qwen3 ./data/index_qwen3

ENV MEDRAG_DATA_DIR=/app/data
ENV MEDRAG_INDEX_DIR=/app/data/index_qwen3
# EVREN_API_KEY çalıştırırken verilir: docker run -e EVREN_API_KEY=... -p 8000:8000 medrag
EXPOSE 8000
CMD ["python", "-m", "medrag.api"]
