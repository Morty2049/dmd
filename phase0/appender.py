# PHASE0: this file is throwaway — replaced in Phase 2 by a NATS JetStream
# publisher + ClickHouse batch writer. See ADR-0003 and ADR-0005.
"""Append a :class:`Message` to the Phase 0 JSONL log.

Opens the log file in binary append mode and writes a single
newline-terminated JSON line. POSIX guarantees that ``O_APPEND`` writes
smaller than ``PIPE_BUF`` are atomic with respect to each other, so
multiple processes appending concurrently cannot interleave within a
line — matching the atomicity guarantee we rely on for Phase 0.

Idempotency is handled on the read path via the deterministic
:attr:`Message.id`. Duplicate appends of the same id are dropped during
read rather than rejected at write time, keeping the writer lock-free.

When ``embed=True`` the message is also indexed into Qdrant immediately
so that subsequent semantic search calls find it without waiting for
a batch embedder run. The embedder import is lazy so callers that do
not pass ``embed=True`` never pull ``sentence-transformers`` into
their import graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

from protocol.schema import Message


def append(msg: Message, log_path: Path, *, embed: bool = False) -> None:
    """Append ``msg`` to the JSONL log at ``log_path``.

    Creates the parent directory if missing. Uses ``"ab"`` mode so
    concurrent writers get POSIX ``O_APPEND`` semantics on this platform.

    When ``embed=True`` the message is also embedded and upserted into
    Qdrant so that ``search`` finds it immediately. The embed step is
    best-effort — if Qdrant is unreachable the write to the hot log
    still succeeds and a warning is printed to stderr. Long-lived
    processes (MCP server) cache the model and client at module level
    so the per-message overhead is ~30ms after the first call; the
    first call pays a one-time ~3-5 second model load.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = msg.model_dump_json() + "\n"
    with open(log_path, "ab") as f:
        f.write(line.encode("utf-8"))

    if not embed:
        return
    # Lazy import — callers that don't want embed don't pay the
    # mem0 + sentence-transformers import cost.
    try:
        from phase0.mem0_store import store

        store(msg)
    except Exception as exc:  # noqa: BLE001
        print(
            f"warning: append succeeded but Mem0 store failed: {exc}",
            file=sys.stderr,
        )
