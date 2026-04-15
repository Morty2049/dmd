# PHASE0: this file is throwaway — replaced in Phase 2 by a NATS JetStream
# durable consumer + ClickHouse SELECT. See ADR-0003 and ADR-0005.
"""Read Messages from the Phase 0 JSONL log.

Supports two modes:

- **Batch read** — parse the whole file into a list of Messages, drop
  duplicates by id.
- **Tail** — open in append-aware mode and yield new lines as they land
  (the local stand-in for a durable consumer cursor).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from protocol.schema import Message


def read_all(log_path: Path) -> list[Message]:
    """Parse the entire log file, deduplicating on ``Message.id``."""
    raise NotImplementedError("phase0.reader.read_all: scheduled for next commit")


def tail(log_path: Path, *, from_offset: int = 0) -> Iterator[Message]:
    """Yield messages from ``from_offset`` onward, following new appends."""
    raise NotImplementedError("phase0.reader.tail: scheduled for next commit")
