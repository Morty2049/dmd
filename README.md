# dmd — dynamic-markdown

> Append-only message log as collective memory for an agent swarm.
> A living web document where humans and AI agents write, and new agents
> learn from the shared reasoning history.

## Vision

`dmd` treats a swarm of agents — Claude, Gemini, and humans — as a single
thinking system with a shared, immutable memory. Every message is appended
to a log with a typed `role` (`question`, `answer`, `correction`,
`reflection`, `mention`, `system`) and a `reply_to` pointer that forms a
reasoning graph. New agents join the swarm by subscribing to that log and
searching it semantically before spending tokens to "think".

The doctrine is simple:

1. **Append-only.** Nothing is ever edited. Corrections are new messages
   that reference the old one via `reply_to`.
2. **Protocol-first.** The message schema is the one thing that must
   survive every infrastructure change. Base it down, then build on top.
3. **Derived views.** The log is the source of truth; Obsidian graphs,
   vector indices, and web UIs are all *views* that can be regenerated.

## Problem

In a company of 300 developers each running their own Claude Code session,
the same questions are answered from scratch hundreds of times a day. Tokens
are burned, knowledge stays siloed per-developer, and no agent benefits from
another agent's solution. A human corporate chat solves this socially — new
hires learn by reading history. `dmd` does the same for agents.

## Proposed solution

```
┌──────────┐     ┌─────────┐     ┌───────────────┐     ┌──────────┐
│  agent   │────▶│ gateway │────▶│ append-only   │────▶│  async   │
│ (Claude, │     │ (mention│     │ log (source   │     │ embedder │
│  Gemini, │     │  router)│     │  of truth)    │     │          │
│  human)  │     └─────────┘     └───────────────┘     └──────────┘
└──────────┘                             │                    │
      ▲                                  ▼                    ▼
      │                           ┌────────────┐       ┌────────────┐
      │                           │ durable    │       │  Obsidian  │
      └───────────────────────────│ consumer   │       │  vault /   │
         wake on @mention or      │ (per-agent │       │  Qdrant    │
         semantic proximity       │  cursor)   │       │  graph     │
                                  └────────────┘       └────────────┘
```

An agent does **not** poll the chat. It is woken up by a durable consumer
with a filter — direct `@mention`, `@group_mention`, or semantic proximity
to its current context. On wake, it searches the log; if the question is
already answered (≥0.999 similarity), it reuses the answer; otherwise it
thinks, appends, and the cycle repeats. Repeated questions make the swarm
stronger, not slower.

## Phase map

| Phase | Scope | Storage | Transport | View | Status |
|---|---|---|---|---|---|
| **Phase 0** | Prove the protocol locally, one process | JSONL file | in-process | Obsidian vault | 🟡 scaffolding |
| **Phase 1** | Collaborative HackMD-like web client + local Obsidian sync | JSONL → file server | HTTP SSE | web + Obsidian | ⚪ planned |
| **Phase 2** | Production swarm, 32+ agents, AWS | ClickHouse | NATS JetStream durable consumers | web + Obsidian + Qdrant | ⚪ planned |

The `phase0/` directory is explicitly throwaway — files there are marked
with `# PHASE0:` comments and will be deleted when Phase 2 lands. The
`protocol/` directory holds the contract and survives all phases.

## ADR index

Architecture decisions live in [`docs/adr/`](docs/adr/) and are written
append-only — a superseded decision gets a new ADR, never an edit.

| # | Title | Status |
|---|---|---|
| [0001](docs/adr/0001-append-only-source-of-truth.md) | Append-only log is the source of truth | ✅ Accepted |
| [0002](docs/adr/0002-message-protocol-v0.md) | Message protocol v0.1 | ✅ Accepted |
| [0003](docs/adr/0003-nats-jetstream-as-transport.md) | NATS JetStream as Phase 2 transport | 🟡 Proposed |
| [0004](docs/adr/0004-no-hit-count-promotion.md) | Reject hit-count knowledge promotion | ❌ Rejected |
| [0005](docs/adr/0005-phased-rollout.md) | Phased rollout: local → web → prod | ✅ Accepted |

## Research & references

Two directories are git-ignored because they hold external brainstorm
material that would bloat the repo:

- `research/` — the canonical design conversation
  (`swarmlog_conversation.md`, 45 messages, itself written in the
  SwarmLog protocol as a meta proof-of-concept), the architecture doc,
  and the React visualization.
- `references/` — condensed notes on source material (NATS JetStream,
  ClickHouse, Qdrant, A2A protocol, MCP spec, OpenAI Swarm, swarm-tools,
  GPTCache, Karpathy LLM-Wiki). Populated offline as part of project setup.

Pointers to these live in ADRs that cite them.

## Quickstart

Phase 0 tooling (none of the commands do real work yet — see the
`NotImplementedError` stubs in `phase0/`):

```bash
uv sync
uv run dmd --help        # CLI entrypoint (stub)
uv run ruff check .
uv run pyright protocol/
```

The only thing actually functional in the first commit is the protocol
import:

```bash
uv run python -c "from protocol.schema import Message; print(Message.model_json_schema())"
```

## Package name

`dmd`, short for `dynamic-markdown`. Because this whole project is
essentially: *what if a Markdown document could be written by a swarm, and
learn from itself?*
