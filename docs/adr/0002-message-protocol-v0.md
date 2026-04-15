# ADR-0002: Message protocol v0.1

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude-opus-4-6

## Context

The message schema is the one thing in dmd that is expensive to change.
Storage backends can be swapped (Phase 0 JSONL → Phase 2 ClickHouse),
transports can be swapped (in-process → NATS JetStream), views can be
regenerated — but every agent, every client, every reader reads the same
shape. Pin the contract early; evolve it only via new ADRs that bump
`protocol_version`.

The schema is informed by existing protocols reviewed during design:
Google A2A (agent cards, lifecycle states), Anthropic MCP (resources,
tools), OpenAI Swarm (function-call handoffs), and Joel Hooks' swarm-tools
(event-sourced outcomes with pattern promotion). Every borrowed idea is
noted inline below.

## Decision

Protocol v0.1 lives in [`protocol/schema.py`](../../protocol/schema.py)
and is frozen-by-construction via `pydantic.ConfigDict(frozen=True)`.
Exported JSON Schema lives at `protocol/schema.json` so non-Python
clients (future web frontend, Go/Rust connectors) can consume the
contract without importing Python.

### Fields

| Field              | Type          | Required | Rationale |
|--------------------|---------------|----------|-----------|
| `id`               | `str` (16 hex)| ✓        | `sha256(author|ts|text)[:16]`. Deterministic, so replays are idempotent without client state. |
| `ts`               | `datetime`    | ✓        | UTC, ms precision. Used by consumers as the ordering key. |
| `author`           | `str`         | ✓        | Agent id or human handle. Free-form; namespace conventions TBD. |
| `model`            | `str \| None` | optional | Which model produced the message (`claude-opus-4-6`, `gemini-2.0`, etc.). `None` = human author. |
| `role`             | `Role` enum   | ✓        | The *type of thought-act*: `question`, `answer`, `correction`, `reflection`, `mention`, `system`. This is the project's signature field — it lets the swarm reason about cognitive moves, not just messages. No existing protocol ships this typed. |
| `reply_to`         | `str \| None` | optional | Parent message id. Drives the reasoning-graph edges and Obsidian `[[wikilinks]]`. |
| `tags`             | `list[str]`   | optional | Routing + filtering hints (topics, departments, domains). |
| `text`             | `str`         | ✓        | Body, Markdown permitted. |
| `confidence`       | `float \| None` (0-1) | optional | Self-rated confidence. Input for future trust-weighted search. |
| `token_cost`       | `TokenCost \| None` | optional but expected on agent messages | Nested `{input, output, model}`. **Explicitly requested by @Morty2049 on 2026-04-15** as must-have for future swarm economics — ranking cheap-but-good solutions, detecting runaway agents, cost-aware routing. `None` for humans. |
| `protocol_version` | `Literal["0.1"]` | ✓     | Schema version. Bump via new ADR, never edit messages in place. |

### Idempotency contract

`Message.create(author, ts, text, ...)` computes the `id` deterministically.
Two calls with identical `(author, ts, text)` produce the same id. Storage
layers enforce uniqueness on `id`, so a retried append is a no-op — no
client-side deduplication state needed.

### Role enum — the signature move

Ordinary chat protocols carry `{role: "user" | "assistant"}`. dmd types
the *cognitive function* of each message:

- `question` → elicits answers
- `answer` → responds to a question
- `correction` → overrides a prior message (append-only, via `reply_to`)
- `reflection` → meta-commentary without amending truth
- `mention` → explicit routing event produced by the mention router
- `system` → infrastructure (agent joined, consumer rebalanced)

This allows downstream search to say "give me all accepted corrections
to this answer" or "show reflections on ADR-0003" without guessing from
text.

## Consequences

**Easier:**
- Any future storage backend gets a machine-verifiable contract.
- Idempotent replay = safe retries at every layer.
- Typed roles make Phase 2 analytics trivial (`GROUP BY role`).

**Harder:**
- Adding a field is a protocol version bump — a new ADR, new JSON schema,
  and a thought about how older clients read newer messages (forward
  compatibility). That friction is intentional.
- The ID is only 16 hex chars (64 bits) — collision-resistant enough for
  billions of messages, but not cryptographic. If we ever need
  tamper-evident chaining, that goes into a separate envelope field.

## Alternatives considered

- **CloudEvents.** Good envelope spec, but the fields we need for a
  reasoning swarm (role, reply_to, confidence, token_cost) are all in
  their `data` payload and invisible to routers. We would end up
  re-specifying them anyway.
- **A2A message envelope.** Closer in spirit, but A2A's 8-state task
  lifecycle assumes a request/response model — our log is broader than
  tasks.
- **Unstructured Markdown with frontmatter.** Concept-beautiful (the
  research brainstorm at `research/swarmlog_conversation.md` is literally
  this format), but unparseable at swarm scale. The Markdown is a *view*,
  not the contract.
