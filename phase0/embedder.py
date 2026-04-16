# DEPRECATED — replaced by phase0/mem0_store.py (ADR-0011).
# This file remains for two reasons:
# 1. append-only repo hygiene (don't delete, deprecate)
# 2. embed_log() can still be used as a one-shot migration tool to
#    re-index the entire JSONL into our custom dmd_messages Qdrant
#    collection (vs Mem0's mem0_dmd collection)
#
# For normal operations, use mem0_store.store() / mem0_store.query()
# instead. The MCP server, appender, and transcript ingester all
# route through mem0_store now.
"""DEPRECATED: L2 → L1 bridge via raw Qdrant. Use mem0_store instead.

Pipeline:
- read the append-only log from ``~/.dmd/swarm.jsonl``
- compute deduplicated message list (the reader handles this)
- embed text using a local multilingual ``sentence-transformers`` model
  (``intfloat/multilingual-e5-small``, 384-dim, Russian + English)
- upsert each vector into the Qdrant collection, keyed by
  ``Message.id`` so re-runs are idempotent

This script is **CPU-bound** — expect ~20-40ms per message on a
reasonable laptop. For the project's current ~418-message corpus
that is ~15 seconds. For the user's 3-year ChatGPT dump (estimated
~50-500k messages) it will be 15-200 minutes on first run, then
seconds per incremental batch.
"""

from __future__ import annotations

import sys
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

from phase0.paths import default_log_path, qdrant_collection, qdrant_url
from phase0.reader import read_all
from protocol.schema import Message

EMBED_MODEL = "intfloat/multilingual-e5-small"
VECTOR_DIM = 384
BATCH_SIZE = 64

# The e5 family expects a prefix: "passage: " for documents and
# "query: " for queries. This is non-obvious but important for
# retrieval quality.
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "

# Module-level lazy globals — loaded once per process. Long-lived
# processes (MCP server) pay the ~3-5s model load on first append
# then get free embeds. CLI one-shots that don't pass embed=True
# never load the model at all.
_model: SentenceTransformer | None = None
_client: QdrantClient | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=qdrant_url())
        ensure_collection(_client, qdrant_collection())
    return _client


def ensure_collection(client: QdrantClient, name: str) -> None:
    """Create the Qdrant collection if it does not exist."""
    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    print(f"embedder: created collection '{name}' (dim={VECTOR_DIM})", file=sys.stderr)


def _message_payload(msg: Message) -> dict[str, object]:
    """Qdrant payload — keep it lean, used for filters and display."""
    return {
        "id": msg.id,
        "ts": msg.ts.isoformat(),
        "author": msg.author,
        "model": msg.model,
        "role": msg.role.value,
        "reply_to": msg.reply_to,
        "tags": msg.tags,
        "text": msg.text,  # stored for display; actual search uses vector
    }


def _embed_text_for_passage(msg: Message) -> str:
    """Combine text + chain_of_thought for richer retrieval.

    Semantically, the reasoning often contains more specific keywords
    than the final response, so concatenating both gives better recall
    on debug-style queries ("I thought about X").
    """
    if msg.chain_of_thought:
        return f"{PASSAGE_PREFIX}{msg.text}\n\nreasoning: {msg.chain_of_thought}"
    return f"{PASSAGE_PREFIX}{msg.text}"


def _qdrant_point_id(msg_id: str) -> int:
    """Qdrant integer point ids derived from the 16-hex Message.id.

    Qdrant requires numeric or UUID ids. Taking the first 16 hex
    chars (64 bits) and treating them as an unsigned int gives us a
    collision-resistant, deterministic mapping so upserts are
    idempotent — the same Message.id always hashes to the same point.
    """
    return int(msg_id, 16)


def embed_messages(
    messages: list[Message],
    *,
    verbose: bool = False,
) -> int:
    """Embed an arbitrary batch of messages and upsert into Qdrant.

    Used both by ``embed_log`` (full-log batch) and by the appender
    (single-message incremental embed when ``embed=True``). Loads the
    model and Qdrant client lazily and caches them at module level
    so a long-lived process pays the ~3-5 second startup once and
    then sees per-message latency of ~30ms.

    Returns the number of points upserted.
    """
    if not messages:
        return 0
    model = _get_model()
    client = _get_client()
    collection = qdrant_collection()

    total = 0
    for start in range(0, len(messages), BATCH_SIZE):
        batch = messages[start : start + BATCH_SIZE]
        texts = [_embed_text_for_passage(m) for m in batch]
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        points = [
            PointStruct(
                id=_qdrant_point_id(m.id),
                vector=vec.tolist(),
                payload=_message_payload(m),
            )
            for m, vec in zip(batch, vectors, strict=True)
        ]
        client.upsert(collection_name=collection, points=points)
        total += len(points)
        if verbose:
            print(
                f"embedder: upserted {total}/{len(messages)}",
                file=sys.stderr,
            )
    return total


def embed_log(
    *,
    log_path: Path | None = None,
) -> int:
    """Embed every message in the log into Qdrant. Returns count upserted."""
    log_path = log_path or default_log_path()
    print(f"embedder: reading {log_path}", file=sys.stderr)
    messages = read_all(log_path)
    if not messages:
        print("embedder: empty log, nothing to do", file=sys.stderr)
        return 0
    print(
        f"embedder: {len(messages)} unique messages to index "
        f"with model '{EMBED_MODEL}' (may download ~120MB on first run)",
        file=sys.stderr,
    )
    return embed_messages(messages, verbose=True)


def main() -> int:
    embed_log()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
