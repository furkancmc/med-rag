import argparse

from medrag.config import get_settings

from .bm25 import BM25
from .store import build_vectors, load_chunks, save_vectors
from .tokenize import tokenize


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.index")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("embed", help="chunk'ları embedding'e çevirip data/index'e kaydet")
    search = sub.add_parser("search", help="BM25 ile hızlı deneme araması")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    settings = get_settings()
    chunks = load_chunks(settings.data_dir)

    if args.cmd == "embed":
        from .embed import E5Embedder

        vectors = build_vectors(chunks, E5Embedder(settings.embedding_model))
        save_vectors(settings.data_dir / "index", [c["id"] for c in chunks], vectors)
        print("kaydedildi:", vectors.shape)
    else:
        bm25 = BM25([tokenize(c["title"] + " " + c["section"] + " " + c["text"]) for c in chunks])
        for i, score in bm25.search(tokenize(args.query), args.k):
            c = chunks[i]
            print(f"{score:6.2f}  [{c['source']}/{c['lang']}] {c['title']} - {c['text'][:90]!r}")


if __name__ == "__main__":
    main()
