# ADR-0007: Author identifiers must include the session surface

- **Status:** Accepted
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude_opus_app

## Context

The 2026-04-15 scaffolding day surfaced a real problem: morty was
working with **four distinct Claude instances simultaneously**:

1. Claude Opus in the native app (wrote the scaffolding + phase0 code)
2. Claude Opus in Antigravity (VS Code fork) — ran `dmd watch`, found
   the stdout buffering bug, shipped the fix
3. Claude Opus in a CLI terminal session
4. Claude Sonnet used sparingly for quick hints (to conserve Opus
   limits)

Using `claude_opus` as a bare author identifier is ambiguous: three of
those agents would collide on the same handle, and the fourth (Sonnet)
was invisible in the log. The `dmd demo` mock also uses `claude_opus`
as an imagined character, colliding with the real ones.

## Decision

Author identifiers take the form `<model>_<surface>`, where:

- `<model>` is a sluggified model family (`claude_opus`, `claude_sonnet`,
  `gemini_2`, etc.) — no version suffix, kept stable across minor
  bumps so reasoning chains don't break every release.
- `<surface>` is a short slug for the execution environment the agent
  is running on. One of:
  - `app` — native Claude app / claude.ai / desktop client
  - `antigravity` — Antigravity IDE
  - `cli` — `claude` CLI in a terminal
  - `api` — direct Anthropic API from user code
  - `hints` — Sonnet called for quick hints to save Opus limits
  - `mock` — scripted demo messages, not real agents
- Use `_` as the separator, not `@`. Command-line args, CSV exports,
  and URL path segments all deal poorly with `@` in handles.

Humans keep bare handles (`morty`, `alice`). No surface suffix — a
human doesn't change identity across IDEs.

### Examples

| Real agent                                  | Handle                |
|----------------------------------------------|-----------------------|
| Claude Opus, native app                      | `claude_opus_app`     |
| Claude Opus, Antigravity                     | `claude_opus_antigravity` |
| Claude Opus, CLI                             | `claude_opus_cli`     |
| Claude Sonnet, hint-mode                     | `claude_sonnet_hints` |
| Gemini 2 via direct API                      | `gemini_2_api`        |
| Scripted demo character                      | `claude_opus_mock`    |
| Human user                                   | `morty`               |

## Consequences

**Easier:**
- Every message in the swarm log can be traced to the exact surface
  that produced it. Bug reports ("Antigravity agent missed a
  mention") are attributable.
- Multi-agent analytics: `GROUP BY author` naturally splits by
  surface. Cost analytics: "how much did Antigravity-Opus spend this
  month?" becomes one query.
- No collision between real agents and the `dmd demo` mock
  characters — the mock ones get `_mock` suffix.

**Harder:**
- Migration debt for already-committed messages. Earlier commits used
  `claude_opus`, `claude_opus_scaffold`, `claude_opus_validate`
  (pre-ADR naming). Per append-only doctrine we do **not** rewrite
  them. New messages from this ADR onward use the scheme above.
  Analytics queries that want a unified view can `LIKE 'claude_opus%'`
  until the old handles age out.
- Agents must know their own surface. For Claude Code sessions, this
  is hand-declared in the ingestion helper (`scripts/append_turn.py`
  takes `--agent-author`).

## Alternatives considered

- **Session UUIDs** (`claude_opus__c7e3a1`). Unique, but unreadable in
  logs and searches. Rejected.
- **Full model version strings** (`claude-opus-4-6-app`). Breaks
  chains on every minor version bump; the surface is what varies per
  turn, not the model. Rejected.
- **`@` separator** (`claude_opus@app`). Looks like an email, reads
  naturally, but breaks command-line quoting and YAML inline syntax.
  Rejected.
