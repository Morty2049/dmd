# PHASE0: this file is throwaway — replaced in Phase 2 by an async
# embedder that double-writes to Qdrant and Obsidian. See ADR-0003 and
# ADR-0005.
"""Materialize the JSONL log into an Obsidian vault.

Every exported ``.md`` file has an **identical frontmatter schema** —
the same keys appear in the same order on every message, even when the
underlying field is null or empty. This rigid shape is required so
Obsidian's Dataview / Templater / filter queries can rely on a stable
set of properties across the whole vault. Conditional frontmatter
breaks "find all messages where confidence < 0.5" at the UI level.

The nested ``token_cost`` object is deliberately flattened into three
top-level fields (``token_cost_input`` / ``token_cost_output`` /
``token_cost_model``) so Dataview can aggregate costs without parsing
inline YAML objects.

Export is idempotent: the same log always produces identical files,
so running export repeatedly is safe and stable for diffs.
"""

from __future__ import annotations

from pathlib import Path

from phase0.reader import read_all
from protocol.schema import Message

# Fixed frontmatter key order — never change this without a protocol
# version bump. Obsidian queries are cheap to write but expensive to
# migrate.
FRONTMATTER_KEYS = (
    "id",
    "ts",
    "author",
    "model",
    "role",
    "reply_to",
    "tags",
    "text_len",
    "confidence",
    "token_cost_input",
    "token_cost_output",
    "token_cost_model",
    "protocol_version",
)


def _escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _yaml_str(value: str | None) -> str:
    if value is None:
        return "null"
    return f'"{_escape_yaml(value)}"'


def _yaml_tags(tags: list[str]) -> str:
    if not tags:
        return "[]"
    return "[" + ", ".join(f'"{_escape_yaml(t)}"' for t in tags) + "]"


def _render_frontmatter(msg: Message) -> list[str]:
    cost = msg.token_cost
    values: dict[str, str] = {
        "id": f'"{msg.id}"',
        "ts": msg.ts.isoformat(),
        "author": _yaml_str(msg.author),
        "model": _yaml_str(msg.model),
        "role": msg.role.value,
        "reply_to": _yaml_str(msg.reply_to),
        "tags": _yaml_tags(msg.tags),
        "text_len": str(len(msg.text)),
        "confidence": "null" if msg.confidence is None else f"{msg.confidence}",
        "token_cost_input": "null" if cost is None else str(cost.input),
        "token_cost_output": "null" if cost is None else str(cost.output),
        "token_cost_model": _yaml_str(None if cost is None else cost.model),
        "protocol_version": f'"{msg.protocol_version}"',
    }
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        lines.append(f"{key}: {values[key]}")
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
