"""dmd message schema v0.1.

A ``Message`` is immutable and idempotent by construction: the ``id`` is a
deterministic hash of ``(author, ts, text)``, so the same inputs always
produce the same id. Replaying an append is therefore safe — storage
layers can reject duplicates on a unique-index without the client having
to track state.

The model is frozen (``ConfigDict(frozen=True)``) to enforce the
append-only doctrine at the Python type level: once constructed, a
Message cannot be mutated. Corrections are new messages that reference
the original via ``reply_to``.

See ADR-0002 for field-by-field rationale.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from protocol.roles import Role

PROTOCOL_VERSION = "0.1"
ID_LENGTH = 16  # hex chars of the sha256 prefix used as the message id


class TokenCost(BaseModel):
    """Tokens spent producing a single message.

    Required on every non-human message so the swarm can compute its own
    operating cost, rank cheap-but-good solutions, and detect runaway
    agents. Human messages set this to ``None``.
    """

    model_config = ConfigDict(frozen=True)

    input: int = Field(ge=0, description="Input (prompt) tokens consumed.")
    output: int = Field(ge=0, description="Output (completion) tokens produced.")
    model: str = Field(
        description="Model identifier used for billing — may differ from "
        "``Message.model`` if routed through a gateway."
    )


class Message(BaseModel):
    """A single append-only entry in the swarm log."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        min_length=ID_LENGTH,
        max_length=ID_LENGTH,
        description="sha256(author|ts_iso|text)[:16]. Deterministic — replays are idempotent.",
    )
    ts: datetime = Field(description="UTC timestamp; ms precision recommended.")
    author: str = Field(min_length=1, description="Agent id or human handle.")
    model: str | None = Field(
        default=None,
        description="Model identifier, e.g. ``claude-opus-4-6``. ``None`` for humans.",
    )
    role: Role = Field(description="Type of thought-act this message performs.")
    reply_to: str | None = Field(
        default=None,
        description="Parent message id — drives the reasoning graph edges.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Routing and filtering hints; used by the mention router and semantic filter.",
    )
    text: str = Field(min_length=1, description="Message body. Markdown permitted.")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Author's self-rated confidence in this message (0-1).",
    )
    token_cost: TokenCost | None = Field(
        default=None,
        description="Tokens consumed producing this message. ``None`` for human authors.",
    )
    protocol_version: Literal["0.1"] = Field(
        default=PROTOCOL_VERSION,
        description="Schema version. Bump via ADR; never edit messages in place.",
    )

    @classmethod
    def create(
        cls,
        *,
        author: str,
        role: Role,
        text: str,
        ts: datetime | None = None,
        model: str | None = None,
        reply_to: str | None = None,
        tags: list[str] | None = None,
        confidence: float | None = None,
        token_cost: TokenCost | None = None,
    ) -> Message:
        """Build a Message with a deterministic id.

        Two calls with identical ``(author, ts, text)`` produce identical
        ids — this is the idempotency guarantee the storage layer relies
        on for safe replay.
        """
        resolved_ts = ts if ts is not None else datetime.now(tz=UTC)
        msg_id = _compute_id(author=author, ts=resolved_ts, text=text)
        return cls(
            id=msg_id,
            ts=resolved_ts,
            author=author,
            model=model,
            role=role,
            reply_to=reply_to,
            tags=list(tags) if tags else [],
            text=text,
            confidence=confidence,
            token_cost=token_cost,
        )


def _compute_id(*, author: str, ts: datetime, text: str) -> str:
    payload = f"{author}|{ts.isoformat()}|{text}".encode()
    return hashlib.sha256(payload).hexdigest()[:ID_LENGTH]
