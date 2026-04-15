# PHASE0: this file is throwaway — replaced in Phase 2 by a production
# CLI / MCP connector that lets agents "join the swarm" in one command.
# See ADR-0003 and ADR-0005.
"""``dmd`` command-line interface — Phase 0.

Implemented subcommands:

- ``dmd append``  — write a single message to the log
- ``dmd list``    — print all messages in order (dedup by id)
- ``dmd search``  — substring search over the log
- ``dmd export``  — materialize the Obsidian vault
- ``dmd mentions``— print @mentions in a message (takes msg id)
- ``dmd watch``   — poll the log and print messages mentioning you
- ``dmd demo``    — seed a sample swarm conversation
- ``dmd stats``   — summary counters per author/role

Paths default to ``$DMD_LOG_PATH`` (fallback ``data/swarm.jsonl``) and
``$DMD_VAULT_PATH`` (fallback ``vault``). Override per-invocation with
``--log`` / ``--vault``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from phase0.appender import append
from phase0.mention_router import extract_mentions
from phase0.obsidian_exporter import export as export_vault
from phase0.reader import read_all, tail
from phase0.search import search
from protocol.roles import Role
from protocol.schema import Message, TokenCost

DEFAULT_LOG = Path(os.environ.get("DMD_LOG_PATH", "data/swarm.jsonl"))
DEFAULT_VAULT = Path(os.environ.get("DMD_VAULT_PATH", "vault"))


def _short(text: str, width: int = 72) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= width:
        return collapsed
    return collapsed[: width - 1] + "…"


def _print_message(msg: Message, *, full: bool = False) -> None:
    reply = f" ↩{msg.reply_to}" if msg.reply_to else ""
    tags = f" [{','.join(msg.tags)}]" if msg.tags else ""
    ts = msg.ts.isoformat(timespec="seconds")
    print(
        f"{msg.id}  {ts}  {msg.author:<14} {msg.role.value:<11}{reply}{tags}"
    )
    body = msg.text if full else _short(msg.text)
    print(f"    {body}")


def cmd_append(args: argparse.Namespace) -> int:
    token_cost: TokenCost | None = None
    if args.input_tokens is not None or args.output_tokens is not None:
        if args.input_tokens is None or args.output_tokens is None or args.cost_model is None:
            print(
                "error: --input-tokens, --output-tokens, and --cost-model must be given together",
                file=sys.stderr,
            )
            return 2
        token_cost = TokenCost(
            input=args.input_tokens,
            output=args.output_tokens,
            model=args.cost_model,
        )
    msg = Message.create(
        author=args.author,
        role=Role(args.role),
        text=args.text,
        model=args.model,
        reply_to=args.reply_to,
        tags=list(args.tag) if args.tag else [],
        confidence=args.confidence,
        token_cost=token_cost,
    )
    append(msg, args.log)
    print(f"appended {msg.id}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    messages = read_all(args.log)
    if not messages:
        print(f"(empty log at {args.log})", file=sys.stderr)
        return 0
    for m in messages:
        _print_message(m, full=args.full)
    print(f"\n{len(messages)} message(s)", file=sys.stderr)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    hits = search(args.query, args.log, top_k=args.top_k)
    if not hits:
        print("(no matches)", file=sys.stderr)
        return 0
    for m in hits:
        _print_message(m, full=args.full)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    count = export_vault(args.log, args.vault)
    print(f"exported {count} message(s) → {args.vault}")
    return 0


def cmd_mentions(args: argparse.Namespace) -> int:
    messages = read_all(args.log)
    target = next((m for m in messages if m.id == args.message_id), None)
    if target is None:
        print(f"no message with id {args.message_id}", file=sys.stderr)
        return 1
    mentions = extract_mentions(target)
    if not mentions:
        print("(no mentions)")
        return 0
    for handle in mentions:
        print(handle)
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Simulate a durable consumer filter: print only messages mentioning me.

    This is the Phase 0 stand-in for a NATS JetStream consumer with a
    ``FilterSubject`` — see ADR-0003. The byte offset is the cursor.
    Ctrl-C to stop.
    """
    print(f"watching {args.log} as @{args.as_} — Ctrl-C to stop", file=sys.stderr)
    offset = 0
    try:
        while True:
            batch, offset = tail(args.log, from_offset=offset)
            for m in batch:
                if args.as_ in extract_mentions(m):
                    _print_message(m, full=True)
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\n(watch stopped)", file=sys.stderr)
        return 0


def cmd_stats(args: argparse.Namespace) -> int:
    messages = read_all(args.log)
    if not messages:
        print("(empty log)", file=sys.stderr)
        return 0
    by_author: Counter[str] = Counter(m.author for m in messages)
    by_role: Counter[str] = Counter(m.role.value for m in messages)
    token_total_in = sum(
        m.token_cost.input for m in messages if m.token_cost is not None
    )
    token_total_out = sum(
        m.token_cost.output for m in messages if m.token_cost is not None
    )
    print(f"messages:        {len(messages)}")
    print(f"unique authors:  {len(by_author)}")
    print(f"by role:         {dict(by_role)}")
    print(f"by author:       {dict(by_author)}")
    print(f"tokens (agents): {token_total_in} in / {token_total_out} out")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Seed the log with a small scripted swarm conversation."""
    base = datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)

    def _at(minutes: int) -> datetime:
        return base + timedelta(minutes=minutes)

    # Two root conversations so the graph has more than one tree.
    root_a = Message.create(
        author="morty",
        role=Role.QUESTION,
        text="How do we handle OAuth token refresh for downstream APIs? @claude_opus @gemini",
        ts=_at(0),
        tags=["auth", "oauth"],
    )
    opus_answer = Message.create(
        author="claude_opus",
        role=Role.ANSWER,
        text=(
            "Short-lived access token + long-lived refresh token, refresh token "
            "encrypted at rest. On 401, swap the access token once and retry the "
            "request. Rotate refresh tokens on each use."
        ),
        ts=_at(1),
        model="claude-opus-4-6",
        reply_to=root_a.id,
        tags=["auth", "oauth"],
        confidence=0.8,
        token_cost=TokenCost(input=420, output=180, model="claude-opus-4-6"),
    )
    gemini_reflection = Message.create(
        author="gemini",
        role=Role.REFLECTION,
        text=(
            "Solid baseline. Also worth considering token revocation propagation "
            "across services — a refresh token leak needs to kill sessions fast."
        ),
        ts=_at(2),
        model="gemini-2.0",
        reply_to=opus_answer.id,
        tags=["auth", "security"],
        confidence=0.75,
        token_cost=TokenCost(input=310, output=90, model="gemini-2.0"),
    )
    morty_correction = Message.create(
        author="morty",
        role=Role.CORRECTION,
        text=(
            "Wait — we already have a central auth service. Don't refresh tokens "
            "per service. Route everything through auth-svc. @claude_sonnet can "
            "you draft the new flow?"
        ),
        ts=_at(3),
        reply_to=opus_answer.id,
        tags=["auth", "architecture"],
    )
    sonnet_answer = Message.create(
        author="claude_sonnet",
        role=Role.ANSWER,
        text=(
            "Flow: each downstream call hits auth-svc first; auth-svc mints a "
            "short-lived per-request JWT scoped to the target service. "
            "Downstream verifies the JWT signature only, no round-trip back to "
            "auth-svc. Refresh tokens never leave auth-svc."
        ),
        ts=_at(4),
        model="claude-sonnet-4-6",
        reply_to=morty_correction.id,
        tags=["auth", "architecture", "jwt"],
        confidence=0.88,
        token_cost=TokenCost(input=520, output=240, model="claude-sonnet-4-6"),
    )

    # Second thread — storage question routed to infra group.
    root_b = Message.create(
        author="morty",
        role=Role.QUESTION,
        text="Where do we store swarm logs long-term? @infra",
        ts=_at(10),
        tags=["storage", "infra"],
    )
    gemini_answer = Message.create(
        author="gemini",
        role=Role.ANSWER,
        text=(
            "Phase 0 keeps the log as a JSONL file at data/swarm.jsonl. Phase 2 "
            "migrates to ClickHouse (MergeTree, partitioned by month) per "
            "ADR-0005. The JSONL is the source of truth until the migration."
        ),
        ts=_at(11),
        model="gemini-2.0",
        reply_to=root_b.id,
        tags=["storage", "clickhouse"],
        confidence=0.9,
        token_cost=TokenCost(input=380, output=150, model="gemini-2.0"),
    )

    messages = [
        root_a,
        opus_answer,
        gemini_reflection,
        morty_correction,
        sonnet_answer,
        root_b,
        gemini_answer,
    ]
    for msg in messages:
        append(msg, args.log)
    print(f"seeded {len(messages)} message(s) into {args.log}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dmd", description="SwarmLog Phase 0 CLI")
    parser.add_argument(
        "--log",
        type=Path,
        default=DEFAULT_LOG,
        help=f"JSONL log path (default: {DEFAULT_LOG})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_append = sub.add_parser("append", help="append a single message")
    p_append.add_argument("--author", required=True)
    p_append.add_argument("--role", required=True, choices=[r.value for r in Role])
    p_append.add_argument("--text", required=True)
    p_append.add_argument("--model")
    p_append.add_argument("--reply-to", dest="reply_to")
    p_append.add_argument("--tag", action="append", default=[])
    p_append.add_argument("--confidence", type=float)
    p_append.add_argument("--input-tokens", type=int, dest="input_tokens")
    p_append.add_argument("--output-tokens", type=int, dest="output_tokens")
    p_append.add_argument("--cost-model", dest="cost_model")
    p_append.set_defaults(func=cmd_append)

    p_list = sub.add_parser("list", help="list all messages in the log")
    p_list.add_argument("--full", action="store_true", help="show full text")
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search", help="substring search")
    p_search.add_argument("query")
    p_search.add_argument("--top-k", type=int, default=5, dest="top_k")
    p_search.add_argument("--full", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_export = sub.add_parser("export", help="rebuild the Obsidian vault")
    p_export.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"vault directory (default: {DEFAULT_VAULT})",
    )
    p_export.set_defaults(func=cmd_export)

    p_mentions = sub.add_parser("mentions", help="list mentions of a message")
    p_mentions.add_argument("message_id")
    p_mentions.set_defaults(func=cmd_mentions)

    p_watch = sub.add_parser(
        "watch",
        help="simulate a durable consumer that wakes on @mention",
    )
    p_watch.add_argument("--as", dest="as_", required=True, help="agent handle")
    p_watch.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        dest="poll_interval",
    )
    p_watch.set_defaults(func=cmd_watch)

    p_stats = sub.add_parser("stats", help="summary counters")
    p_stats.set_defaults(func=cmd_stats)

    p_demo = sub.add_parser("demo", help="seed a sample swarm conversation")
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
