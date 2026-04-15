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
"""

from __future__ import annotations

from pathlib import Path

from protocol.schema import Message


def append(msg: Message, log_path: Path) -> None:
    """Append ``msg`` to the JSONL log at ``log_path``.

    Creates the parent directory if missing. Uses ``"ab"`` mode so
    concurrent writers get POSIX ``O_APPEND`` semantics on this platform.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = msg.model_dump_json() + "\n"
    with open(log_path, "ab") as f:
        f.write(line.encode("utf-8"))
