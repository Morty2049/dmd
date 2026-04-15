"""dmd swarm message protocol.

This package is the CONTRACT between every agent, client, and storage
backend in the dmd system. It survives every phase transition — Phase 0
(local JSONL), Phase 1 (web client), Phase 2 (ClickHouse + NATS JetStream).

Changes to the protocol are decided by ADR and bump ``protocol_version``.
Never edit existing messages; instead publish a new message that references
the old one via ``reply_to``.
"""

from protocol.roles import Role
from protocol.schema import Message, TokenCost

__all__ = ["Message", "Role", "TokenCost"]
