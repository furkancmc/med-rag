from collections.abc import Callable

KS = (1, 3, 5, 10)


def first_relevant_rank(hit_doc_ids: list[str], doc_id: str) -> int | None:
    """İlgili dokümanın ilk geçtiği sıra (1'den başlar), yoksa None."""
    for rank, d in enumerate(hit_doc_ids, start=1):
        if d == doc_id:
            return rank
    return None


def evaluate(
    queries: list[dict], search: Callable[[str], list[dict]]
) -> dict[str, float]:
    """search(query) -> chunk listesi. recall@k (doküman düzeyinde) ve MRR@10 döner."""
    ranks = []
    for q in queries:
        hits = search(q["query"])
        ranks.append(first_relevant_rank([h["doc_id"] for h in hits], q["doc_id"]))
    n = len(ranks) or 1
    result = {f"recall@{k}": sum(1 for r in ranks if r and r <= k) / n for k in KS}
    result["mrr@10"] = sum(1 / r for r in ranks if r) / n
    return result


def format_table(results: dict[str, dict[str, float]]) -> str:
    cols = [f"recall@{k}" for k in KS] + ["mrr@10"]
    lines = ["| yöntem | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for name, r in results.items():
        lines.append(f"| {name} | " + " | ".join(f"{r[c]:.3f}" for c in cols) + " |")
    return "\n".join(lines)
