import argparse

from medrag.config import get_settings

from .build import build_chunks
from .curated import curated_titles
from .download import (
    DEFAULT_CATEGORIES,
    download_medlineplus,
    download_wikipedia,
    search_categories,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("medlineplus", help="MedlinePlus health topics XML indir")

    wiki = sub.add_parser("wikipedia", help="Vikipedi tıp makalelerini indir")
    wiki.add_argument("--lang", choices=["tr", "en"], default="tr")
    wiki.add_argument("--curated", action="store_true", help="elle seçilmiş konu listesini indir")
    wiki.add_argument("--category", action="append", help="birden fazla verilebilir")
    wiki.add_argument("--limit", type=int, default=500)
    wiki.add_argument("--depth", type=int, default=1)

    cats = sub.add_parser("categories", help="Vikipedi'de kategori adı ara")
    cats.add_argument("--lang", choices=["tr", "en"], default="tr")
    cats.add_argument("query")

    sub.add_parser("build", help="ham veriden data/chunks.jsonl üret")

    args = parser.parse_args()
    data_dir = get_settings().data_dir

    if args.cmd == "medlineplus":
        print("yazıldı:", download_medlineplus(data_dir / "raw"))
    elif args.cmd == "categories":
        for title in search_categories(args.lang, args.query):
            print(title)
    elif args.cmd == "wikipedia":
        if args.curated:
            path = download_wikipedia(
                data_dir / "raw", args.lang, titles=curated_titles(args.lang)
            )
        else:
            cats = args.category or DEFAULT_CATEGORIES[args.lang]
            path = download_wikipedia(data_dir / "raw", args.lang, cats, args.limit, args.depth)
        print("yazıldı:", path)
    else:
        print("chunk sayısı:", build_chunks(data_dir))


if __name__ == "__main__":
    main()
