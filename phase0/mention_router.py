# PHASE0: this file is throwaway — replaced in Phase 2 by a FastAPI
# gateway + semantic-proximity router publishing to NATS. See ADR-0003.
"""Parse ``@mention`` handles out of a message.

Phase 0 is purely textual — we scan :attr:`Message.text` for tokens
matching ``@[A-Za-z0-9_]+`` and return them in order of first
occurrence. Phase 2 will add semantic-proximity routing at the gateway
so that an agent wakes up even without an explicit mention when the
message is close enough to its current context.

Group expansion (``@payments`` → individual agent ids) is out of scope
here: the agent directory itself is a Phase 2 concern documented as an
open question in ADR-0003.
"""

from __future__ import annotations

import re

from protocol.schema import Message

_MENTION_RE = re.compile(r"@([A-Za-z0-9_]+)")


def extract_mentions(msg: Message) -> list[str]:
    """Return the list of handles mentioned in ``msg.text``.

    Preserves first-occurrence order and deduplicates within a single
    message (``@alice ... @alice`` → ``["alice"]``).
    """
    seen: set[str] = set()
    result: list[str] = []
    for match in _MENTION_RE.finditer(msg.text):
        handle = match.group(1)
        if handle not in seen:
            seen.add(handle)
            result.append(handle)
    return result
