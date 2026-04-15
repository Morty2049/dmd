# ADR-0001: Append-only log is the source of truth

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude-opus-4-6

## Context

dmd models a swarm of agents writing into a shared memory. The memory
must support:

- **Many concurrent writers** (hundreds of developers + thousands of agents).
- **Auditability** — every past thought must remain inspectable, forever.
- **Cheap replay** — a new agent should be able to reconstruct state by
  re-reading history, no schema migrations required.
- **Derived views** — Obsidian graph, vector index, web UI — all computed
  from the same source.

A mutable CRUD store would force us to choose: either lose history, or
bolt on a separate audit log and keep them in sync. Both paths eventually
diverge.

## Decision

The **append-only log is the single source of truth**. No message is
ever edited or deleted. Every other artifact in the system — Qdrant
vectors, Obsidian `.md` files, ClickHouse materialized views, the web
client's rendered state — is a *derived view* that can be dropped and
regenerated from the log.

Corrections are themselves messages with `role = CORRECTION` and a
`reply_to` pointing at the original.

## Consequences

**Easier:**
- Storage is a commodity — any append-capable medium works (JSONL file,
  Kafka, NATS JetStream, ClickHouse MergeTree). We can swap them per phase
  without touching agent code.
- Replay is free. A brand-new view (or a new agent) just reads from offset 0.
- Debugging incidents means reading the log, not reconstructing state.
- The `Message` type is `frozen=True` in Pydantic — the invariant is
  enforced at the Python type level, not just in docs.

**Harder:**
- Storage grows monotonically. We need an archive/compaction story later
  (Phase 2+), but the log itself never gets rewritten — older segments
  just move to cold storage.
- Derived views can lag the log. That is explicit, not accidental — see
  the async embedder design in ADR-0003.
- Deletion for compliance (GDPR right-to-be-forgotten) becomes a cross-cut
  concern and needs its own ADR when it comes up.

## Alternatives considered

- **Mutable DB + audit log.** Rejected: two sources of truth eventually
  drift and every feature has to be implemented twice.
- **Event-sourcing with snapshots.** Partially compatible — we may add
  snapshots for fast cold-start later, but the log remains authoritative.
- **Git as the log.** Interesting, and Karpathy's LLM-Wiki community has
  explored it, but a git repo is slow to append at swarm scale and a
  commit graph is not the same shape as a reply graph.
