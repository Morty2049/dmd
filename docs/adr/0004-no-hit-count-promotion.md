# ADR-0004: Reject hit-count knowledge promotion

- **Status:** Rejected
- **Date:** 2026-04-15
- **Deciders:** @Morty2049, @claude-opus-4-6

## Context

An earlier design iteration proposed promoting cached answers through
tiers based on how often they were reused:

```
Candidate (≥0.95 similarity) → Validated (≥0.90) → Golden (≥0.85)
```

The intent was "let the swarm learn which answers work" by lowering the
match threshold for frequently-reused answers so they get returned more
eagerly. This is the same shape as swarm-tools' pattern promotion
("candidate → established → proven").

## Decision

**Rejected.** Do not implement hit-count-based promotion, and do not
silently reintroduce any mechanism with the same shape under a different
name.

## Rationale

Promoting answers by reuse count is a **filter bubble inside the
knowledge base**. Three failure modes:

1. **Popular ≠ correct.** An answer that happens to match many queries
   early gets shown more, gets matched more, gets promoted further. The
   metric rewards "most matched", not "most correct".
2. **Correct-but-rare answers decay.** A precise answer to a narrow
   technical question gets matched once a month. It never accumulates
   hits, never gets promoted, eventually falls below the threshold of a
   competing generic answer — and disappears from the swarm's effective
   memory.
3. **Stale "golden" answers persist.** Once an answer is tier-promoted,
   the lowered threshold makes it *even harder* to dislodge. The system
   is self-reinforcing against the very updates it should welcome.

This was flagged directly in design on 2026-04-15:
> "подход к самообучению будет примитивным и приведет к деградации
> знаний. Лучше не использовать в выдаче такой подход."

## Consequences

- The `Message` schema does **not** carry a `hit_count` field. If one
  appears, it must be an analytics artifact, not a retrieval input.
- Retrieval ranking in the semantic cache layer uses model-provided
  signals (similarity, confidence, recency of the most recent
  correction targeting this message), never aggregate popularity.
- We still need a self-improvement story. That is an open problem;
  candidates worth exploring later include:
  - **Correction-aware retrieval** — an answer with an accepted
    `CORRECTION` in its reply chain ranks lower than one without.
  - **Expert-weighted trust** — score messages by the verified accuracy
    of their author, not reuse count.
  - **Active invalidation** — periodic re-evaluation of hot answers
    against fresh model output to detect drift.
- Any future ADR that reintroduces a usage-count signal into retrieval
  must cite this ADR and explain why it does not hit the three failure
  modes above.

## Alternatives considered

- **Hit-count with decay.** Still biased toward whatever was popular
  early. Decay slows the bubble, does not pop it.
- **Manual curation.** Does not scale to a swarm.
- **LLM-judge promotion.** Plausible but expensive, and pushes the
  problem onto another model with its own biases — worth a dedicated
  ADR if we go there.
