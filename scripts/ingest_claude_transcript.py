"""Map a native Claude Code transcript JSONL into dmd Messages.

See ADR-0008 for the full specification of the input format and the
mapping rules. This script is a pure data transformation — no prompts,
no LLM-in-the-loop. Given a transcript file on disk, it produces a
deterministic sequence of :class:`Message` records and appends them to
the swarm log. Idempotent thanks to content-hashed message ids.

Usage::

    .venv/bin/python scripts/ingest_claude_transcript.py \\
        ~/.claude/projects/<slug>/<session-uuid>.jsonl \\
        --surface app

    # or for the parallel Antigravity session:
    .venv/bin/python scripts/ingest_claude_transcript.py \\
        ~/.claude/projects/<slug>/<other-session>.jsonl \\
        --surface antigravity

    # bulk — one session per file:
    for f in ~/.claude/projects/<slug>/*.jsonl; do
        .venv/bin/python scripts/ingest_claude_transcript.py "$f"
    done

If ``--surface`` is omitted the script reads the transcript's
``entrypoint`` field and picks the matching handle from ADR-0007.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from phase0.appender import append
from phase0.obsidian_exporter import export
from phase0.paths import default_log_path, default_vault_path
from protocol.roles import Role
from protocol.schema import Message, TokenCost

DEFAULT_LOG = default_log_path()
DEFAULT_VAULT = default_vault_path()

# Text-block prefixes that indicate injected context rather than real
# user input. If a user text block starts with any of these, we drop
# the block. A user turn with no remaining text blocks is skipped
# entirely.
INJECTED_PREFIXES = (
    "<ide_opened_file>",
    "<ide_selection>",
    "<ide_diagnostics>",
    "<system-reminder>",
    "<local-command-caveat>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<user-prompt-submit-hook>",
    "<create-pr-command>",
)

# entrypoint → (author handle, surface slug for tags)
ENTRYPOINT_TO_AUTHOR: dict[str, tuple[str, str]] = {
    "claude-desktop": ("claude_opus_app", "app"),
    "claude-vscode": ("claude_opus_antigravity", "antigravity"),
    "claude-cli": ("claude_opus_cli", "cli"),
    "claude-code": ("claude_opus_cli", "cli"),
}


def _strip_injected(text: str) -> str:
    """Remove injected context blocks; return the cleaned text.

    Any leading fragment that matches a known injected prefix up to
    its matching closing tag is removed. If the whole block is
    injected context, returns the empty string.
    """
    cleaned = text
    # Strip all occurrences of <tag>...</tag> where tag is in the
    # known injected list. Non-greedy, multiline.
    for prefix in INJECTED_PREFIXES:
        tag = prefix[1:-1]  # "<foo>" → "foo"
        cleaned = re.sub(
            rf"<{re.escape(tag)}>.*?</{re.escape(tag)}>",
            "",
            cleaned,
            flags=re.DOTALL,
        )
    return cleaned.strip()


def _extract_text_blocks(content: Any) -> list[str]:
    """Return the list of ``text`` block strings from a content value.

    The transcript's ``message.content`` is either a bare string (older
    format / simple messages) or a list of typed blocks. We collect
    the text across both shapes.
    """
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text:
                    out.append(text)
        return out
    return []


def _extract_thinking(content: Any) -> str | None:
    """Join all ``thinking`` blocks into one string; ``None`` if empty."""
    if not isinstance(content, list):
        return None
    chunks: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "thinking":
            text = block.get("thinking")
            if isinstance(text, str) and text:
                chunks.append(text)
    if not chunks:
        return None
    return "\n\n".join(chunks)


def _extract_tool_trace(content: Any) -> str | None:
    """Produce a compact ``[tools: Bash, Write, Read×3]`` trailer."""
    if not isinstance(content, list):
        return None
    counts: Counter[str] = Counter()
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            name = block.get("name")
            if isinstance(name, str):
                counts[name] += 1
    if not counts:
        return None
    parts = [f"{n}×{c}" if c > 1 else n for n, c in sorted(counts.items())]
    return f"[tools: {', '.join(parts)}]"


def _resolve_surface(arg_surface: str | None, entrypoint: str | None) -> tuple[str, str]:
    """Return (author_handle, surface_slug) for this session."""
    if arg_surface is not None:
        slug = arg_surface
        author = {
            "app": "claude_opus_app",
            "antigravity": "claude_opus_antigravity",
            "cli": "claude_opus_cli",
        }.get(slug, f"claude_opus_{slug}")
        return (author, slug)
    if entrypoint and entrypoint in ENTRYPOINT_TO_AUTHOR:
        return ENTRYPOINT_TO_AUTHOR[entrypoint]
    return ("claude_opus_unknown", "unknown")


def _parse_ts(raw: str) -> datetime:
    # Accept trailing Z
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return datetime.fromisoformat(raw)


def ingest(
    jsonl_path: Path,
    *,
    log_path: Path,
    surface_override: str | None = None,
    user_author: str = "morty",
    dry_run: bool = False,
) -> list[Message]:
    """Parse ``jsonl_path`` and append mapped Messages to ``log_path``.

    Returns the list of Messages that were (or would be) appended.
    """
    lines: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            lines.append(json.loads(raw))

    if not lines:
        return []

    # Discover surface from the first line that has `entrypoint`.
    entrypoint: str | None = None
    for ln in lines:
        ep = ln.get("entrypoint")
        if isinstance(ep, str):
            entrypoint = ep
            break
    agent_author, surface_slug = _resolve_surface(surface_override, entrypoint)

    # Session short id for tagging.
    session_id = lines[0].get("sessionId") or jsonl_path.stem
    session_tag_full = f"session:{session_id[:8]}"

    # Map transcript_uuid → dmd_id for parent resolution.
    uuid_to_dmd: dict[str, str] = {}
    produced: list[Message] = []

    for ln in lines:
        kind = ln.get("type")
        if kind not in ("user", "assistant"):
            continue
        if ln.get("isSidechain"):
            continue

        uuid = ln.get("uuid")
        parent_uuid = ln.get("parentUuid")
        ts_raw = ln.get("timestamp")
        if not isinstance(uuid, str) or not isinstance(ts_raw, str):
            continue

        message = ln.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        ts = _parse_ts(ts_raw)

        reply_to = uuid_to_dmd.get(parent_uuid) if isinstance(parent_uuid, str) else None
        base_tags = [
            "dmd:self",
            "transcript",
            f"surface:{surface_slug}",
            session_tag_full,
        ]

        if kind == "user":
            raw_blocks = _extract_text_blocks(content)
            cleaned_blocks = [
                cleaned for b in raw_blocks if (cleaned := _strip_injected(b))
            ]
            if not cleaned_blocks:
                continue
            text = "\n\n".join(cleaned_blocks)
            msg = Message.create(
                author=user_author,
                role=Role.QUESTION,
                text=text,
                ts=ts,
                reply_to=reply_to,
                tags=base_tags,
            )
        else:
            text_parts = _extract_text_blocks(content)
            text_joined = "\n\n".join(text_parts).strip()
            thinking = _extract_thinking(content)
            tool_trace = _extract_tool_trace(content)

            # Role rule from ADR-0008: only tool_use → REFLECTION (inner
            # action); any text → ANSWER.
            if text_joined:
                role = Role.ANSWER
            elif tool_trace or thinking:
                role = Role.REFLECTION
            else:
                continue

            # Build the body. If there was no user-visible text but
            # there were tool calls or thinking, surface a brief
            # placeholder so downstream readers can tell something
            # happened without cracking open the frontmatter.
            body_parts: list[str] = []
            if text_joined:
                body_parts.append(text_joined)
            else:
                body_parts.append("_(no visible text — inner action only)_")
            if tool_trace:
                body_parts.append(tool_trace)
            body = "\n\n".join(body_parts)

            usage = message.get("usage") or {}
            model = message.get("model")
            token_cost: TokenCost | None = None
            if isinstance(usage, dict) and isinstance(model, str):
                input_tokens = sum(
                    int(usage.get(k, 0) or 0)
                    for k in (
                        "input_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                    )
                )
                output_tokens = int(usage.get("output_tokens", 0) or 0)
                token_cost = TokenCost(
                    input=input_tokens,
                    output=output_tokens,
                    model=model,
                )

            msg = Message.create(
                author=agent_author,
                role=role,
                text=body,
                ts=ts,
                model=model if isinstance(model, str) else None,
                reply_to=reply_to,
                tags=base_tags,
                token_cost=token_cost,
                chain_of_thought=thinking,
            )

        uuid_to_dmd[uuid] = msg.id
        produced.append(msg)

    if not dry_run:
        for msg in produced:
            append(msg, log_path)

    return produced


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ingest_claude_transcript",
        description="Map a Claude transcript JSONL into dmd Messages (ADR-0008).",
    )
    p.add_argument("path", type=Path, help="Path to the transcript JSONL file.")
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    p.add_argument("--surface", choices=["app", "antigravity", "cli"], default=None)
    p.add_argument("--user-author", default="morty")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--export", action="store_true")
    p.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    args = p.parse_args(argv)

    produced = ingest(
        args.path,
        log_path=args.log,
        surface_override=args.surface,
        user_author=args.user_author,
        dry_run=args.dry_run,
    )
    print(
        f"{'would append' if args.dry_run else 'appended'} "
        f"{len(produced)} message(s) from {args.path.name}",
        file=sys.stderr,
    )
    if args.export and not args.dry_run:
        count = export(args.log, args.vault)
        print(f"exported {count} file(s) → {args.vault}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
