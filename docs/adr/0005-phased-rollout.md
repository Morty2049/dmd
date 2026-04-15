# ADR-0005: Phased rollout — local → web → production

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude-opus-4-6

## Context

Two forces pull in opposite directions:

1. The user is explicit: **"сразу overkill архитектуру, может быть
   взрывной рост"**. No SQLite, no toy stack, no "we'll migrate later"
   excuses. The final system is ClickHouse + NATS JetStream + Qdrant +
   FastAPI + web frontend + CLI/MCP connector.
2. The user is also explicit: **"делаем сначала B локально — с obsidian,
   смотрим реализацию — переходим в веб с Obsidian, тестим несколько
   агентов — ловим баги — переходим на CH + NATS + …"**. Start small,
   prove the protocol, learn before committing infrastructure.

These are reconciled by phasing the *implementation* while keeping the
*protocol* stable from day one.

## Decision

Three phases, each with an explicit throwaway boundary.

### Phase 0 — local prototype (this commit and the next)

- **Storage:** plain JSONL file at `data/swarm.jsonl`. **Not SQLite** —
  the user has a specific aversion to SQLite and it is not to be used
  even as a prototype shortcut.
- **Transport:** in-process function calls. No broker.
- **View:** `phase0/obsidian_exporter.py` materializes one `.md` per
  message into `vault/`, wikilinked via `[[reply_to]]`. Open the vault
  directly in Obsidian to see the reasoning graph.
- **Search:** local substring first, then local embeddings (sentence-
  transformers) with a numpy index. Qdrant comes later.
- **Scope mark:** every file in `phase0/` begins with
  `# PHASE0: this file is throwaway — replaced in Phase 2 by <X>`. When
  Phase 2 lands, `phase0/` is deleted, not migrated.

### Phase 1 — collaborative web + local Obsidian sync

- **Storage:** JSONL behind a file server or simple object store.
- **Transport:** HTTP SSE for the web client; a sync daemon for local
  Obsidian vaults.
- **Frontend:** HackMD-like collaborative editor. Every `Enter` produces
  a new append — the "edit" UX is actually an append under the hood.
- **Goal:** catch real bugs in the protocol with 2-3 agents and a human
  or two writing concurrently. Document what surprises us in ADRs.
- **Explicit non-goal:** production scale. This is still a prototype.

### Phase 2 — production swarm

- **Storage:** ClickHouse (MergeTree, partitioned by month,
  `LowCardinality` on high-cardinality-low-uniqueness columns).
- **Transport:** NATS JetStream (see ADR-0003), `DenyDelete` +
  `DenyPurge`.
- **Index:** Qdrant with INT8 quantization.
- **Gateway:** FastAPI. Handles mention routing, semantic proximity
  filtering, and backpressure.
- **Connector:** CLI and/or MCP server so an agent can "join the swarm"
  in one command. This is the "поток сознания — примкнуть и занять
  своё место" model the user described.
- **Deployment:** Docker Compose on AWS initially; Kubernetes later if
  we hit multi-region.

### What survives every phase

The `protocol/` directory. Nothing in it may depend on a specific
phase's storage, transport, or view. If a protocol change is needed, it
is a new ADR bumping `protocol_version` — not a quiet edit.

### What is thrown away at each boundary

- Phase 0 → Phase 1: delete `phase0/`; the JSONL file format persists
  but now lives behind a server.
- Phase 1 → Phase 2: delete the file-server layer; import all historical
  JSONL into ClickHouse via `INSERT INTO swarm_log FROM JSON EACH ROW`.

## Consequences

**Easier:**
- The protocol is the only real risk. Every phase ships a working
  end-to-end path on that contract.
- Phase transitions are clean deletes, not migrations, because the
  source of truth is a content-addressable log and the derived views are
  regeneratable.
- Every phase produces its own ADR describing what it taught us. The
  project maintains its own append-only memory of itself — the same
  doctrine it implements for its users.

**Harder:**
- Discipline required: resist letting Phase 0 ergonomics creep into
  Phase 2 design. Every file in `phase0/` must be visibly throwaway.
- The user cannot demo a web UI until Phase 1. Expectation set.

## Alternatives considered

- **Skip Phase 0, go straight to Phase 2.** Rejected: the protocol has
  not survived contact with real swarm traffic yet. Building on an
  unproven contract means either paying a protocol migration later
  (expensive because everything downstream depends on it) or shipping a
  bad contract we live with forever.
- **Build Phase 0 on SQLite.** Rejected on user instruction; also SQLite
  would tempt us to query it instead of treating the log as the source
  of truth.
- **Build Phase 0 on in-memory only.** Rejected: we want the JSONL on
  disk so a human can inspect it, grep it, and feel the shape of the
  data before Phase 2 infra hides it.
