import argparse
import os
from pathlib import Path

from medrag.config import get_settings

from .bm25 import BM25
from .embed import ApiEmbedder
from .store import embed_incremental, load_chunks, save_vectors
from .tokenize import tokenize


def check_api(settings, chunks: list[dict]) -> None:
    import time

    from .embed import passage_text

    api_key = os.environ.get("EVREN_API_KEY")
    if not api_key:
        raise SystemExit("EVREN_API_KEY tanımlı değil")
    for size, count in ((64, 1), (64, 6), (64, 12)):
        embedder = ApiEmbedder(
            settings.embed_api_url,
            api_key,
            settings.embed_api_model,
            settings.embed_dimensions,
            batch_size=size,
            workers=count,
        )
        texts = [passage_text(c) for c in chunks[: size * count]]
        start = time.time()
        try:
            vecs = embedder.encode_passages(texts)
        except Exception as e:  # noqa: BLE001 - teşhis aracı: her hatayı olduğu gibi göster
            print(f"{count} paralel x {size}: HATA {type(e).__name__}: {e} ({time.time() - start:.1f}s)", flush=True)
            continue
        took = time.time() - start
        print(f"{count} paralel x {size}: {took:.1f}s, {len(texts) / took:.1f} metin/sn, şekil={vecs.shape}", flush=True)


def list_models(settings) -> None:
    """Servisteki modelleri listeler (rerank ve görsel model var mı görmek için)."""
    import json
    import urllib.request

    req = urllib.request.Request(
        settings.llm_api_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {os.environ.get('EVREN_API_KEY', '')}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001 - teşhis aracı
        print("model listesi alınamadı:", type(e).__name__, e, flush=True)
        return
    for m in data.get("data", []):
        extra = {k: v for k, v in m.items() if k not in ("id", "object", "created", "owned_by")}
        print("MODEL", m.get("id"), json.dumps(extra, ensure_ascii=False)[:300], flush=True)


def check_rerank(settings) -> None:
    """Olası rerank uç noktalarını dener."""
    import json
    import urllib.request

    body = {
        "query": "diyabet belirtileri",
        "documents": ["Diyabette sık idrara çıkma görülür.", "Grip ateş yapar."],
    }
    for path in ("/rerank", "/v1/rerank"):
        for model in ("qwen3-reranker-8b", "qwen3-reranker-4b", "qwen3-reranker", "bge-reranker-v2-m3"):
            base = settings.llm_api_url.rstrip("/")
            url = (base[: -len("/v1")] if path.startswith("/v1") and base.endswith("/v1") else base) + path
            req = urllib.request.Request(
                url,
                data=json.dumps({**body, "model": model}).encode(),
                headers={
                    "Authorization": f"Bearer {os.environ.get('EVREN_API_KEY', '')}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    print("RERANK OK", url, model, resp.read()[:300], flush=True)
            except Exception as e:  # noqa: BLE001 - teşhis aracı
                print("RERANK yok", url, model, type(e).__name__, str(e)[:120], flush=True)


def check_chat(settings) -> None:
    """Sohbet uç noktasının cevap yapısını yazdırır (içerik metni değil, alanlar ve uzunluklar)."""
    import time

    from medrag.llm import EvrenLLM

    llm = EvrenLLM(settings.llm_api_url, settings.llm_model)
    msgs = [{"role": "user", "content": "Tek cümleyle yanıtla: grip nedir?"}]
    for max_tokens in (120, 600, 2000):
        start = time.time()
        try:
            data = llm.raw(msgs, max_tokens)
        except Exception as e:  # noqa: BLE001 - teşhis aracı
            print(f"max_tokens={max_tokens}: HATA {type(e).__name__}: {e}", flush=True)
            continue
        choice = data["choices"][0]
        message = choice["message"]
        fields = {k: (len(v) if isinstance(v, str) else type(v).__name__) for k, v in message.items()}
        print(
            f"max_tokens={max_tokens}: {time.time() - start:.1f}s model={data.get('model')} "
            f"finish={choice.get('finish_reason')} usage={data.get('usage')} alanlar={fields}",
            flush=True,
        )
        content = message.get("content")
        if content:
            print("  örnek cevap:", content[:150].replace("\n", " "), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m medrag.index")
    sub = parser.add_subparsers(dest="cmd", required=True)
    embed = sub.add_parser("embed", help="chunk'ları embedding'e çevirip kaydet")
    embed.add_argument("--index-dir", help="varsayılan: <data_dir>/index")
    embed.add_argument("--full", action="store_true", help="önbelleği yok say, hepsini yeniden hesapla")
    embed.add_argument(
        "--trust-legacy",
        action="store_true",
        help="özet dosyası olmayan eski indeksi chunk kimliğine güvenerek devral",
    )
    sub.add_parser("check", help="embedding API'sini birkaç istekle dene, süreleri yazdır")
    search = sub.add_parser("search", help="BM25 ile hızlı deneme araması")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    settings = get_settings()
    chunks = load_chunks(settings.data_dir)

    if args.cmd == "check":
        list_models(settings)
        check_rerank(settings)
        check_chat(settings)
        check_api(settings, chunks)
        return

    if args.cmd == "embed":
        api_key = os.environ.get("EVREN_API_KEY")
        if not api_key:
            raise SystemExit("EVREN_API_KEY ortam değişkeni tanımlı değil")
        embedder = ApiEmbedder(
            settings.embed_api_url,
            api_key,
            settings.embed_api_model,
            settings.embed_dimensions,
            batch_size=settings.embed_batch_size,
            workers=settings.embed_workers,
        )
        meta = {
            "model": settings.embed_api_model,
            "dimensions": settings.embed_dimensions,
        }
        index_dir = Path(args.index_dir) if args.index_dir else settings.data_dir / "index"
        if args.full:  # önbelleği yok say: boş bir dizinden başla
            cache_dir = index_dir.with_name(index_dir.name + ".__yok__")
        else:
            cache_dir = index_dir
        batch = settings.embed_batch_size * settings.embed_workers
        vectors, hashes, stats = embed_incremental(
            chunks,
            embedder,
            cache_dir,
            settings.embed_api_model,
            settings.embed_dimensions,
            batch=batch,
            trust_legacy=args.trust_legacy,
        )
        fmt = save_vectors(
            index_dir,
            [c["id"] for c in chunks],
            vectors,
            meta,
            hashes,
            settings.index_max_float16_mb,
        )
        print("embedding özeti:", stats.summary())
        print("kaydedildi:", index_dir, vectors.shape, fmt)
    else:
        bm25 = BM25([tokenize(c["title"] + " " + c["section"] + " " + c["text"]) for c in chunks])
        for i, score in bm25.search(tokenize(args.query), args.k):
            c = chunks[i]
            print(f"{score:6.2f}  [{c['source']}/{c['lang']}] {c['title']} - {c['text'][:90]!r}")


if __name__ == "__main__":
    main()
