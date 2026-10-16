import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .chunk import chunk_document
from .models import Document
from .parse import (
    parse_europepmc_article,
    parse_local_file,
    parse_medlineplus_topic,
    parse_nihods_factsheet,
    parse_openfda_label,
    parse_wikipedia_extract,
)
from .rawstore import read_jsonl
from .textutil import text_hash

# Özetler bütün kalsın diye makale özetlerinde daha büyük parça boyutu
MAX_WORDS = {"europepmc": 320}
DEFAULT_MAX_WORDS = 200
OVERLAP = 30


def _load(rows: list[dict], parse: Callable[..., Document | None], *args) -> list[Document]:
    docs = (parse(row, *args) for row in rows)
    return [d for d in docs if d]


def load_documents(raw_dir: Path, local_dir: Path) -> list[Document]:
    docs: list[Document] = []
    for jsonl in sorted((raw_dir / "medlineplus").glob("*.jsonl")):
        docs += _load(read_jsonl(jsonl), parse_medlineplus_topic)
    for jsonl in sorted((raw_dir / "wikipedia").glob("*.jsonl")):
        docs += _load(read_jsonl(jsonl), parse_wikipedia_extract, jsonl.stem)
    docs += _load(read_jsonl(raw_dir / "europepmc" / "articles.jsonl"), parse_europepmc_article)
    docs += _load(read_jsonl(raw_dir / "openfda" / "labels.jsonl"), parse_openfda_label)
    docs += _load(read_jsonl(raw_dir / "nihods" / "factsheets.jsonl"), parse_nihods_factsheet)
    if local_dir.exists():
        for path in sorted(local_dir.iterdir()):
            doc = parse_local_file(path)
            if doc:
                docs.append(doc)
    return docs


def build_chunk_dicts(docs: list[Document]) -> tuple[list[dict], dict]:
    """Dokümanları parçalar; aynı (normalleştirilmiş) metni taşıyan tekrarları eler.

    Döner: (chunk sözlükleri, istatistik). Sıra ve kimlikler girdiden kararlı türer.
    """
    seen: set[str] = set()
    out: list[dict] = []
    dupes: Counter[str] = Counter()
    per_source: Counter[str] = Counter()
    for doc in docs:
        words = MAX_WORDS.get(doc.source, DEFAULT_MAX_WORDS)
        for chunk in chunk_document(doc, max_words=words, overlap=OVERLAP):
            key = text_hash(chunk.text)
            if key in seen:
                dupes[doc.source] += 1
                continue
            seen.add(key)
            out.append(chunk.to_dict())
            per_source[doc.source] += 1
    return out, {"per_source": dict(per_source), "duplicates": dict(dupes)}


def build_chunks(data_dir: Path) -> int:
    """Ham dosyaları okuyup data/chunks.jsonl dosyasını yazar. Chunk sayısını döner."""
    docs = load_documents(data_dir / "raw", data_dir / "local")
    if not docs:
        raise RuntimeError(
            "Hiç doküman bulunamadı. Önce 'download' çalıştır veya data/local'e dosya koy."
        )
    chunks, stats = build_chunk_dicts(docs)
    with (data_dir / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    docs_by_source = Counter(d.source for d in docs)
    for source in sorted(docs_by_source):
        print(
            f"  {source}: {docs_by_source[source]} doküman, "
            f"{stats['per_source'].get(source, 0)} parça, "
            f"{stats['duplicates'].get(source, 0)} tekrar elendi"
        )
    return len(chunks)
