# PHASE0: MCP server exposing dmd memory to any MCP-aware client
# (Claude desktop, Claude Code, Claude CLI, Cursor, Continue, ...).
# See ADR-0010.
"""``dmd-memory`` — Model Context Protocol server over the dmd store.

Exposes the user-global ``~/.dmd/`` swarm log to any agent on the
machine via stdio MCP. The agent gets four tools:

- ``chitchat`` — *what has the user been doing recently?* Returns the
  last N messages across all sessions and surfaces, chronologically.
  This is the **"I just opened a new agent, give me ambient context"**
  primitive. No semantic search, no RAG — just temporal recency. The
  agent reads it once at the start of a turn and stops asking the
  human to re-explain.

- ``search`` — semantic Qdrant query. Use this when chitchat is too
  shallow and you need to find prior decisions, bug fixes, or
  reasoning by meaning rather than recency.

- ``get`` — fetch one message by id + walk its ``reply_to`` chain so
  you can see the full thread it lived in.

- ``append`` — write your own conclusion back to the log so the next
  agent benefits.

Stdio transport, one process per client. Multi-process safe: the
hot log is ``O_APPEND`` (POSIX atomic per line) and Qdrant has its
own concurrency.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from phase0.appender import append as append_to_log
from phase0.paths import default_log_path, qdrant_collection, qdrant_url
from phase0.reader import read_all
from phase0.search import search_semantic
from protocol.roles import Role
from protocol.schema import Message

mcp = FastMCP("dmd-memory")


def _format_message_short(msg: Message, *, max_text: int = 200) -> str:
    text = " ".join(msg.text.split())
    if len(text) > max_text:
        text = text[: max_text - 1] + "…"
    reply = f" ↩{msg.reply_to[:8]}" if msg.reply_to else ""
    tags = f" [{','.join(msg.tags[:4])}]" if msg.tags else ""
    return (
        f"[{msg.ts.strftime('%Y-%m-%d %H:%M')}] "
        f"{msg.author} ({msg.role.value}){reply}{tags}\n"
        f"  {text}"
    )


@mcp.tool()
def chitchat(
    window_minutes: int = 60,
    max_messages: int = 30,
    include_reflections: bool = False,
) -> str:
    """Get the user's recent activity context across all sessions.

    USE THIS at the start of your turn when you want ambient awareness
    of what the user has been working on, who else has been helping,
    and what the in-flight problem is — without burning tokens on a
    full semantic search. This is your "what's everyone been gossiping
    about" peek into the swarm.

    Args:
        window_minutes: How far back to look. Default 60 (last hour).
        max_messages: Cap on returned messages. Default 30.
        include_reflections: Whether to include tool-only assistant
            turns (lots of `[tools: Bash, Read]` noise). Default False
            because most of the signal is in user questions and
            assistant text answers.
    """
    log_path = default_log_path()
    if not log_path.exists():
        return f"(empty log at {log_path})"

    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(minutes=window_minutes)

    messages = read_all(log_path)
    recent = [m for m in messages if m.ts >= cutoff]
    if not include_reflections:
        recent = [m for m in recent if m.role != Role.REFLECTION]
    recent.sort(key=lambda m: m.ts)
    recent = recent[-max_messages:]

    if not recent:
        return f"No activity in the last {window_minutes} minutes."

    authors = sorted({m.author for m in recent})
    by_author: dict[str, int] = {}
    for m in recent:
        by_author[m.author] = by_author.get(m.author, 0) + 1
    summary_line = ", ".join(f"{a}({by_author[a]})" for a in authors)

    body = "\n\n".join(_format_message_short(m) for m in recent)
    return (
        f"== Recent dmd activity (last {window_minutes} min, "
        f"{len(recent)} messages) ==\n"
        f"Active: {summary_line}\n\n"
        f"{body}\n\n"
        f"(Use `search` for older or topic-specific lookups, "
        f"`get` to expand a thread by message id.)"
    )


@mcp.tool()
def search(query: str, top_k: int = 5) -> str:
    """Semantic search over the entire dmd swarm log.

    Pull prior conversations by meaning, not by literal keyword. Use
    when the user references something you don't remember, when you
    suspect a problem has been solved before, or when you want to
    ground an answer in real prior reasoning instead of generating
    fresh.

    Args:
        query: Natural language question. Russian and English both
            supported (multilingual embedding model).
        top_k: How many top hits to return. Default 5.
    """
    try:
        hits = search_semantic(query, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        return (
            f"semantic search failed: {exc}\n"
            f"Is the Qdrant container running? "
            f"`docker compose up -d qdrant` from the dmd repo. "
            f"Endpoint: {qdrant_url()}, collection: {qdrant_collection()}"
        )
    if not hits:
        return f"(no hits for '{query}' — log may be unindexed)"

    lines = [f"== Semantic hits for '{query}' (top {len(hits)}) =="]
    for score, m in hits:
        lines.append(f"\n[score {score:.3f}]  {_format_message_short(m, max_text=300)}")
    return "\n".join(lines)


@mcp.tool()
def get(message_id: str, walk_chain: bool = True, max_chain: int = 8) -> str:
    """Fetch one message by id; optionally walk its reply chain.

    Args:
        message_id: Full or prefix id (8+ hex chars) of the message.
        walk_chain: If true, follow ``reply_to`` parents up to
            ``max_chain`` levels and return the whole thread.
        max_chain: Cap on chain walk depth.
    """
    log_path = default_log_path()
    if not log_path.exists():
        return f"(empty log at {log_path})"

    messages = read_all(log_path)
    by_id = {m.id: m for m in messages}

    target = next(
        (m for m in messages if m.id == message_id or m.id.startswith(message_id)),
        None,
    )
    if target is None:
        return f"no message with id starting '{message_id}'"

    chain: list[Message] = [target]
    if walk_chain:
        cursor = target
        while cursor.reply_to and len(chain) < max_chain:
            parent = by_id.get(cursor.reply_to)
            if parent is None:
                break
            chain.append(parent)
            cursor = parent
        chain.reverse()  # oldest first

    parts = ["== Thread =="]
    for m in chain:
        parts.append("")
        parts.append(_format_message_short(m, max_text=600))
        if m.chain_of_thought:
            cot = " ".join(m.chain_of_thought.split())
            if len(cot) > 400:
                cot = cot[:399] + "…"
            parts.append(f"  reasoning: {cot}")
    return "\n".join(parts)


@mcp.tool()
def append(
    author: str,
    role: str,
    text: str,
    reply_to: str | None = None,
    tags: list[str] | None = None,
    chain_of_thought: str | None = None,
) -> str:
    """Write a new message to the dmd swarm log.

    Use this to record a conclusion, a corrective note, or a
    decision the next agent will benefit from. Honor ADR-0007 for
    your author handle: use ``claude_opus_app`` /
    ``claude_opus_antigravity`` / ``claude_opus_cli`` /
    ``claude_sonnet_hints`` according to your surface, or follow the
    ``<model>_<surface>`` pattern if your surface is new.

    Args:
        author: Your handle (see ADR-0007).
        role: One of question, answer, correction, reflection,
            mention, system.
        text: The visible message body.
        reply_to: Optional parent message id this is a response to.
        tags: Optional list of routing tags.
        chain_of_thought: Optional private reasoning behind the text
            (will be stored in v0.2 ``chain_of_thought`` field).
    """
    try:
        role_enum = Role(role)
    except ValueError:
        return f"invalid role '{role}' — must be one of {[r.value for r in Role]}"

    msg = Message.create(
        author=author,
        role=role_enum,
        text=text,
        reply_to=reply_to,
        tags=tags or [],
        chain_of_thought=chain_of_thought,
    )
    # embed=True so the message is searchable immediately by the next
    # tool call. The MCP server is a long-lived process so the model
    # is loaded once and cached at module level.
    append_to_log(msg, default_log_path(), embed=True)
    return (
        f"appended {msg.id} (indexed in Qdrant — searchable now)"
    )


@mcp.tool()
def stats() -> str:
    """Return summary stats: message count, author breakdown, recent activity."""
    log_path = default_log_path()
    if not log_path.exists():
        return f"(empty log at {log_path})"

    messages = read_all(log_path)
    if not messages:
        return "(empty log)"

    by_author: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for m in messages:
        by_author[m.author] = by_author.get(m.author, 0) + 1
        by_role[m.role.value] = by_role.get(m.role.value, 0) + 1

    last = max(messages, key=lambda m: m.ts)
    span = (last.ts - min(m.ts for m in messages)).total_seconds() / 3600

    lines = [
        f"messages:          {len(messages)}",
        f"unique authors:    {len(by_author)}",
        f"by role:           {by_role}",
        f"by author:         {by_author}",
        f"span:              {span:.1f} hours",
        f"last activity:     {last.ts.isoformat()} by {last.author}",
        f"log path:          {log_path}",
    ]
    return "\n".join(lines)


def main() -> None:
    """stdio entrypoint for MCP clients."""
    mcp.run()


if __name__ == "__main__":
    main()


# Help static analysis: these names are intentionally re-exported via
# the FastMCP decorators above; mark them as used.
_ = (chitchat, search, get, append, stats, Any)
