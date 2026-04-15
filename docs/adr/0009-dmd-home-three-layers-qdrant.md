# ADR-0009: User-global store + three-layer memory (Qdrant for L1)

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude_opus_app

## Context

The scaffolding we built over 2026-04-15 was project-scoped: one
`data/swarm.jsonl` per repo, one vault per repo, transcripts ingested
only from that project's Claude Code sessions. That is wrong for the
actual problem morty articulated late in the day:

> мне нужна общая база знаний, память для агентов кто бы ни был этим
> агентом. У меня накопилось за 3 года огромное количество
> неструктурированных диалогов, у моих друзей и коллег тоже. У
> агентов которые запутались в контексте тоже. ЭТА ШТУКА ДОЛЖНА
> РЕШАТЬ ЗАДАЧУ.

The project scope assumed one codebase per memory store. The real
scope is one **user** (or one **team**) per memory store, spanning
every project, every Claude surface, every tool they use, and
including historical chat dumps going back years.

Morty also articulated a three-layer memory model that matches how
this problem is actually solved:

- **L3 — Agent Memory (context window).** The LLM's own RAM for the
  current turn. Standard, nothing to build here.
- **L2 — Shared Memory ON (RAM-like).** Append-only hot log, low
  latency, multi-writer, read-your-writes. What `swarm.jsonl`
  already is — we just had it in the wrong directory.
- **L1 — Cold storage (RAG).** Semantic search over a vector index
  of the full historical corpus. The missing piece.

## Decision

### Scope

One user-global store at `~/.dmd/`:

```
~/.dmd/
├── swarm.jsonl           L2 hot log, shared by every agent and
│                         every project on this user's machine
├── vault/                derived view (Obsidian) over L2
├── qdrant_storage/       L1 Qdrant persistence (Docker volume)
└── embedder.state.json   embedder's last-processed offset
```

`$DMD_HOME` env var overrides the default, which makes multi-user or
team setups possible later without a code change.

### L1 technology: Qdrant (not LanceDB)

Morty explicitly chose Qdrant over LanceDB because he wants to learn
it and has Docker running already. Runs as `qdrant/qdrant:latest` via
`docker-compose.yml` at the repo root, persists to
`~/.dmd/qdrant_storage`. One collection `dmd_messages`, cosine
distance, 384 dimensions.

### Embedding model: `intfloat/multilingual-e5-small`

Chosen for:
- **Multilingual** — morty writes Russian and English; paraphrase
  variants across both languages need to match.
- **Small** — ~120 MB, CPU-runnable, no GPU required for MVP.
- **E5 prompt convention** — `"query: ..."` and `"passage: ..."`
  prefixes are a known trick that boosts retrieval quality without
  any finetuning.
- **384-dim vectors** — ~4x cheaper than 768-dim variants on storage
  and query time; quality is sufficient for the current corpus size.

Upgrade path: re-embed the log with a larger model (e.g.
`multilingual-e5-large` or `bge-m3`) by wiping the Qdrant collection
and re-running `phase0/embedder.py`. The log is the source of truth;
the vector index is fully regeneratable.

### Embedder reads text + chain_of_thought together

When a `Message` has both a response text and a `chain_of_thought`
(populated by the transcript mapper from Claude thinking blocks),
the embedder concatenates them before embedding:

```
passage: <text>

reasoning: <chain_of_thought>
```

Rationale: the response is often a crisp summary; the reasoning
contains the specific keywords, bug names, and wrong turns that
match debugging-style queries ("what did I try for X that didn't
work"). Concatenation is the cheapest way to let one vector surface
both.

### Search API replaces substring

`phase0/search.py` now defaults to `search_semantic()` which queries
Qdrant. `search_substring()` is kept as an explicit fallback mode
for debugging and for when Qdrant is down (the hot log on disk is
always readable, the vector service may not be).

### Historical snapshot

The `data/swarm.jsonl` and `vault/` committed under this repo stay
as a historical snapshot from before the migration. They are no
longer authoritative — the canonical store is `~/.dmd/`. We do not
delete them in this commit per the append-only doctrine; a later
commit may move them to `docs/snapshots/` or similar if they become
noise.

## Consequences

**Easier:**
- One query surface (`dmd.search`) that any agent on any project on
  this user's machine can use. No per-project memory fragmentation.
- Semantic retrieval that actually finds what the user meant,
  verified live on 5 queries against our own 418-message corpus —
  the user's literal question "ради чего копится лог" scored 0.939
  vs substring which missed it entirely.
- Future ChatGPT / Claude web dump ingestion is now a pure
  import-script concern — the infrastructure (hot log → embedder →
  Qdrant → search) is agnostic to the source of the messages.
- Docker-compose up for Qdrant is one command; other agents joining
  the project get the same setup reproducibly.

**Harder:**
- External dependency on Docker + Qdrant running. If the user kills
  Docker, semantic search fails until it's back up. The substring
  fallback keeps the system functional but slower to find things.
- Embeddings need to be kept in sync. The embedder must run after
  every batch of new messages, or at least before queries. Currently
  this is manual / via `auto_ingest`. A proper watcher daemon is
  future work.
- Two embedding-model upgrades in the future mean re-embedding every
  message. For ~418 that's 15 seconds; for a 500k ChatGPT dump that's
  15-30 minutes. Bearable but non-trivial.
- Cross-user sharing (morty's friends and colleagues) is not
  addressed here. That likely needs a shared Qdrant instance or a
  merge-the-logs workflow — open question.

## Alternatives considered

- **LanceDB instead of Qdrant.** Simpler, embedded, no server. Would
  have been my MVP pick. Morty chose Qdrant explicitly because he
  wants to learn it and has Docker running; the operational cost is
  acceptable, the long-term prod fit is better.
- **Keeping the log project-scoped and just adding Qdrant per
  project.** Rejected: the problem is literally "3 years of dumps
  across many tools", so per-project scoping defeats the purpose.
- **Stuffing ChatGPT dumps into a RAG solution that already exists
  (e.g. Mem0, Letta, GPTCache).** Considered briefly. Rejected
  because none of them expose the append-only doctrine + typed
  role + reply_to graph that give this project its reasoning-over-
  reasoning character. The point of dmd is that the log is the
  source of truth and all other stores are derived views; existing
  RAG frameworks invert this by treating the vector store as
  authoritative.
