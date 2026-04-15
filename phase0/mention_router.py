# PHASE0: this file is throwaway — replaced in Phase 2 by a FastAPI
# gateway + semantic proximity router publishing to NATS. See ADR-0003.
"""Parse ``@mention`` and ``@group_mention`` tokens out of messages.

Phase 0 behavior is purely textual: scan ``Message.text`` for handles
matching ``@[A-Za-z0-9_]+`` and return them as routing targets. Phase 2
will add semantic proximity routing — if a message is close enough to
an agent's current context, it is routed to that agent even without an
explicit mention.

Phase 0 does not expand groups — the agent directory is a Phase 2
concern (see open questions in ADR-0003).
"""

from __future__ import annotations

from protocol.schema import Message


def extract_mentions(msg: Message) -> list[str]:
    """Return the list of handles mentioned in ``msg.text``."""
    raise NotImplementedError("phase0.mention_router.extract_mentions: scheduled for next commit")
