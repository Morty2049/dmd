# PHASE0: this file is throwaway — replaced in Phase 2 by a NATS JetStream
# durable consumer + ClickHouse SELECT. See ADR-0003 and ADR-0005.
"""Read :class:`Message` records from the Phase 0 JSONL log.

Two modes:

- :func:`read_all` — parse the entire file, drop duplicates by
  :attr:`Message.id`, return sorted by timestamp.
- :func:`tail` — iterate over messages starting at a byte offset and
  return the next byte offset alongside the results, so callers can
  cheaply resume where they left off (the Phase 0 stand-in for a
  durable JetStream consumer cursor described in ADR-0003).
"""

from __future__ import annotations

import json
from pathlib import Path

from protocol.schema import Message


def read_all(log_path: Path) -> list[Message]:
    """Parse the entire log file, deduplicating on :attr:`Message.id`.

    Missing file → empty list. Malformed lines raise immediately rather
    than silently dropping data — the append-only log must be
    self-consistent, and silent skips would mask real bugs.
    """
    if not log_path.exists():
        return []
    seen: dict[str, Message] = {}
    with open(log_path, "rb") as f:
        for raw in f:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            data = json.loads(line)
            msg = Message.model_validate(data)
            # First occurrence wins — matches replay semantics.
            if msg.id not in seen:
                seen[msg.id] = msg
    return sorted(seen.values(), key=lambda m: m.ts)


def tail(log_path: Path, *, from_offset: int = 0) -> tuple[list[Message], int]:
    """Read messages from ``from_offset`` onward.

    Returns ``(messages, new_offset)``. Callers persist ``new_offset``
    between calls to implement cursor-like behavior. In Phase 2 this is
    replaced by a JetStream durable consumer — the API shape here
    mirrors that contract so the agent-side code can migrate cleanly.
    """
    if not log_path.exists():
        return ([], from_offset)
    messages: list[Message] = []
    with open(log_path, "rb") as f:
        f.seek(from_offset)
        for raw in f:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            messages.append(Message.model_validate(json.loads(line)))
        new_offset = f.tell()
    return (messages, new_offset)
