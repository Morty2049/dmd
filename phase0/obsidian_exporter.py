# PHASE0: this file is throwaway — replaced in Phase 2 by an async
# embedder that double-writes to Qdrant and Obsidian. See ADR-0003 and
# ADR-0005.
"""Materialize the JSONL log into an Obsidian vault.

For each :class:`Message` we write ``vault/msg_<id>.md`` with YAML
frontmatter (``id``, ``ts``, ``author``, ``model``, ``role``, ``tags``,
``confidence``, ``token_cost``, ``protocol_version``) and a body that
contains the message text followed by an Obsidian wikilink
(``[[msg_<reply_to>]]``) to the parent. Open the vault in Obsidian and
the Graph view renders the reasoning graph for free.

Export is idempotent: the same log always produces identical files,
so running export repeatedly is safe and stable for diffs.
"""

from __future__ import annotations

from pathlib import Path

from phase0.reader import read_all
from protocol.schema import Message


def _escape_yaml(value: str) -> str:
    # Minimal YAML escaping for single-line string values.
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_frontmatter(msg: Message) -> list[str]:
    model_yaml = "null" if msg.model is None else f'"{_escape_yaml(msg.model)}"'
    lines = [
        "---",
        f'id: "{msg.id}"',
        f"ts: {msg.ts.isoformat()}",
        f'author: "{_escape_yaml(msg.author)}"',
        f"model: {model_yaml}",
        f"role: {msg.role.value}",
    ]
    if msg.reply_to is not None:
        lines.append(f'reply_to: "{msg.reply_to}"')
    if msg.tags:
        tags_csv = ", ".join(f'"{_escape_yaml(t)}"' for t in msg.tags)
        lines.append(f"tags: [{tags_csv}]")
    if msg.confidence is not None:
        lines.append(f"confidence: {msg.confidence}")
    if msg.token_cost is not None:
        lines.append(
            f"token_cost: {{ input: {msg.token_cost.input}, "
            f"output: {msg.token_cost.output}, "
            f'model: "{_escape_yaml(msg.token_cost.model)}" }}'
        )
    lines.append(f'protocol_version: "{msg.protocol_version}"')
    lines.append("---")
    return lines


def _render(msg: Message) -> str:
    parts = _render_frontmatter(msg)
    parts.append("")
    parts.append(msg.text.strip())
    parts.append("")
    if msg.reply_to is not None:
        parts.append(f"↩ Replies to: [[msg_{msg.reply_to}]]")
    return "\n".join(parts) + "\n"


def export(log_path: Path, vault_path: Path) -> int:
    """Rebuild the Obsidian vault from the JSONL log.

    Returns the number of message files written. Creates the vault
    directory if it does not exist. Does not delete stale files from
    previous exports — that is a separate concern for a later commit.
    """
    messages = read_all(log_path)
    vault_path.mkdir(parents=True, exist_ok=True)
    for msg in messages:
        out = vault_path / f"msg_{msg.id}.md"
        out.write_text(_render(msg), encoding="utf-8")
    return len(messages)
