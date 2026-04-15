# ADR-0006: Add `chain_of_thought` field to the Message protocol

- **Status:** Accepted (promoted from Proposed later the same day, after
  ADR-0008 proved thinking blocks are available on disk in the native
  Claude transcript format and populating the field is deterministic,
  not post-hoc storytelling)
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude_opus_app

## Context

The user asked for agents' reasoning (chain of thought) to live in the
swarm log alongside their responses. Today the protocol has no place
for it, so in `scripts/ingest_session.py` I smuggled reasoning inside
`text` under a `## Reasoning` / `## Response` markdown convention.
That works but:

- it's a convention, not a contract — different agents will format it
  differently
- Obsidian / Dataview can't query reasoning separately from the
  response
- search matches in CoT get conflated with matches in the public reply

## Decision

Add one optional field to `Message` and bump the protocol version to
`0.2`:

```python
chain_of_thought: str | None  # the agent's private reasoning, if any
```

- `None` means "no reasoning recorded" — same as today
- Human messages always have `None`
- Agents that have access to their own thinking tokens populate it;
  agents that don't leave it `None`

Messages written under `v0.1` remain valid when read by a `v0.2`
reader — the field defaults to `None`. No migration needed for
existing log lines.

## Consequences

**Easier:**
- Obsidian Dataview queries like "show me every answer where CoT
  mentions auth-svc but the reply doesn't" become trivial.
- Search can be scoped: `dmd search --in reasoning "oauth"` vs
  `dmd search --in text "oauth"`.
- The `## Reasoning` / `## Response` convention in `ingest_session.py`
  can be lifted out of `text` into the proper field in a follow-up
  migration (not mandatory).

**Harder:**
- The exporter's rigid frontmatter schema gains one more field. Fine
  — that's what rigid schemas are for.
- Writers that *don't* have access to their own CoT (most current
  Claude sessions) must honestly leave it `None`. Making up a
  reasoning summary post-hoc and stuffing it into the field would be
  dishonest; don't do it.

## Alternatives considered

- **Keep it in `text` with a convention.** That's the current hack.
  Works for one author, breaks when three agents each invent their
  own markers.
- **Emit a separate `REFLECTION` message per reasoning block.** Would
  double the message count and muddy the `reply_to` graph.
- **Add a freeform `metadata: dict[str, Any]` escape hatch.** Tempting,
  but then everyone puts their own keys in it and we lose the
  contract. Reject.
