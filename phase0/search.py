# PHASE0: Semantic search via Mem0 (ADR-0011), substring fallback.
"""L1 query path: semantic search over the swarm log.

Primary path goes through Mem0 (which manages Qdrant embeddings
internally). Fallback substring search reads the JSONL hot log
directly — works when Qdrant is down.
"""

from __future__ import annotations

from pathlib import Path

from phase0.paths import default_log_path
from phase0.reader import read_all
from protocol.schema import Message


def search_semantic(
    query: str,
    *,
    top_k: int = 5,
    user_id: str = "global",
    agent_id: str | None = None,
) -> list[tuple[float, Message]]:
    """Semantic search via Mem0 → Qdrant."""
    from phase0.mem0_store import query as mem0_query

    return mem0_query(query, top_k=top_k, user_id=user_id, agent_id=agent_id)


def search_substring(query: str, log_path: Path, *, top_k: int = 5) -> list[Message]:
    """Fallback: substring match on log text. Use when Qdrant is down."""
    terms = [t for t in query.lower().split() if t]
    if not terms:
        return []
    messages = read_all(log_path)
    scored: list[tuple[float, Message]] = []
    for m in messages:
        text = m.text.lower()
        hits = sum(text.count(t) for t in terms)
        if hits == 0:
            continue
        recency_bonus = m.ts.timestamp() * 1e-10
        scored.append((hits + recency_bonus, m))
    scored.sort(key=lambda p: p[0], reverse=True)
    return [m for _, m in scored[:top_k]]


def search(
    query: str,
    log_path: Path | None = None,
    *,
    top_k: int = 5,
    mode: str = "semantic",
) -> list[Message]:
    """Top-level query API — semantic default, substring fallback."""
    if mode == "substring":
        return search_substring(query, log_path or default_log_path(), top_k=top_k)
    hits = search_semantic(query, top_k=top_k)
    return [m for _, m in hits]
