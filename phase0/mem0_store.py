"""Mem0-backed storage layer for dmd (ADR-0011).

Thin wrapper that replaces our custom ``embedder.py`` + raw Qdrant
code with Mem0's managed ``Memory`` class. The rest of dmd (MCP
server, transcript mapper, CLI, Obsidian exporter) sees the same
interface — ``store()`` and ``query()`` return/accept ``Message``
objects. Mem0 handles embedding, vector indexing, and collection
lifecycle internally.

Always uses ``infer=False`` — we store raw messages, not LLM-
extracted facts. Our protocol metadata (author, role, reply_to,
tags, chain_of_thought, token_cost, ts) travels as a ``metadata``
dict so it survives the round-trip through Mem0's Qdrant payload.

Lazy singleton: the ``Memory`` object (and its embedding model) is
created once per process on first call to ``get_store()``. Long-
lived processes (MCP server) pay ~3-5s on first use, then ~30ms
per operation.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any

from phase0.paths import qdrant_url
from protocol.roles import Role
from protocol.schema import Message, TokenCost

_store: Any = None  # mem0.Memory, lazily initialized

# Collection name for the Mem0-managed Qdrant collection.
MEM0_COLLECTION = os.environ.get("DMD_MEM0_COLLECTION", "mem0_dmd")
EMBED_MODEL = "intfloat/multilingual-e5-small"
EMBED_DIMS = 384


def get_store() -> Any:
    """Return the singleton ``mem0.Memory`` instance, creating on first call."""
    global _store
    if _store is not None:
        return _store

    from mem0 import Memory

    # Parse qdrant URL → host + port
    url = qdrant_url()
    host = url.replace("http://", "").replace("https://", "").split(":")[0]
    port = int(url.rsplit(":", 1)[-1]) if ":" in url.rsplit("/", 1)[-1] else 6333

    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "host": host,
                "port": port,
                "collection_name": MEM0_COLLECTION,
                "embedding_model_dims": EMBED_DIMS,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": EMBED_MODEL,
                "embedding_dims": EMBED_DIMS,
            },
        },
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": "claude-sonnet-4-6",
                "api_key": os.environ.get("ANTHROPIC_API_KEY", "unused-infer-false"),
            },
        },
    }

    _store = Memory.from_config(config)
    print(
        f"mem0_store: initialized (qdrant={host}:{port}, "
        f"collection={MEM0_COLLECTION}, embed={EMBED_MODEL})",
        file=sys.stderr,
    )
    return _store


def _msg_to_metadata(msg: Message) -> dict[str, Any]:
    """Extract dmd protocol fields as a flat metadata dict for Mem0."""
    meta: dict[str, Any] = {
        "dmd_id": msg.id,
        "ts": msg.ts.isoformat(),
        "author": msg.author,
        "model": msg.model,
        "role": msg.role.value,
        "reply_to": msg.reply_to,
        "tags": msg.tags,
        "protocol_version": msg.protocol_version,
    }
    if msg.confidence is not None:
        meta["confidence"] = msg.confidence
    if msg.token_cost is not None:
        meta["token_cost_input"] = msg.token_cost.input
        meta["token_cost_output"] = msg.token_cost.output
        meta["token_cost_model"] = msg.token_cost.model
    if msg.chain_of_thought is not None:
        meta["chain_of_thought"] = msg.chain_of_thought[:2000]  # cap for payload size
    return meta


def _metadata_to_msg(memory: dict[str, Any]) -> Message:
    """Reconstruct a ``Message`` from a Mem0 search result + metadata."""
    meta = memory.get("metadata") or {}
    ts_raw = meta.get("ts")
    ts = datetime.fromisoformat(ts_raw) if isinstance(ts_raw, str) else datetime.now()

    role_raw = meta.get("role", "answer")
    role = Role(role_raw) if isinstance(role_raw, str) else Role.ANSWER

    token_cost = None
    if meta.get("token_cost_input") is not None:
        token_cost = TokenCost(
            input=int(meta["token_cost_input"]),
            output=int(meta.get("token_cost_output", 0)),
            model=str(meta.get("token_cost_model", "unknown")),
        )

    return Message(
        id=str(meta.get("dmd_id", memory.get("id", ""))),
        ts=ts,
        author=str(meta.get("author", "unknown")),
        model=meta.get("model") if isinstance(meta.get("model"), str) else None,
        role=role,
        reply_to=meta.get("reply_to") if isinstance(meta.get("reply_to"), str) else None,
        tags=list(meta.get("tags") or []),
        text=str(memory.get("memory", "")),
        confidence=meta.get("confidence"),
        token_cost=token_cost,
        chain_of_thought=meta.get("chain_of_thought"),
    )


def store(msg: Message, *, user_id: str = "global") -> str:
    """Store a single Message in Mem0 (with embedding). Returns Mem0 memory id."""
    m = get_store()

    # Build the text to embed: message text + chain_of_thought for richer retrieval
    embed_text = msg.text
    if msg.chain_of_thought:
        embed_text = f"{msg.text}\n\nreasoning: {msg.chain_of_thought}"

    result = m.add(
        [{"role": msg.role.value, "content": embed_text}],
        user_id=user_id,
        agent_id=msg.author,
        metadata=_msg_to_metadata(msg),
        infer=False,
    )
    results = result.get("results", [])
    return results[0]["id"] if results else ""


def bulk_store(messages: list[Message], *, user_id: str = "global") -> int:
    """Store multiple Messages. Returns count stored."""
    count = 0
    for msg in messages:
        try:
            store(msg, user_id=user_id)
            count += 1
        except Exception as exc:  # noqa: BLE001
            print(f"mem0_store: failed to store {msg.id}: {exc}", file=sys.stderr)
    return count


def query(
    text: str,
    *,
    top_k: int = 5,
    user_id: str = "global",
    agent_id: str | None = None,
) -> list[tuple[float, Message]]:
    """Semantic search via Mem0. Returns [(score, Message), ...] descending."""
    m = get_store()
    kwargs: dict[str, Any] = {"user_id": user_id, "limit": top_k}
    if agent_id:
        kwargs["agent_id"] = agent_id

    results = m.search(text, **kwargs)
    hits: list[tuple[float, Message]] = []
    for r in results.get("results", []):
        score = float(r.get("score", 0))
        msg = _metadata_to_msg(r)
        hits.append((score, msg))
    return hits
