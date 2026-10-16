import json
from pathlib import Path

from .chunk import chunk_document
from .models import Document
from .parse import parse_local_file, parse_medlineplus_topic, parse_wikipedia_extract


def load_documents(raw_dir: Path, local_dir: Path) -> list[Document]:
    docs: list[Document] = []
    for jsonl in sorted((raw_dir / "medlineplus").glob("*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            doc = parse_medlineplus_topic(json.loads(line))
            if doc:
                docs.append(doc)
    for jsonl in sorted((raw_dir / "wikipedia").glob("*.jsonl")):
        lang = jsonl.stem
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            doc = parse_wikipedia_extract(json.loads(line), lang)
            if doc:
                docs.append(doc)
    if local_dir.exists():
        for path in sorted(local_dir.iterdir()):
            doc = parse_local_file(path)
            if doc:
                docs.append(doc)
    return docs


def build_chunks(data_dir: Path) -> int:
    """Ham dosyaları okuyup data/chunks.jsonl dosyasını yazar. Chunk sayısını döner."""
    docs = load_documents(data_dir / "raw", data_dir / "local")
    if not docs:
        raise RuntimeError(
            "Hiç doküman bulunamadı. Önce 'download' çalıştır veya data/local'e dosya koy."
        )
    count = 0
    with (data_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for doc in docs:
            for chunk in chunk_document(doc):
                f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
                count += 1
    return count
