import argparse
import os
import sys
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from medrag.config import get_settings

from .build import build_chunks
from .curated import curated_titles
from .download import (
    DEFAULT_CATEGORIES,
    download_medlineplus,
    download_medlineplus_report,
    download_wikipedia,
    download_wikipedia_report,
    search_categories,
)
from .europepmc import download_europepmc
from .nihods import download_nihods
from .openfda import download_openfda
from .report import SourceReport

SOURCES = ("medlineplus", "wikipedia-tr", "wikipedia-en", "europepmc", "openfda", "nihods")


def _runner(
    name: str, raw: Path, limit: int | None, per_topic: int
) -> Callable[[], SourceReport]:
    full = limit is None
    if name == "medlineplus":
        return lambda: download_medlineplus_report(raw, limit=limit)
    if name.startswith("wikipedia-"):
        lang = name.split("-", 1)[1]
        return lambda: download_wikipedia_report(
            raw, lang, titles=curated_titles(lang), limit=limit, prune=full
        )
    if name == "europepmc":
        return lambda: download_europepmc(
            raw, curated_titles("en"), per_topic=per_topic, limit=limit
        )
    if name == "openfda":
        return lambda: download_openfda(
            raw, limit=limit, api_key=os.environ.get("OPENFDA_API_KEY", "")
        )
    if name == "nihods":
        return lambda: download_nihods(raw, limit=limit)
    raise SystemExit(f"bilinmeyen kaynak: {name} (seçenekler: {', '.join(SOURCES)})")


def _safe(name: str, run: Callable[[], SourceReport]) -> SourceReport:
    """Bir kaynağın çökmesi diğerlerini durdurmasın; hata raporlanır."""
    start = time.time()
    try:
        report = run()
    except Exception as e:  # noqa: BLE001 - kaynak başına yalıtım, ayrıntı günlüğe yazılır
        traceback.print_exc()
        report = SourceReport(name, fatal=f"{type(e).__name__}: {str(e)[:200]}")
        report.seconds = time.time() - start
    print(report.render(), flush=True)
    return report


def fetch(sources: list[str], raw: Path, limit: int | None, per_topic: int) -> int:
    """Kaynakları paralel indirir (farklı sunucular), özet yazdırır. Başarısız kaynak sayısını döner."""
    if sources == ["all"]:
        sources = list(SOURCES)
    runners = {s: _runner(s, raw, limit, per_topic) for s in sources}
    with ThreadPoolExecutor(max_workers=len(runners)) as pool:
        futures = {s: pool.submit(_safe, s, r) for s, r in runners.items()}
        reports = [futures[s].result() for s in runners]
    print("\n=== ÖZET ===")
    for r in reports:
        status = "TAMAM" if r.ok else "HATA "
        print(f"{status} {r.source}: alınan {r.fetched}/{r.requested}, belge {r.documents}"
              + (f"  [{r.fatal}]" if r.fatal else ""))
    return sum(1 for r in reports if not r.ok)


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

    fetch_p = sub.add_parser(
        "fetch", help="birden çok kaynağı paralel indir (europepmc, openfda, nihods, ...)"
    )
    fetch_p.add_argument("--sources", default="all", help=f"virgülle: all | {', '.join(SOURCES)}")
    fetch_p.add_argument("--limit", type=int, default=None, help="kaynak başına öğe sınırı (deneme)")
    fetch_p.add_argument("--per-topic", type=int, default=None, help="Europe PMC: konu başına makale")

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
            cats_ = args.category or DEFAULT_CATEGORIES[args.lang]
            path = download_wikipedia(data_dir / "raw", args.lang, cats_, args.limit, args.depth)
        print("yazıldı:", path)
    elif args.cmd == "fetch":
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        per_topic = args.per_topic or get_settings().europepmc_per_topic
        failed = fetch(sources, data_dir / "raw", args.limit, per_topic)
        sys.exit(1 if failed else 0)
    else:
        print("chunk sayısı:", build_chunks(data_dir))


if __name__ == "__main__":
    main()
