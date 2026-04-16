# ADR-0011: Mem0 as storage backend (hybrid architecture)

- **Status:** Accepted
- **Date:** 2026-04-16
- **Deciders:** @Morty2049, @claude_opus_app

## Context

On 2026-04-15 evening, after a full day building dmd's custom
embedder + raw Qdrant integration (~400 LOC), we discovered that
Mem0 (mem0.ai, active community, well-maintained) does the same
commodity work — embedding, vector indexing, search, multi-backend
support — in ~10 lines of config.

The user's reaction was direct: *"пу-пу-пуууу"* (deflation). After
testing Mem0 hands-on with our Qdrant instance, both parties agreed
that building a custom storage layer when a mature one exists is
wasted effort. But the parts of dmd that Mem0 does NOT have — Claude
Code transcript parser, MCP server, protocol with role typing,
chitchat — are genuinely unique.

## Decision

**Hybrid:** use Mem0 as the storage backend, keep dmd as the
integration layer on top.

### Replaced by Mem0 (commodity)

| dmd component | Mem0 equivalent | LOC removed |
|---|---|---|
| `phase0/embedder.py` | `mem0.Memory.add(infer=False)` | ~190 (deprecated) |
| `phase0/search.py` custom Qdrant code | `mem0.Memory.search()` | ~80 |
| Raw `qdrant-client` calls | Mem0's internal Qdrant adapter | — |

### Kept from dmd (unique)

| Component | Why unique |
|---|---|
| `scripts/ingest_claude_transcript.py` | Nobody else parses `~/.claude/projects/*.jsonl` |
| `phase0/mcp_server.py` with `chitchat` | Temporal recent-activity tool, not in Mem0 |
| `protocol/schema.py` Message v0.2 | Role typing (q/a/correction/reflection) + chain_of_thought |
| `scripts/auto_ingest.py` + Stop hook | Automatic system-level logging |
| `phase0/obsidian_exporter.py` | Human graph view |

### New file: `phase0/mem0_store.py`

Thin wrapper (~130 LOC) exposing three functions:
- `store(msg)` — Mem0 `add(infer=False)` with protocol metadata
- `query(text, top_k)` — Mem0 `search()` → reconstruct `Message`
- `bulk_store(messages)` — batch version of `store()`

Protocol metadata (author, role, reply_to, tags, chain_of_thought,
token_cost, ts) travels as a `metadata` dict through Mem0's Qdrant
payload and survives the round-trip.

### Infrastructure

Same Qdrant at `localhost:6333`, two collections:
- `dmd_messages` — legacy (our custom embedder). Can be deleted
  after confirming Mem0 path works.
- `mem0_dmd` — new primary, Mem0-managed.

Mem0 config uses `infer=False` always — no LLM fact extraction, raw
message storage. LLM config (Anthropic) is required by Mem0's init
but never called.

## Consequences

**Easier:**
- ~270 LOC of custom embedding/search code replaced by 10 lines of
  Mem0 config. Less surface area to maintain.
- Mem0 handles Qdrant collection lifecycle, embedding model loading,
  batch upserts, and future backend migrations (Chroma, Pinecone,
  Weaviate) without our code changing.
- `search_substring()` fallback still reads JSONL directly — no
  regression if Qdrant/Mem0 is down.

**Harder:**
- New dependency: `mem0ai>=1.0` + `anthropic>=0.30` (for the init
  config, even though we don't call the LLM).
- Mem0's `add()` is slightly slower than our custom upsert (~50ms
  vs ~30ms) due to its abstraction layer. Negligible for our volumes.
- Mem0's payload schema differs from ours — the wrapper translates,
  but if Mem0 changes their internal format we need to update
  `_metadata_to_msg()`.
- Two Qdrant collections co-exist until we delete the legacy one.

## Alternatives considered

- **Use Mem0 for everything including transcript parsing.** Rejected:
  Mem0 has no Claude Code awareness. The transcript mapper is our
  unique value.
- **Use Mem0 with `infer=True`.** Rejected: would burn LLM tokens
  on every message to extract "facts", losing full reasoning chains.
  For bulk import of 3-year ChatGPT dumps this would cost thousands
  of dollars.
- **Keep building custom.** Rejected after morty's honest reaction.
  The storage layer is solved; spending time on it is opportunity
  cost against the unique integration work.
- **Switch to Zep/Memori/other.** Not evaluated hands-on yet. Mem0
  was the first we tested and it passed. If Mem0 becomes a problem,
  the wrapper in `mem0_store.py` makes swapping straightforward.
