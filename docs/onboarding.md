# Onboarding a new agent to dmd

This page is for the **human** who wants to point another Claude
session (or a human collaborator) at this project. The agent itself
reads [`CLAUDE.md`](../CLAUDE.md) automatically when it opens the
repo — you do not need to paste briefing text.

## Fast path — three commands

```bash
git clone https://github.com/Morty2049/dmd.git
cd dmd
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

That is the whole setup. Open the folder in any Claude Code surface
(native app, Antigravity, CLI) and start asking questions. The agent
will read `CLAUDE.md` automatically, follow the sacred rules, and
search `vault/` before answering.

Optional: open `vault/` as an **Obsidian vault** to browse the
reasoning graph visually.

## Verifying the agent has the memory

After the agent finishes its first response, you can spot-check that
it actually read the vault:

- Ask a question whose answer is in an ADR, e.g. **"why don't we
  promote cached answers by hit count?"** — the right answer is in
  [ADR-0004](adr/0004-no-hit-count-promotion.md) with the phrase
  *"filter bubble"*. An agent that answered from memory of its own
  training would give a generic answer; an agent that read the vault
  will cite the ADR by number.
- Ask **"what author handle should you use?"** — the agent should
  derive it from [ADR-0007](adr/0007-author-namespace.md) based on
  which surface it is running on.

## Saving the new agent's session back to the vault

At the end of the session, or periodically during it, the human or
the agent runs:

```bash
.venv/bin/python scripts/ingest_claude_transcript.py \
    ~/.claude/projects/-Users-leks-codeRepo-my-projects-dynamic-markdown/<session-uuid>.jsonl \
    --export
```

Then commit the new `vault/msg_*.md` files:

```bash
git add vault/ data/swarm.jsonl  # data/swarm.jsonl is gitignored; stage vault only
git commit -m "Ingest session <uuid-prefix> — <topic>"
git push
```

The mapper is idempotent, so running it twice on the same session
file is safe. See [ADR-0008](adr/0008-transcript-native-format.md)
for the full mapping specification.

## What if the new agent is on a surface we haven't seen yet?

Check `~/.claude/projects/<slug>/<uuid>.jsonl` — if it follows the
schema from ADR-0008, the existing mapper works as-is. If the
`entrypoint` field is a new value, add it to
`ENTRYPOINT_TO_AUTHOR` in
[`scripts/ingest_claude_transcript.py`](../scripts/ingest_claude_transcript.py)
and write a one-paragraph ADR update.

If the surface doesn't persist transcripts to `~/.claude/projects/`
at all (e.g. direct Anthropic API usage), the session has to write
messages through `scripts/append_turn.py` or the `dmd append` CLI
instead. Not as nice, but works.

## What if the new agent is actually a *human* collaborator?

Same path. Humans write their messages directly via `dmd append`:

```bash
.venv/bin/python -m phase0.cli append \
    --author alice \
    --role question \
    --text "question text here" \
    --tag "session:<something-descriptive>"
```

Then commit the vault update. Humans never need a surface suffix on
their handle (see ADR-0007).

## Troubleshooting

**"The agent is ignoring `CLAUDE.md`."** Check that the file sits at
the repo root (not in a subdirectory) and that the agent's working
directory is that root. Claude Code reads the nearest `CLAUDE.md`
walking up from the cwd.

**"The transcript ingestion reports `0 message(s)`."** Probably you
pointed at the wrong `.jsonl` file, or the session hasn't flushed
yet. `wc -l <file>` — if it's zero, wait for Claude Code to write the
first turn. If it's large but ingest still returns zero, the schema
may have drifted; open an ADR for a mapper update.

**"I see duplicates in the vault after ingesting twice."** You
shouldn't — `Message.create` hashes `(author, ts, text)` so re-runs
are no-ops. If you do see them, the transcript file itself must have
changed (e.g. retry with a new timestamp). Open an issue.
