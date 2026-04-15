# dmd vault

This directory is an Obsidian vault. Open it with **File → Open Vault**
and Obsidian will render the reasoning graph for the Phase 0 log.

The vault is **generated** by `phase0/obsidian_exporter.py` from
`data/swarm.jsonl`. Treat the `.md` files inside as a build artifact,
not as the source of truth — edits here will be overwritten on the next
export.

The graph edges come from `reply_to` → `[[msg_<id>]]` wikilinks in the
exported message files. Open the Graph view in Obsidian to see the
swarm's collective reasoning.

> This file and `.gitkeep` exist so the vault directory survives a
> clean checkout. Exported message files (`msg_*.md`) will appear once
> the exporter is wired up in the next commit.
