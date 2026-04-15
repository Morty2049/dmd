# PHASE0: this file is throwaway — replaced in Phase 2 by Qdrant with
# INT8-quantized HNSW. See ADR-0003 and ADR-0005.
"""Local substring search over the Phase 0 log.

Deliberately dumb: case-insensitive term matching with a small recency
tiebreaker. No embeddings, no tokenization, no stemming. The point is
to validate the *API shape* (query → top-k Messages) that Phase 2 will
implement against Qdrant — not to be a good ranker.

The next commit after Phase 0 settles will swap this in-place for a
``sentence-transformers`` + numpy index. The CLI and callers do not
need to change.
"""

from __future__ import annotations

from pathlib import Path

from phase0.reader import read_all
from protocol.schema import Message


def search(query: str, log_path: Path, *, top_k: int = 5) -> list[Message]:
    """Return up to ``top_k`` messages most similar to ``query``.

    Scoring: sum of term-frequency matches in ``msg.text``, with a
    small recency bonus so that among equally-scoring messages the
    newest wins.
    """
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
        # Recency is a tiebreaker, not a primary ranker.
        recency_bonus = m.ts.timestamp() * 1e-10
        scored.append((hits + recency_bonus, m))
    scored.sort(key=lambda p: p[0], reverse=True)
    return [m for _, m in scored[:top_k]]
