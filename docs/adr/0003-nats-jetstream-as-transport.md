# ADR-0003: NATS JetStream as Phase 2 transport

- **Status:** Proposed — activates in Phase 2
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude-opus-4-6

## Context

In Phase 2, dmd needs to move messages between many concurrent writers
(agents + humans) and many concurrent readers (agent consumers with
per-agent filters), while preserving the append-only doctrine from
ADR-0001. The transport must:

1. Accept many writers without blocking each other.
2. Give every reader a **durable cursor** so an agent that disconnects
   resumes exactly where it left off — no re-processing, no gaps.
3. Support **server-side filtering** so an agent only wakes up for
   messages that matter to it (direct `@mention`, `@group_mention`, or
   semantic proximity) — this is the "poток сознания, к рою нужно примкнуть
   и занять своё место" model discussed in design.
4. Be genuinely append-only at the protocol level — no accidental deletes.

## Decision

Phase 2 transport is **NATS JetStream**, configured append-only:

- One stream `swarm_v1` with subject hierarchy
  `swarm.v1.<kind>.<topic>` (e.g., `swarm.v1.question.auth`,
  `swarm.v1.answer.payments`). Subject hierarchy is how we get
  server-side filtering.
- Stream flags: `DenyDelete = true`, `DenyPurge = true`. This is the
  append-only contract enforced by the broker itself, not by client
  convention.
- Deduplication via `Nats-Msg-Id` set to `Message.id` — idempotency
  guaranteed at the transport layer, matching the contract from ADR-0002.
- Per-agent **durable pull consumer** with a `FilterSubject` or
  `FilterSubjects` list. The agent's subscription is "who am I, and what
  do I care about right now" — the runtime owns the cursor.

### Agent wake model

An agent does not poll the log. It is woken by:

1. **Direct mention.** The mention router (a stateless gateway
   component) parses incoming text for `@agent_42`, emits a
   `Message(role=MENTION, ...)` event on `swarm.v1.mention.agent_42`.
   Agent 42's durable consumer is subscribed to that subject.
2. **Group mention.** `@payments` expands via a directory into
   per-member mention events. The directory is eventually-consistent
   and itself lives in the log.
3. **Semantic proximity.** The gateway computes an embedding of the
   incoming message and, if similarity to an agent's current context
   crosses a threshold, emits a routed copy on
   `swarm.v1.routed.<agent_id>`. The agent is subscribed to its own
   routed-subject. Threshold tuning is out of scope for this ADR (and
   will need its own eval harness — see open questions).

### Deduplication at three layers

Matching the research from 2026-04-15:

1. **NATS** — `Nats-Msg-Id` window (default 2 min) drops immediate retries.
2. **Redis `SET NX`** — claim window for consumer groups (prevents two
   batch writers from racing to ClickHouse with the same id).
3. **ClickHouse `insert_deduplication_token`** — final defense; even if
   a message survives (1) and (2), ClickHouse will not write the same
   token twice.

## Consequences

**Easier:**
- Durable cursors per agent are a native feature, not something we build.
- Append-only is enforced by the broker, not by convention.
- Scaling reads = add consumers. Scaling writes = add streams/partitions.

**Harder:**
- One more service in the stack. The Phase 0 prototype does NOT run
  NATS — see ADR-0005 — it uses in-process function calls to simulate
  the subscription. This is deliberate: the protocol is locked first,
  the transport arrives later.
- Semantic proximity routing is an open engineering problem. The
  threshold, the embedding model, and the "current context" window all
  need tuning with real data. We noted this in design as a known risk
  (echoing the earlier critique of magic constant 0.92 thresholds).
- Replay of an entire stream into a new agent is O(stream size). For the
  32-agent MVP that is fine; at 10k agents we need snapshots.

## Alternatives considered

- **Kafka.** Equivalent in power, heavier to operate for a 32-agent MVP.
  Would revisit if we hit NATS throughput limits.
- **Redis Streams.** Simpler but weaker durability story and no native
  server-side subject filtering at the granularity we need.
- **Plain HTTP SSE + Postgres.** Fine for Phase 1 web prototype but does
  not give us per-consumer durable cursors for free.
- **In-process event bus.** This is literally Phase 0 (see ADR-0005);
  good enough to prove the protocol, insufficient for a real swarm.

## Open questions (deferred to follow-up ADRs)

- How is the agent directory structured so `@group` expansion is itself
  append-only?
- What embedding model, what threshold, what "current context" window
  for semantic routing? Needs an eval harness with real chat data.
- GDPR / right-to-be-forgotten under a `DenyPurge` stream — probably
  handled via tombstones + a separate redacted view, but that is its
  own ADR when the need arises.
