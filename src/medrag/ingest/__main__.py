import argparse

from medrag.config import get_settings

from .build import build_chunks
from .download import DEFAULT_CATEGORIES, download_medlineplus, download_wikipedia


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("medlineplus", help="MedlinePlus health topics XML indir")

    wiki = sub.add_parser("wikipedia", help="Vikipedi tıp makalelerini indir")
    wiki.add_argument("--lang", choices=["tr", "en"], default="tr")
    wiki.add_argument("--category", action="append", help="birden fazla verilebilir")
    wiki.add_argument("--limit", type=int, default=500)
    wiki.add_argument("--depth", type=int, default=1)

    sub.add_parser("build", help="ham veriden data/chunks.jsonl üret")

    args = parser.parse_args()
    data_dir = get_settings().data_dir

    if args.cmd == "medlineplus":
        for p in download_medlineplus(data_dir / "raw"):
            print("indirildi:", p)
    elif args.cmd == "wikipedia":
        cats = args.category or DEFAULT_CATEGORIES[args.lang]
        path = download_wikipedia(data_dir / "raw", args.lang, cats, args.limit, args.depth)
        print("yazıldı:", path)
    else:
        print("chunk sayısı:", build_chunks(data_dir))


if __name__ == "__main__":
    main()
