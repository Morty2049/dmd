"""Tests for the dmd message protocol (``protocol/schema.py``).

These tests pin the *contract*: idempotent id derivation, append-only
enforcement via frozen models, and JSON round-trip stability. The
protocol is the one thing in dmd that must survive all phases, so its
tests are the tightest in the repo.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from protocol.roles import Role
from protocol.schema import ID_LENGTH, PROTOCOL_VERSION, Message, TokenCost


def _fixed_ts() -> datetime:
    return datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)


def test_id_is_deterministic_for_same_inputs() -> None:
    ts = _fixed_ts()
    a = Message.create(author="alice", role=Role.QUESTION, text="hello", ts=ts)
    b = Message.create(author="alice", role=Role.QUESTION, text="hello", ts=ts)
    assert a.id == b.id
    assert len(a.id) == ID_LENGTH


def test_id_differs_when_any_key_input_changes() -> None:
    ts = _fixed_ts()
    base = Message.create(author="alice", role=Role.QUESTION, text="hello", ts=ts)
    assert (
        Message.create(author="bob", role=Role.QUESTION, text="hello", ts=ts).id
        != base.id
    )
    assert (
        Message.create(author="alice", role=Role.QUESTION, text="world", ts=ts).id
        != base.id
    )
    other_ts = _fixed_ts().replace(minute=1)
    assert (
        Message.create(author="alice", role=Role.QUESTION, text="hello", ts=other_ts).id
        != base.id
    )


def test_message_is_frozen_append_only_enforced_at_type_level() -> None:
    msg = Message.create(author="alice", role=Role.QUESTION, text="hi", ts=_fixed_ts())
    with pytest.raises(ValidationError):
        msg.text = "edited"  # type: ignore[misc]


def test_json_roundtrip_preserves_all_fields() -> None:
    original = Message.create(
        author="claude_opus",
        role=Role.ANSWER,
        text="Route through auth-svc.",
        ts=_fixed_ts(),
        model="claude-opus-4-6",
        reply_to="a" * ID_LENGTH,
        tags=["auth", "architecture"],
        confidence=0.87,
        token_cost=TokenCost(input=420, output=180, model="claude-opus-4-6"),
    )
    serialized = original.model_dump_json()
    revived = Message.model_validate_json(serialized)
    assert revived == original
    assert revived.protocol_version == PROTOCOL_VERSION


def test_token_cost_required_components_validate() -> None:
    with pytest.raises(ValidationError):
        TokenCost(input=-1, output=0, model="x")  # negative tokens rejected
    cost = TokenCost(input=100, output=50, model="claude-opus-4-6")
    assert cost.input == 100


def test_confidence_bounds() -> None:
    ts = _fixed_ts()
    with pytest.raises(ValidationError):
        Message.create(
            author="alice",
            role=Role.ANSWER,
            text="hi",
            ts=ts,
            confidence=1.5,
        )
