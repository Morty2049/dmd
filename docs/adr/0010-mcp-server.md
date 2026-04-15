# ADR-0010: dmd as an MCP server (`dmd-memory`)

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude_opus_app

## Context

Two independent forces converged on this decision:

1. **Morty's frustration**, articulated late on 2026-04-15:
   *"так задалбывает если честно каждый раз новым агентам параллельно
   объяснять что делать, какой-то кошмар."*
   He runs four+ Claude surfaces simultaneously (native app,
   Antigravity, CLI, Sonnet hint mode) and was re-pasting the same
   project briefing into every new session.

2. **Morty's `chitchat` insight** in the same turn:
   *"когда ты знаешь что другой агент работает над проектом и вы
   'сплетничаете про последний контекст' ... но вы знаете про
   пользователя ближайший контекст (про проект / shared memory),
   а если надо то и глубже понять — то покопаетесь (RAG)."*
   This is two distinct primitives, not one: ambient awareness of
   recent activity (chitchat) and deep semantic lookup (search).

We had the data on disk in `~/.dmd/swarm.jsonl`. We had the vector
index in Qdrant. What we did not have was a **way for an arbitrary
agent on an arbitrary surface to actually call them** without a
custom integration. CLAUDE.md helps for one project; nothing carries
across surfaces.

## Decision

Ship a Model Context Protocol server, `dmd-memory`, that any
MCP-aware client can attach to via stdio. One config block per
client, no per-project setup, the same memory layer everywhere.

### Tools exposed

Five tools, deliberately small surface:

- `chitchat(window_minutes=60, max_messages=30, include_reflections=False)`
  — temporal, recent-activity peek. Use at the start of a turn for
  ambient awareness of what the user (and other agents) have been
  doing. Returns a chronological dump with active-author summary.
  Designed to replace the "explain the project to me" prompt morty
  was tired of writing. **This is the new primitive that came out
  of his insight.**

- `search(query, top_k=5)` — semantic Qdrant query. Use when
  chitchat is too shallow and you need to find prior decisions or
  bug fixes by meaning, not recency.

- `get(message_id, walk_chain=True, max_chain=8)` — fetch one
  message + walk its `reply_to` parents, returning the whole thread.
  Includes `chain_of_thought` reasoning when present.

- `append(author, role, text, reply_to, tags, chain_of_thought)` —
  write your conclusion back into the log so the next agent
  benefits. Author handle follows ADR-0007.

- `stats()` — sanity check. Counts, last activity, log path.

### Transport

stdio. One subprocess per MCP client, spawned by the client when it
starts. Multi-process safe because:
- the hot log uses POSIX `O_APPEND` (atomic per line)
- Qdrant is a service with its own concurrency
- the MCP process holds no shared in-memory state

stdio also avoids any port collisions and works inside sandboxed
clients (Claude Desktop) that wouldn't be able to bind to a local HTTP
port reliably.

### Console script

`pyproject.toml` exposes `dmd-mcp` as a `[project.scripts]` entry
pointing at `phase0.mcp_server:main`. After `pip install -e .` the
binary is available in the venv and any client config can reference
it as `<venv>/bin/dmd-mcp` or as `python -m phase0.mcp_server`.

### What `chitchat` does NOT try to be

- It does not do clustering or "active threads" detection. The agent
  gets raw chronological text and infers threads itself.
- It does not summarize via an LLM. Zero LLM calls inside the MCP
  process — that would be expensive, slow, and introduce a new model
  dependency. The reading agent has its own LLM.
- It does not filter by relevance to the agent's current task. That
  is what `search` is for. The two tools are deliberately separate
  primitives.

## Consequences

**Easier:**
- One config edit per Claude surface, then no more re-pasting context.
- The same `chitchat` blob informs every new agent regardless of
  which surface they live on. **Cross-surface memory parity.**
- `append` closes the loop: agents not only read the swarm log but
  contribute to it. Any insight from one agent becomes context for
  the next without a human relay.
- Verification is trivial. Any session can call `chitchat` and the
  human can spot whether the agent received real recent activity or
  not.

**Harder:**
- One more moving part in the install path: now you need Qdrant
  running AND the MCP server registered AND the embedder kept fresh.
  The setup doc (`docs/mcp-setup.md`) covers this but it is a step.
- Every MCP client needs its own config edit. Three surfaces = three
  files to touch. A future ADR could explore a single source-of-truth
  config that all surfaces import, but it does not exist today.
- `chitchat`'s window is a fixed `window_minutes` knob. Different
  contexts want different windows ("the last hour" vs "since I last
  was here"). For now the agent passes a value; later we may add a
  "since session start" mode that takes a previous chitchat call's
  high-water mark.

## Open follow-ups (not blocking this commit)

- **Auto-embed on append.** Today, `append` writes to L2 but does
  not auto-update Qdrant. The next session calling `search` will
  miss the new message until someone runs `phase0.embedder` again.
  Either the MCP `append` should background-trigger an embed, or a
  file watcher daemon should embed continuously. Out of scope here.
- **Cross-user `chitchat`.** Right now it reads one user's
  `~/.dmd/swarm.jsonl`. Morty's eventual vision is shared memory
  across friends and colleagues — that means either a remote
  Qdrant + remote hot log (sync via git or a simple sync daemon)
  or a federated query across multiple `~/.dmd` stores. Open ADR.
- **Search returning `chain_of_thought`.** Currently `search` only
  returns the message text and tags. Reasoning blocks live in the
  payload but are not surfaced. Cheap to add; deferred until the
  user explicitly wants them in retrieval results.
