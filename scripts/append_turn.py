"""Auto-append one conversation turn to the swarm log.

Going-forward ingestion helper: after each Claude response, pipe the
user's message and the agent's reply into this script and both land
in ``data/swarm.jsonl`` with correct ``reply_to`` chaining — no
manual id tracking, no copy-paste rituals.

The script finds the most recent message in the log that carries the
target session tag and uses its id as the parent of the user turn.
The user turn then becomes the parent of the agent turn. This keeps
the reasoning tree for a given session as a linear chain by default;
forks are still possible by passing ``--user-reply-to`` explicitly.

Usage:

    .venv/bin/python scripts/append_turn.py \\
        --session "session:dmd-dev" \\
        --user-text "$(cat /tmp/user_turn.txt)" \\
        --agent-text "$(cat /tmp/agent_turn.txt)" \\
        --agent-author claude_opus_app \\
        --agent-model claude-opus-4-6 \\
        --agent-input-tokens 1200 \\
        --agent-output-tokens 800 \\
        [--agent-reasoning "$(cat /tmp/cot.txt)"] \\
        [--export]

Short-option aliases exist for convenience; see ``--help``. Auto-exports
to ``vault/`` at the end when ``--export`` is passed.

Idempotent. Message ids are deterministic on (author, ts, text), so
re-running with the same inputs is a no-op at the reader level. The
``--stamp`` flag (default on) forces a fresh timestamp on every run,
so repeated manual invocations are *not* idempotent — pass
``--no-stamp`` + ``--ts`` if you want replay semantics.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from phase0.appender import append
from phase0.obsidian_exporter import export
from phase0.reader import read_all
from protocol.roles import Role
from protocol.schema import Message, TokenCost

DEFAULT_LOG = Path("data/swarm.jsonl")
DEFAULT_VAULT = Path("vault")


def _latest_in_session(log_path: Path, session_tag: str) -> str | None:
    """Return the id of the newest message carrying ``session_tag``."""
    messages = read_all(log_path)
    candidates = [m for m in messages if session_tag in m.tags]
    if not candidates:
        return None
    candidates.sort(key=lambda m: m.ts, reverse=True)
    return candidates[0].id


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="append_turn",
        description="Append one {user, agent} conversation turn to the dmd log.",
    )
    p.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"JSONL log path (default: {DEFAULT_LOG})",
    )
    p.add_argument(
        "--session",
        required=True,
        help="Session tag, e.g. 'session:dmd-dev'. Used to find the parent.",
    )
    p.add_argument(
        "--user-text",
        required=True,
        help="The user's full message text for this turn.",
    )
    p.add_argument(
        "--agent-text",
        required=True,
        help="The agent's full reply text for this turn.",
    )
    p.add_argument(
        "--user-author",
        default="morty",
        help="Handle for the human (default: morty).",
    )
    p.add_argument(
        "--user-role",
        default="question",
        choices=[r.value for r in Role],
    )
    p.add_argument(
        "--agent-author",
        required=True,
        help="Agent handle, ADR-0007 format (e.g. claude_opus_app).",
    )
    p.add_argument(
        "--agent-role",
        default="answer",
        choices=[r.value for r in Role],
    )
    p.add_argument("--agent-model", help="Model id, e.g. claude-opus-4-6")
    p.add_argument("--agent-reasoning", help="Optional chain-of-thought text.")
    p.add_argument("--agent-input-tokens", type=int)
    p.add_argument("--agent-output-tokens", type=int)
    p.add_argument("--agent-cost-model")
    p.add_argument("--agent-confidence", type=float)
    p.add_argument(
        "--user-reply-to",
        help="Override the auto-detected parent for the user turn.",
    )
    p.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Extra tag applied to BOTH messages. Repeatable.",
    )
    p.add_argument(
        "--ts",
        help="Explicit ISO-8601 timestamp for the user turn. Agent turn "
        "is 1 second later. Omit to use the current UTC time.",
    )
    p.add_argument("--export", action="store_true", help="Re-export vault after append.")
    p.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"Vault directory (default: {DEFAULT_VAULT}).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.ts is not None:
        user_ts = datetime.fromisoformat(args.ts)
        if user_ts.tzinfo is None:
            user_ts = user_ts.replace(tzinfo=UTC)
    else:
        user_ts = datetime.now(tz=UTC)

    parent_id = args.user_reply_to or _latest_in_session(args.log, args.session)

    session_tags = [args.session, *args.tag]

    user_msg = Message.create(
        author=args.user_author,
        role=Role(args.user_role),
        text=args.user_text,
        ts=user_ts,
        reply_to=parent_id,
        tags=session_tags,
    )
    append(user_msg, args.log)

    agent_ts = user_ts.replace(microsecond=min(999_999, user_ts.microsecond + 1000))
    if agent_ts == user_ts:
        # Ensure strict temporal ordering without nanosecond tricks.
        agent_ts = datetime.fromtimestamp(user_ts.timestamp() + 0.001, tz=UTC)

    token_cost: TokenCost | None = None
    if args.agent_input_tokens is not None and args.agent_output_tokens is not None:
        cost_model = args.agent_cost_model or args.agent_model or "unknown"
        token_cost = TokenCost(
            input=args.agent_input_tokens,
            output=args.agent_output_tokens,
            model=cost_model,
        )

    # ADR-0006 is still Proposed — until v0.2 ships the reasoning is
    # carried inside the text body, not as a separate field.
    agent_text = args.agent_text
    if args.agent_reasoning:
        agent_text = (
            f"## Reasoning\n\n{args.agent_reasoning.strip()}\n\n"
            f"## Response\n\n{args.agent_text.strip()}"
        )

    agent_msg = Message.create(
        author=args.agent_author,
        role=Role(args.agent_role),
        text=agent_text,
        ts=agent_ts,
        model=args.agent_model,
        reply_to=user_msg.id,
        tags=session_tags,
        confidence=args.agent_confidence,
        token_cost=token_cost,
    )
    append(agent_msg, args.log)

    print(f"user:  {user_msg.id}", file=sys.stderr)
    print(f"agent: {agent_msg.id}", file=sys.stderr)

    if args.export:
        count = export(args.log, args.vault)
        print(f"exported {count} file(s) → {args.vault}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
