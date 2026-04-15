# PHASE0: this will grow a proper async worker in Phase 2 (see
# ADR-0003). For now it's a batch process run manually or by
# auto_ingest. The core logic — local multilingual embeddings upserted
# into Qdrant keyed by Message.id — is the part that survives.
"""L2 → L1 bridge: embed every Message in the hot log into Qdrant.

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


def embed_log(
    *,
    log_path: Path | None = None,
    collection: str | None = None,
    url: str | None = None,
) -> int:
    """Embed every message in the log into Qdrant. Returns count upserted."""
    log_path = log_path or default_log_path()
    collection = collection or qdrant_collection()
    url = url or qdrant_url()

    print(f"embedder: reading {log_path}", file=sys.stderr)
    messages = read_all(log_path)
    if not messages:
        print("embedder: empty log, nothing to do", file=sys.stderr)
        return 0

    print(f"embedder: {len(messages)} unique messages to index", file=sys.stderr)
    print(f"embedder: loading model '{EMBED_MODEL}' (may download ~120MB)", file=sys.stderr)
    model = SentenceTransformer(EMBED_MODEL)

    client = QdrantClient(url=url)
    ensure_collection(client, collection)

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
        print(
            f"embedder: upserted {total}/{len(messages)}",
            file=sys.stderr,
        )
    return total


def main() -> int:
    embed_log()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
