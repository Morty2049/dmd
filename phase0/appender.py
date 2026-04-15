# PHASE0: this file is throwaway — replaced in Phase 2 by a NATS JetStream
# publisher + ClickHouse batch writer. See ADR-0003 and ADR-0005.
"""Append a Message to the Phase 0 JSONL log.

Will open ``data/swarm.jsonl`` in ``O_APPEND`` mode, serialize the
message with ``Message.model_dump_json()``, and write a single newline-
terminated line. Idempotency is handled upstream by the deterministic
``Message.id`` — duplicate appends of the same id are dropped on read.
"""

from __future__ import annotations

from pathlib import Path

from protocol.schema import Message


def append(msg: Message, log_path: Path) -> None:
    """Append ``msg`` to the JSONL log at ``log_path``.

    Raises ``NotImplementedError`` until the next commit implements the
    actual write path.
    """
    raise NotImplementedError("phase0.appender.append: scheduled for next commit")
