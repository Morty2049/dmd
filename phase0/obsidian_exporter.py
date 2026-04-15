# PHASE0: this file is throwaway — replaced in Phase 2 by an async
# embedder that double-writes to Qdrant and Obsidian. See ADR-0003 and
# ADR-0005.
"""Materialize the JSONL log into an Obsidian vault.

For each Message, write ``vault/msg_<id>.md`` with YAML frontmatter
(id, ts, author, model, role, tags) and body containing the text plus
a ``[[msg_<reply_to>]]`` wikilink. Obsidian's graph view then renders
the reasoning graph for free — no extra tooling needed.

Export is idempotent: existing files are overwritten with identical
content, so the same log always produces the same vault.
"""

from __future__ import annotations

from pathlib import Path


def export(log_path: Path, vault_path: Path) -> int:
    """Rebuild the Obsidian vault from the JSONL log.

    Returns the number of message files written.
    """
    raise NotImplementedError("phase0.obsidian_exporter.export: scheduled for next commit")
