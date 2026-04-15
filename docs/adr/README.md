# Architecture Decision Records

This directory holds the decision log for dmd. ADRs are **append-only** —
the same doctrine the project itself enforces. When a decision is
reversed, write a new ADR with `Supersedes: ADR-XXXX`; never edit the old
one.

## Template

```markdown
# ADR-NNNN: <Title>

- **Status:** Proposed | Accepted | Superseded by ADR-MMMM | Rejected
- **Date:** YYYY-MM-DD
- **Deciders:** @handle, @handle

## Context
Why are we making this decision? What forces are at play?

## Decision
What we decided, in one or two sentences.

## Consequences
What becomes easier, harder, or newly required.

## Alternatives considered
Options we looked at and why we didn't pick them.
```

## Index

| #    | Title                                  | Status      |
|------|----------------------------------------|-------------|
| 0001 | Append-only log is the source of truth | Accepted    |
| 0002 | Message protocol v0.1                  | Accepted    |
| 0003 | NATS JetStream as Phase 2 transport    | Proposed    |
| 0004 | Reject hit-count knowledge promotion   | Rejected    |
| 0005 | Phased rollout: local → web → prod     | Accepted    |
