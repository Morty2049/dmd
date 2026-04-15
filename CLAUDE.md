# Orientation for a new Claude agent joining dmd

You are reading this because a Claude Code session just opened this
repository and `CLAUDE.md` is auto-included in your context. Spend the
next couple of seconds aligning yourself with the project's rules,
then search the vault for whatever the human is actually asking about.

## What this project is

`dmd` (dynamic-markdown) is **collective append-only memory for a
swarm of AI agents**. Every conversation between a human and any
Claude/Gemini session on this codebase is deterministically mapped
into `data/swarm.jsonl` and rendered to `vault/msg_*.md` for Obsidian.
The point: when a new agent joins cold, it should be able to read
history instead of making the human repeat context.

**You are that new agent right now.** The instructions below are how
you make use of what's already there — and how you add to it without
breaking it for whoever joins after you.

## Sacred rules — do not violate

1. **Append-only.** You may not edit or delete messages in
   `data/swarm.jsonl` or files in `vault/`. Corrections are **new**
   messages that reference the original via `reply_to` with
   `role: correction`. See [ADR-0001](docs/adr/0001-append-only-source-of-truth.md).

2. **The protocol is the contract.** `protocol/schema.py` defines
   `Message` v0.2. Do not change fields without writing a new ADR and
   bumping the version. The `chain_of_thought` field was added in
   v0.2 under [ADR-0006](docs/adr/0006-chain-of-thought-field.md); any
   further addition follows the same discipline.

3. **`phase0/` is throwaway, `protocol/` is forever.** Anything under
   `phase0/` is scheduled for deletion at Phase 2. Do not depend on
   `phase0/*` from `protocol/*`. See [ADR-0005](docs/adr/0005-phased-rollout.md).

4. **No `git add -A` / `git add .`.** Stage files by name. The repo
   has a `.gitignore` but foot-guns around `.env` and local data are
   easier to avoid than to clean up.

5. **Do not force-push `main`.** Ever. Previous work lives there.

## Before you answer a question — search the vault

The vault already contains the full history of how this project was
built, including the reasoning that produced every ADR. You almost
certainly do not need to re-derive those decisions. Check first:

```bash
.venv/bin/python -m phase0.cli search "your topic" --top-k 10
# or for a specific author:
.venv/bin/python -m phase0.cli list | grep <author>
```

If you see a relevant `msg_<id>.md`, read it fully before replying.
The message's `chain_of_thought` frontmatter block often contains the
reasoning behind a decision — that's the key feature of the v0.2
protocol, use it.

If the vault has no hit, **then** it's genuinely a new question and
you can think from scratch — and write your answer back so the next
agent benefits.

## Your author handle

Determined by the Claude Code surface you run on, per
[ADR-0007](docs/adr/0007-author-namespace.md):

| Surface                         | Handle                    |
|---------------------------------|---------------------------|
| Native Claude app               | `claude_opus_app`         |
| Antigravity / VS Code extension | `claude_opus_antigravity` |
| CLI (`claude` in a terminal)    | `claude_opus_cli`         |
| Claude Sonnet in hint mode      | `claude_sonnet_hints`     |

If your session is on a surface not listed here, pick
`claude_<model>_<surface>` following the same pattern and write a
one-line note in the next ADR draft.

## Saving your own session to the memory

You do not need to write dmd-protocol JSON by hand. Claude Code
already persists every turn of your session on disk at

```
~/.claude/projects/<slug>/<session-uuid>.jsonl
```

where `<slug>` is the absolute project path with `/` → `-`. Run the
deterministic mapper at the end of your session (or after a hook, if
one is wired up) to ingest the transcript and refresh the vault:

```bash
.venv/bin/python scripts/ingest_claude_transcript.py \
    ~/.claude/projects/-Users-leks-codeRepo-my-projects-dynamic-markdown/<your-session-uuid>.jsonl \
    --export
```

The mapper is idempotent — re-running it on the same file is a no-op
at the reader level. See [ADR-0008](docs/adr/0008-transcript-native-format.md)
for the full mapping spec (which fields are dropped, how thinking
blocks become `chain_of_thought`, how `parentUuid` becomes
`reply_to`).

## Commit discipline

Every non-trivial change earns an ADR. ADRs live in `docs/adr/` and
are themselves append-only — a reversed decision produces a new ADR
with `Supersedes: ADR-NNNN`, never a rewrite of the old one. See the
[ADR index](docs/adr/README.md) for the current list.

Commits go to `main` with detailed messages. The previous commits on
this branch show the style — short imperative title, paragraph
explaining what and why, known gaps called out explicitly, co-author
trailer.

## Starter reading list (in priority order)

Read these before touching anything:

1. [`README.md`](README.md) — project vision and phase map
2. [`docs/adr/README.md`](docs/adr/README.md) — ADR index
3. [`docs/adr/0001-append-only-source-of-truth.md`](docs/adr/0001-append-only-source-of-truth.md)
4. [`docs/adr/0002-message-protocol-v0.md`](docs/adr/0002-message-protocol-v0.md)
5. [`docs/adr/0008-transcript-native-format.md`](docs/adr/0008-transcript-native-format.md)
6. [`protocol/schema.py`](protocol/schema.py) — the contract itself

Everything else is searchable via `dmd search`. Use it.
