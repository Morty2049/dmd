# PHASE0: this file is throwaway — replaced in Phase 2 by Qdrant with
# INT8-quantized HNSW. See ADR-0003 and ADR-0005.
"""Local semantic search over the Phase 0 log.

Initial pass uses naive substring matching so we can exercise the CLI
without pulling heavy ML deps. The next commit adds an embedding-backed
ranker using ``sentence-transformers`` with a numpy index. Neither is a
production retrieval layer — they exist to validate the search API
shape that Phase 2 will implement against Qdrant.
"""

from __future__ import annotations

from pathlib import Path

from protocol.schema import Message


def search(query: str, log_path: Path, *, top_k: int = 5) -> list[Message]:
    """Return the ``top_k`` messages most similar to ``query``."""
    raise NotImplementedError("phase0.search.search: scheduled for next commit")
