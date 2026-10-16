You are one of 7 parallel engineers working on `medrag`, a Turkish medical RAG assistant (FastAPI + vanilla JS). You are in your own git worktree of the repo (the lead's checkout is /home/user/phone; do not touch it). Read PLAN.md (section "Faz 2": workstreams, file ownership table, contracts, Evren models) and README.md first, then the code you will touch. IMPORTANT: usage limits may interrupt you at any time — commit small, working increments often so progress is never lost.

## Environment facts
- Python venv with all deps: /tmp/claude-0/venv. From your worktree root run tests with `PYTHONPATH=src /tmp/claude-0/venv/bin/python -m pytest -q` and lint with `/tmp/claude-0/venv/bin/ruff check .` (local ruff has extra rules like BLE/PLW enabled — keep it clean). Avoid `pip install` unless truly needed (the venv is shared by parallel agents).
- This sandbox has NO network except PyPI: you cannot reach the Evren API. Every network call must be dependency-injected (like the existing `post=` callables) and unit-tested with fakes. Real-API validation is done later by the lead via GitHub Actions — so add/extend workflow_dispatch workflows and `src/medrag/eval/*_cli.py` modules (auto-discovered by `python -m medrag.eval`, see eval/__main__.py) that print clear diagnostics.
- Evren API: OpenAI-compatible, base https://evren-llmapi.ssyz.org.tr/v1, key in env EVREN_API_KEY (never hardcode, log or print it). Models: chat `auto` (routes to qwen3-vl-30b-a3b), `deepseek-v4-flash` (thinking), `deepseek-v4.1-flash`, `glm-5.3`, `qwen3.8-flash-next`, `mimo-v2.6-pro`, `gemma-4-31b`; embeddings `qwen3-embedding-8b` (/v1/embeddings); rerank `qwen3-reranker-8b` via `POST /v1/rerank {"model","query","documents":[str]}` → `{"results":[{"index":int,"relevance_score":float?,"document":{"text":...}}], ...}` (verified working, served as qwen/qwen3-vl-reranker-8b; exact score key unconfirmed — accept `relevance_score` or `score`), context 4096 tokens. Everything is free and runs on H200 GPUs: use HIGH concurrency (default 16 parallel requests, configurable) with retry/backoff on 429/5xx. Measured: one embedding request has ~3-6 s fixed latency; ~25-33 texts/s saturation.
- Conventions: stdlib urllib for HTTP (no requests/httpx in runtime code), dependency injection, Turkish user-facing text, short Turkish comments/docstrings, type hints, small functions. Settings live in src/medrag/config.py — add your fields ONLY directly under your workstream's comment block ("Arama ve embedding (iş akışı A)"). Shared lazy deps in src/medrag/deps.py (do not edit).

## Rules
- Only edit files you own (below) plus: your block in config.py, new tests named `tests/test_retrieval_*.py`, existing tests directly covering your files, and pyproject.toml only if truly needed.
- Do NOT edit README.md, PLAN.md, deps.py, api/main.py, or other workstreams' files (index/store.py and ingest/** belong to the data workstream; chat/** and llm.py to the safety workstream). If you need something from another workstream, define a clean interface on your side and mention it in your report.
- Commit early and often in your worktree branch. Commit messages: short, plain Turkish, each ending with exactly these two lines:
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01QKPbPDPCCodzqbrCZfCgw3
  Do NOT push and do NOT switch branches; the lead merges your branch.
- Before finishing: all tests pass, ruff clean, everything committed (`git status` clean).
- Your final message (report) in English must contain: (1) branch name and commit list, (2) what you built and key design decisions, (3) new settings/endpoints/files, (4) exact real-API validation steps for the lead (which workflow to run with which inputs, what output means success), (5) known limitations/risks, (6) a ready-to-paste Turkish "README notları" markdown section for users and developers.

## Your workstream: A — Retrieval (reranker, multi-query, eval)
You own: src/medrag/retrieve.py, src/medrag/rerank.py (new), src/medrag/index/embed.py, src/medrag/eval/search_cli.py, src/medrag/eval/queries.py, src/medrag/eval/metrics.py, .github/workflows/eval.yml, tests/test_retrieve.py, tests/test_api_embed.py, tests/test_eval.py, new tests/test_retrieval_*.py.

A previous attempt of this workstream was interrupted after only writing this settings block — start by adding it under the "Arama ve embedding (iş akışı A)" block in config.py (after `index_dir`), adjust if you see fit, and commit:
```
    embed_workers: int = 16  # paralel embedding isteği (H200: yüksek eşzamanlılık)
    embed_query_cache_size: int = 1024  # sorgu embedding LRU önbelleği; 0 kapatır
    # Reranker: vektör aramadan `rerank_pool` aday alınır, yeniden sıralanıp ilk k döner.
    rerank_enabled: bool = True
    rerank_api_url: str = "https://evren-llmapi.ssyz.org.tr/v1"
    rerank_model: str = "qwen3-reranker-8b"
    rerank_pool: int = 40
    rerank_batch_size: int = 20  # istek başına doküman; gruplar paralel gider
    rerank_timeout: float = 20.0  # saniye, yeniden denemeler dahil; aşılırsa vektör sırası
    rerank_template: str = "qwen3"  # "qwen3": Qwen3-Reranker talimat şablonu, "none": ham metin
    # Çoklu sorgu: İngilizce çeviri + 1-2 Türkçe yeniden yazım, RRF ile birleşir (ölçülene kadar kapalı).
    multiquery_enabled: bool = False
    multiquery_model: str = "auto"
    multiquery_timeout: float = 15.0  # saniye; aşılırsa sadece orijinal sorgu kullanılır
```

Current state: vector search over 13,236 chunks (qwen3-embedding-8b, 1024-dim, cosine) is the default (recall@5 0.85, recall@10 0.94, MRR 0.73, recall@1 0.65 on 150 LLM-generated Turkish questions; BM25 and hybrid were worse — see eval/results.md). The chat service (owned by another workstream) calls `retriever.search(query, k=top_k)` and `load_retriever(settings)` builds the retriever; keep that signature and behavior compatible.

Tasks:
1. Reranker (`rerank.py`): `ApiReranker` calling `/v1/rerank` with `qwen3-reranker-8b`. Candidate pool from vector search (configurable, default 40) → rerank → top k. Fit the 4096-token context: send title + section + truncated text (~1500 chars) per doc; split large pools into batches sent in parallel; robust parsing (`relevance_score`/`score`, missing indices); on any error fall back to the vector order and log once (no crash). Make the Qwen3-Reranker instruction template optional (setting) since the server may or may not apply it.
2. Multi-query expansion: an LLM (configurable model, default `auto`) returns an English translation + 1-2 Turkish paraphrases (robust parsing of plain lines or JSON); run the vector searches in parallel and fuse with RRF into the candidate pool before reranking. Switchable; default OFF until the eval proves it helps — expose CLI flags so the lead can measure.
3. Embedding client (`index/embed.py`): thread-safe LRU cache for query embeddings, default workers raised to 16 and configurable from settings.
4. `load_retriever(settings)` returns the configured pipeline (vector → optional multi-query → optional rerank), reranking ON by default. The chat service must not need changes. Keep BM25/hybrid modes available.
5. Eval (`search_cli.py`, `queries.py`, `metrics.py`): `run` compares vector, vector+rerank (pool 20 and 40), multiquery+vector, multiquery+rerank, plus bm25 as a baseline; metrics recall@1/3/5/10, MRR@10 and mean/p95 latency per query; write eval/results.md (markdown table + short notes) and eval/results.json. Add `--methods` and `--limit` flags. `gen --n 500` with high concurrency (16 workers default) and quotas that adapt to whatever (source, lang) groups exist in chunks (the data workstream is adding sources like `europepmc`, `openfda`, `ods`), keep Turkish questions, dedupe questions; backward compatible with the existing eval/queries.jsonl format.
6. `.github/workflows/eval.yml`: workflow_dispatch inputs for `n` (regenerate size), `regenerate` (bool), `methods`; commit eval/results.md, eval/results.json, eval/queries.jsonl like today.
7. Tests for everything with fakes (rerank parsing/batching/fallback, multi-query fusion, LRU cache thread safety, eval metrics/latency, quotas).
Report the expected latency added by reranking and multi-query.