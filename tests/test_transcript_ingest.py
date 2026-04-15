"""Tests for scripts/ingest_claude_transcript.py.

Uses small synthetic JSONL fixtures that mirror the real Claude Code
transcript schema documented in ADR-0008 — one "user" turn with
injected IDE context, one "assistant" turn with thinking + text +
tool_use blocks, one user reply. Asserts the mapper produces the
expected Messages with correct reply_to chaining, CoT extraction,
injected-content stripping, and tool-trace appending.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# scripts/ is not an importable package; add it to sys.path for tests.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from ingest_claude_transcript import ingest  # noqa: E402

from protocol.roles import Role  # noqa: E402


def _write_fixture(path: Path, lines: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )


def _turn(
    uuid: str,
    parent: str | None,
    ts: str,
    kind: str,
    content: list[dict] | str,
    **extra: object,
) -> dict:
    line: dict = {
        "type": kind,
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": ts,
        "sessionId": "testsession",
        "isSidechain": False,
        "entrypoint": "claude-desktop",
        "message": {"role": kind, "content": content, **extra},
    }
    return line


def test_user_injected_context_is_stripped(tmp_path: Path) -> None:
    fixture = tmp_path / "t.jsonl"
    _write_fixture(
        fixture,
        [
            _turn(
                "u1",
                None,
                "2026-04-15T10:00:00Z",
                "user",
                [
                    {
                        "type": "text",
                        "text": (
                            "<ide_opened_file>file.py</ide_opened_file>\n"
                            "Real user question here."
                        ),
                    }
                ],
            ),
        ],
    )
    msgs = ingest(fixture, log_path=tmp_path / "log.jsonl", dry_run=True)
    assert len(msgs) == 1
    assert msgs[0].role == Role.QUESTION
    assert "Real user question here." in msgs[0].text
    assert "ide_opened_file" not in msgs[0].text


def test_assistant_thinking_becomes_chain_of_thought(tmp_path: Path) -> None:
    fixture = tmp_path / "t.jsonl"
    _write_fixture(
        fixture,
        [
            _turn("u1", None, "2026-04-15T10:00:00Z", "user", "hi"),
            _turn(
                "a1",
                "u1",
                "2026-04-15T10:00:05Z",
                "assistant",
                [
                    {
                        "type": "thinking",
                        "thinking": "Let me consider this carefully.",
                        "signature": "sig",
                    },
                    {"type": "text", "text": "Here is my answer."},
                ],
                model="claude-opus-4-6",
                usage={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            ),
        ],
    )
    msgs = ingest(fixture, log_path=tmp_path / "log.jsonl", dry_run=True)
    assert len(msgs) == 2
    answer = msgs[1]
    assert answer.role == Role.ANSWER
    assert answer.text == "Here is my answer."
    assert answer.chain_of_thought == "Let me consider this carefully."
    assert answer.token_cost is not None
    assert answer.token_cost.input == 10
    assert answer.token_cost.output == 5
    assert answer.reply_to == msgs[0].id


def test_assistant_tool_only_turn_becomes_reflection(tmp_path: Path) -> None:
    fixture = tmp_path / "t.jsonl"
    _write_fixture(
        fixture,
        [
            _turn("u1", None, "2026-04-15T10:00:00Z", "user", "do stuff"),
            _turn(
                "a1",
                "u1",
                "2026-04-15T10:00:01Z",
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "tu1",
                        "name": "Bash",
                        "input": {"command": "ls"},
                        "caller": "me",
                    },
                    {
                        "type": "tool_use",
                        "id": "tu2",
                        "name": "Read",
                        "input": {"file_path": "/x"},
                        "caller": "me",
                    },
                ],
                model="claude-opus-4-6",
                usage={"input_tokens": 1, "output_tokens": 1},
            ),
        ],
    )
    msgs = ingest(fixture, log_path=tmp_path / "log.jsonl", dry_run=True)
    # Only the user and the reflection (no answer yet).
    assistant_msg = next(m for m in msgs if m.role == Role.REFLECTION)
    assert "[tools: Bash, Read]" in assistant_msg.text


def test_reply_to_chain_follows_parent_uuid(tmp_path: Path) -> None:
    fixture = tmp_path / "t.jsonl"
    _write_fixture(
        fixture,
        [
            _turn("u1", None, "2026-04-15T10:00:00Z", "user", "first"),
            _turn(
                "a1",
                "u1",
                "2026-04-15T10:00:01Z",
                "assistant",
                [{"type": "text", "text": "answer1"}],
                model="claude-opus-4-6",
                usage={"input_tokens": 1, "output_tokens": 1},
            ),
            _turn("u2", "a1", "2026-04-15T10:00:02Z", "user", "second"),
            _turn(
                "a2",
                "u2",
                "2026-04-15T10:00:03Z",
                "assistant",
                [{"type": "text", "text": "answer2"}],
                model="claude-opus-4-6",
                usage={"input_tokens": 1, "output_tokens": 1},
            ),
        ],
    )
    msgs = ingest(fixture, log_path=tmp_path / "log.jsonl", dry_run=True)
    assert len(msgs) == 4
    assert msgs[0].reply_to is None
    assert msgs[1].reply_to == msgs[0].id
    assert msgs[2].reply_to == msgs[1].id
    assert msgs[3].reply_to == msgs[2].id


def test_sidechain_messages_are_skipped(tmp_path: Path) -> None:
    fixture = tmp_path / "t.jsonl"
    _write_fixture(
        fixture,
        [
            _turn("u1", None, "2026-04-15T10:00:00Z", "user", "main"),
            {
                "type": "user",
                "uuid": "sc1",
                "parentUuid": None,
                "timestamp": "2026-04-15T10:00:05Z",
                "sessionId": "testsession",
                "isSidechain": True,
                "entrypoint": "claude-desktop",
                "message": {"role": "user", "content": "subagent work"},
            },
        ],
    )
    msgs = ingest(fixture, log_path=tmp_path / "log.jsonl", dry_run=True)
    assert len(msgs) == 1
    assert msgs[0].text == "main"


def test_injected_only_user_turn_is_dropped(tmp_path: Path) -> None:
    fixture = tmp_path / "t.jsonl"
    _write_fixture(
        fixture,
        [
            _turn(
                "u1",
                None,
                "2026-04-15T10:00:00Z",
                "user",
                [
                    {
                        "type": "text",
                        "text": "<system-reminder>just a reminder</system-reminder>",
                    }
                ],
            ),
            _turn("u2", "u1", "2026-04-15T10:00:05Z", "user", "real text"),
        ],
    )
    msgs = ingest(fixture, log_path=tmp_path / "log.jsonl", dry_run=True)
    # The injected-only first user turn is skipped; the second stays.
    # Its parent should resolve to None because u1 never produced a dmd id.
    assert len(msgs) == 1
    assert msgs[0].text == "real text"
    assert msgs[0].reply_to is None
