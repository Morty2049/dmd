"""End-to-end tests for the Phase 0 pipeline.

Covers: append → read_all (with dedup), search, Obsidian export
(idempotent + wikilinks present), mention extraction, tail offsets.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from phase0.appender import append
from phase0.mention_router import extract_mentions
from phase0.obsidian_exporter import export
from phase0.reader import read_all, tail
from phase0.search import search
from protocol.roles import Role
from protocol.schema import Message, TokenCost


def _ts(minute: int) -> datetime:
    return datetime(2026, 4, 15, 10, minute, 0, tzinfo=UTC) + timedelta(seconds=minute)


def test_append_then_read_all_returns_messages_sorted_by_ts(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    m1 = Message.create(author="a", role=Role.QUESTION, text="first", ts=_ts(1))
    m2 = Message.create(author="a", role=Role.ANSWER, text="second", ts=_ts(2))
    append(m2, log)  # intentionally out of order
    append(m1, log)
    messages = read_all(log)
    assert [m.id for m in messages] == [m1.id, m2.id]


def test_duplicate_appends_are_deduplicated_on_read(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    msg = Message.create(author="a", role=Role.QUESTION, text="hello", ts=_ts(1))
    for _ in range(3):
        append(msg, log)
    messages = read_all(log)
    assert len(messages) == 1
    assert messages[0].id == msg.id


def test_search_finds_relevant_messages(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    msgs = [
        Message.create(
            author="a", role=Role.ANSWER, text="OAuth refresh tokens", ts=_ts(1)
        ),
        Message.create(
            author="b", role=Role.ANSWER, text="ClickHouse partitions", ts=_ts(2)
        ),
        Message.create(
            author="c", role=Role.ANSWER, text="Refresh the OAuth flow", ts=_ts(3)
        ),
    ]
    for m in msgs:
        append(m, log)
    # Tests exercise the substring fallback path — semantic path is
    # covered by a live dogfood test against the real Qdrant index,
    # not pytest, because it requires an embedder model + running
    # service we do not spin up in unit tests.
    hits = search("oauth refresh", log, top_k=5, mode="substring")
    assert len(hits) == 2
    assert {m.author for m in hits} == {"a", "c"}


def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    append(Message.create(author="a", role=Role.QUESTION, text="x", ts=_ts(1)), log)
    assert search("   ", log, mode="substring") == []


def test_export_creates_one_file_per_message_with_wikilinks(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    vault = tmp_path / "vault"
    root = Message.create(
        author="a", role=Role.QUESTION, text="root?", ts=_ts(1), tags=["x"]
    )
    child = Message.create(
        author="b",
        role=Role.ANSWER,
        text="child!",
        ts=_ts(2),
        reply_to=root.id,
        model="claude-opus-4-6",
        token_cost=TokenCost(input=10, output=5, model="claude-opus-4-6"),
    )
    append(root, log)
    append(child, log)
    written = export(log, vault)
    assert written == 2
    root_md = (vault / f"msg_{root.id}.md").read_text(encoding="utf-8")
    child_md = (vault / f"msg_{child.id}.md").read_text(encoding="utf-8")
    assert f'id: "{root.id}"' in root_md
    assert "role: question" in root_md
    assert f"[[msg_{root.id}]]" in child_md
    assert "role: answer" in child_md
    # Rigid frontmatter: every key present, nulls written explicitly.
    for key in (
        "id",
        "ts",
        "author",
        "model",
        "role",
        "reply_to",
        "tags",
        "text_len",
        "chain_of_thought_len",
        "confidence",
        "token_cost_input",
        "token_cost_output",
        "token_cost_model",
        "protocol_version",
    ):
        assert f"{key}:" in root_md, f"missing key in root: {key}"
        assert f"{key}:" in child_md, f"missing key in child: {key}"
    # Root has no token_cost → all three flattened fields are null.
    assert "token_cost_input: null" in root_md
    assert "token_cost_model: null" in root_md
    # Child has token_cost → flattened with numeric values.
    assert "token_cost_input: 10" in child_md
    assert "token_cost_output: 5" in child_md
    assert 'token_cost_model: "claude-opus-4-6"' in child_md


def test_export_is_idempotent(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    vault = tmp_path / "vault"
    m = Message.create(author="a", role=Role.QUESTION, text="hi", ts=_ts(1))
    append(m, log)
    export(log, vault)
    first = (vault / f"msg_{m.id}.md").read_text(encoding="utf-8")
    export(log, vault)
    second = (vault / f"msg_{m.id}.md").read_text(encoding="utf-8")
    assert first == second


def test_mention_extraction_preserves_order_and_dedupes() -> None:
    msg = Message.create(
        author="morty",
        role=Role.QUESTION,
        text="Hey @claude_opus and @gemini — also @claude_opus again please",
        ts=_ts(1),
    )
    assert extract_mentions(msg) == ["claude_opus", "gemini"]


def test_tail_returns_advanced_offset_and_new_messages(tmp_path: Path) -> None:
    log = tmp_path / "swarm.jsonl"
    m1 = Message.create(author="a", role=Role.QUESTION, text="one", ts=_ts(1))
    append(m1, log)
    batch1, offset1 = tail(log, from_offset=0)
    assert [m.id for m in batch1] == [m1.id]
    m2 = Message.create(author="a", role=Role.ANSWER, text="two", ts=_ts(2))
    append(m2, log)
    batch2, offset2 = tail(log, from_offset=offset1)
    assert [m.id for m in batch2] == [m2.id]
    assert offset2 > offset1


def test_read_all_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_all(tmp_path / "nope.jsonl") == []
