# ADR-0008: Claude transcript as the native ingestion source

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude_opus_app

## Context

Earlier in the project we had no way to get "the real conversation"
into the swarm log. I reconstructed turns by hand in
`scripts/ingest_session.py`, and morty correctly pushed back: reconstructions
are lossy, they don't look like real LLM output, and the whole idea
should be engineering, not prompting Claude to return JSON at the end
of each turn.

During this session we discovered that **every Claude surface already
persists its own conversation on disk** in a structured format we can
parse deterministically. No prompting, no LLM-in-the-loop, no manual
copy-paste — the mapping is pure data transformation.

## Inventory of Claude transcript sources (as of 2026-04-15)

### Native Mac app (`claude-desktop`)

- **Path:** `~/.claude/projects/<slug>/<session-uuid>.jsonl`
- **Slug format:** absolute cwd with `/` → `-`, e.g.
  `/Users/leks/codeRepo/my_projects/dynamic-markdown`
  → `-Users-leks-codeRepo-my-projects-dynamic-markdown`
- **Discriminator:** first line with `type == "user"` has
  `entrypoint: "claude-desktop"`
- **Sample:** this very session,
  `dd0171a8-4f75-4e0d-8d70-56393859bb53.jsonl` (473 lines)

### Antigravity / VS Code extension (`claude-vscode`)

- **Path:** same tree, `~/.claude/projects/<slug>/<session-uuid>.jsonl`
- **Discriminator:** `entrypoint: "claude-vscode"`
- **Sample:** the parallel session that found the buffering bug,
  `12a1cbdb-b579-41f2-9a70-92b64af850fd.jsonl` (58 lines)

### Claude CLI (`claude` terminal)

- **Path:** assumed same tree; schema assumed same. Not yet verified
  with a real sample. When morty runs the CLI against this project
  we'll confirm and, if different, add an override in the mapper.
- **Discriminator:** expected `entrypoint: "claude-cli"` or similar.

### Claude Sonnet "hints" sessions

- Usually short API or app interactions. If they land in
  `~/.claude/projects/` at all, they follow the same schema. If not,
  they fall back to manual `dmd append`.

### Direct Anthropic API usage

- No local transcript. The consuming code is responsible for any
  logging. Out of scope for the native mapper.

## JSONL line schema (observed fields, stable across surfaces)

Each line is a JSON object. Relevant fields (others ignored):

```
type            one of: user, assistant, system,
                queue-operation, attachment, file-history-snapshot,
                ai-title
parentUuid      the uuid of the previous line in the chain (or null)
uuid            this line's uuid
timestamp       ISO-8601 with ms, UTC
sessionId       session uuid (same for every line in the file)
isSidechain     true for subagent sessions — skip by default
cwd             working directory
entrypoint      claude-desktop / claude-vscode / claude-cli / ...
version         client version
gitBranch       current git branch at the time of the turn

message         {role, content, model?, usage?, stop_reason?, ...}
                content is either a string OR a list of blocks:
                  {type: "text",     text: "..."}
                  {type: "thinking", thinking: "...", signature: "..."}
                  {type: "tool_use", name, input, id, caller}
                  {type: "tool_result", tool_use_id, content, is_error?}

usage           {input_tokens, output_tokens,
                 cache_creation_input_tokens,
                 cache_read_input_tokens, ...}
                (only on assistant lines)
```

## Mapping rules — transcript line → dmd Message

1. **Skip non-conversational lines.** `queue-operation`,
   `attachment`, `file-history-snapshot`, `ai-title`, and `system`
   are infrastructure and do not become messages.

2. **Skip sidechains.** `isSidechain == true` is a subagent run; its
   transcript belongs to a different graph and should be ingested as
   a separate tree if at all.

3. **One transcript line → one dmd Message.** No turn aggregation
   across lines. The parent-chain already forms the graph; preserving
   line-level granularity lets us query individual tool calls.

4. **Role mapping:**
   - `type == "user"` + user-typed text → `Role.QUESTION`
   - `type == "user"` + system-wrapped context (`<ide_opened_file>`,
     `<system-reminder>`, etc.) → skip if the block is ONLY the
     wrapper; keep if there is real user text alongside
   - `type == "assistant"` with any `text` block → `Role.ANSWER`
   - `type == "assistant"` with only `tool_use` blocks → `Role.REFLECTION`
     (my inner workings, not a reply)

5. **Text field construction:**
   - For user: concatenate `text` blocks, dropping any block whose
     text starts with `<ide_`, `<system-reminder>`, or
     `<local-command-caveat>` — those are injected context, not
     user input.
   - For assistant: concatenate `text` blocks.

6. **Chain-of-thought:** `thinking` block `thinking` field → joined
   into `Message.chain_of_thought` (new in protocol v0.2, see
   ADR-0006).

7. **Tool trace:** for assistant lines with `tool_use` blocks, append
   a compact trace to the end of `text`:
   ```
   [tools: Bash, Write, Read×3]
   ```
   This preserves what tools were called without bloating the log
   with full inputs.

8. **reply_to:** build a map `transcript_uuid → dmd_id` during a
   single pass; use the `parentUuid` lookup to set `reply_to`.

9. **token_cost:** take from `usage`:
   - `input = input_tokens + cache_creation_input_tokens + cache_read_input_tokens`
     (total tokens billed, cache reads included for accurate cost
     accounting; a follow-up ADR may split them)
   - `output = output_tokens`
   - `model = message.model`

10. **author:** derived from surface via ADR-0007:
    - `claude-desktop` → `claude_opus_app` (matches current model)
    - `claude-vscode` → `claude_opus_antigravity`
    - `claude-cli` → `claude_opus_cli`
    - user lines → `morty` (the active human for this project)

11. **tags:** `["transcript", f"surface:{surface}",
    f"session:{session_uuid[:8]}"]` plus any existing tags.

12. **Idempotency:** `Message.create` hashes
    `(author, ts, text)`. The transcript `timestamp` is used as `ts`,
    so re-running the mapper on the same file produces identical
    ids — the reader dedupes and nothing doubles.

## Consequences

**Easier:**
- Zero-prompting backfill. A new Claude session joining the project
  can run `scripts/ingest_claude_transcript.py ~/.claude/projects/<slug>/*.jsonl`
  once and have the full history in the swarm log.
- Thinking blocks become first-class memory. Future agents can search
  *reasoning*, not just responses.
- Per-surface analytics: "which surface produced the most
  corrections?", "which surface costs the most tokens per turn?".
- The whole ingestion is testable on fixtures — drop a mock JSONL in
  `tests/fixtures/`, run the mapper, assert the resulting Messages.

**Harder:**
- The mapper has to keep up with schema drift. The `message.content`
  block types have already grown (text, thinking, tool_use,
  tool_result, and more on the horizon). When a new block type
  appears we update the mapper, add a fixture, and bump the mapper's
  own `SCHEMA_VERSION` constant.
- Privacy: transcripts may contain secrets the user would rather not
  commit to a git-tracked vault. The mapper must have an opt-out
  filter (env var / config) for sensitive tags. Out of scope for
  v0.1 of the mapper, but flagged here so we don't forget.

## Alternatives considered

- **Manual `dmd append` per turn** — what we had in ADR-0003's
  interim. Doesn't scale, error-prone, loses thinking.
- **Claude Code Stop-hook** — would work but requires a hook shell
  script that itself parses the transcript. We still need the mapper
  described here; the hook is just the *trigger*, not a replacement.
- **Ask Claude to produce structured JSON at the end of each turn.**
  Explicitly rejected by morty: "это не должно быть промптами".
  Parsing a deterministic on-disk format is the correct engineering
  answer.
