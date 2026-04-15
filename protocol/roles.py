"""Message roles — the *type* of a thought-act, not just a chat role.

The ``role`` field is the signature feature of the dmd protocol: it lets
the swarm reason about the *kind* of cognitive move a message represents,
not merely that it was said. See ADR-0002 for rationale.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """The type of thought-act a message performs."""

    QUESTION = "question"
    """A request for information, analysis, or a decision."""

    ANSWER = "answer"
    """A direct response to a ``QUESTION``."""

    CORRECTION = "correction"
    """A message that contradicts or amends an earlier one via ``reply_to``.

    Append-only doctrine: we never edit the original — we append a
    correction that points at it.
    """

    REFLECTION = "reflection"
    """Commentary on another message without amending it.

    Useful for ``"I notice this relates to..."`` or meta-observations that
    should be indexed but do not change the truth value of the target.
    """

    MENTION = "mention"
    """Explicit routing of a target agent or group into a conversation.

    Produced by the mention router when it rewrites ``@agent`` / ``@group``
    in human-authored text into first-class protocol events.
    """

    SYSTEM = "system"
    """Infrastructure messages (agent joined, consumer rebalanced, etc.).

    These are protocol-level, not semantic content.
    """
