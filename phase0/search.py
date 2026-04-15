# PHASE0: Qdrant-backed semantic search over the append-only log.
# Replaces the earlier substring-only implementation. See ADR-0009.
"""L1 query path: semantic search over the swarm log.

Given a natural language query, embed it with the same multilingual
model used by the embedder, query the Qdrant collection for top-k
nearest neighbors by cosine similarity, and return the matching
:class:`Message` records. No substring matching; no recency bias;
pure semantic retrieval.

A fallback substring search is still available via
``search(query, log_path, mode="substring")`` for debugging and for
times when the Qdrant service is down — the hot log on disk is
always readable, the vector index is not.
"""

from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient

from phase0.embedder import EMBED_MODEL, QUERY_PREFIX
from phase0.paths import default_log_path, qdrant_collection, qdrant_url
from phase0.reader import read_all
from protocol.roles import Role
from protocol.schema import Message, TokenCost

# Lazy global so the model loads exactly once per process.
_model = None


def _get_model():  # type: ignore[no-untyped-def]
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _payload_to_message(payload: dict[str, object]) -> Message:
    """Reconstruct a :class:`Message` from a Qdrant payload."""
    from datetime import datetime

    ts_raw = payload.get("ts")
    ts = datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str) else datetime.now()
    role_raw = payload.get("role", "answer")
    role = Role(role_raw) if isinstance(role_raw, str) else Role.ANSWER
    model_raw = payload.get("model")
    reply_to_raw = payload.get("reply_to")
    cost_raw = payload.get("token_cost")
    return Message(
        id=str(payload.get("id", "")),
        ts=ts,
        author=str(payload.get("author", "unknown")),
        model=model_raw if isinstance(model_raw, str) else None,
        role=role,
        reply_to=reply_to_raw if isinstance(reply_to_raw, str) else None,
        tags=list(payload.get("tags") or []),  # type: ignore[arg-type]
        text=str(payload.get("text", "")),
        confidence=None,
        token_cost=TokenCost(**cost_raw) if isinstance(cost_raw, dict) else None,
        chain_of_thought=None,
    )


def search_semantic(
    query: str,
    *,
    top_k: int = 5,
    collection: str | None = None,
    url: str | None = None,
    score_threshold: float | None = None,
) -> list[tuple[float, Message]]:
    """Return ``[(score, message), ...]`` sorted by descending similarity."""
    collection = collection or qdrant_collection()
    url = url or qdrant_url()

    model = _get_model()
    vec = model.encode(
        [f"{QUERY_PREFIX}{query}"],
        normalize_embeddings=True,
    )[0].tolist()

    client = QdrantClient(url=url)
    hits = client.query_points(
        collection_name=collection,
        query=vec,
        limit=top_k,
        with_payload=True,
        score_threshold=score_threshold,
    ).points

    out: list[tuple[float, Message]] = []
    for h in hits:
        if h.payload is None:
            continue
        out.append((float(h.score), _payload_to_message(h.payload)))
    return out


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
    """Top-level query API — defaults to semantic, substring on fallback.

    Preserves the pre-existing substring signature so the CLI does
    not need to change shape, but swaps the default to real semantic
    retrieval against Qdrant.
    """
    if mode == "substring":
        return search_substring(query, log_path or default_log_path(), top_k=top_k)
    hits = search_semantic(query, top_k=top_k)
    return [m for _, m in hits]
