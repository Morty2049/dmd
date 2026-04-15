# Hooking dmd into your Claude clients via MCP

Stop re-explaining the same project to every new agent. After a
five-line config edit, every Claude session you open — native app,
Antigravity, CLI, Cursor, anything else MCP-aware — gets four tools
that read from `~/.dmd/swarm.jsonl` and Qdrant:

| Tool        | What it gives the agent |
|-------------|--------------------------|
| `chitchat`  | The last hour of activity across **all** your sessions, chronological. The "what was I just doing" peek. Use this at turn start. |
| `search`    | Semantic search over the entire log. Russian + English. |
| `get`       | One message + its full reply chain, by id. |
| `append`    | Write a conclusion back so the next agent sees it. |
| `stats`     | Counts and last-activity, for sanity-checking the store. |

## Prerequisites (one time, on the machine)

```bash
cd /path/to/dmd               # this repo
docker compose up -d qdrant   # L1 vector store at :6333
.venv/bin/pip install -e .    # makes the `dmd-mcp` console script available
.venv/bin/python -m phase0.embedder   # index existing log → Qdrant
```

## Native Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(create it if missing). Add the `mcpServers` block:

```json
{
  "mcpServers": {
    "dmd-memory": {
      "command": "/Users/leks/codeRepo/my_projects/dynamic-markdown/.venv/bin/python",
      "args": ["-m", "phase0.mcp_server"],
      "cwd": "/Users/leks/codeRepo/my_projects/dynamic-markdown"
    }
  }
}
```

Restart Claude Desktop. The agent now has `dmd-memory.chitchat`,
`.search`, `.get`, `.append`, `.stats` available as tools.

## Antigravity (VS Code extension)

Antigravity reads MCP servers from the same `claude_desktop_config.json`
when launched alongside Claude Desktop, OR from its own settings if
configured separately. Try the desktop config first.

If that does not pick it up, add to VS Code settings.json:

```json
{
  "claude.mcpServers": {
    "dmd-memory": {
      "command": "/Users/leks/codeRepo/my_projects/dynamic-markdown/.venv/bin/python",
      "args": ["-m", "phase0.mcp_server"],
      "cwd": "/Users/leks/codeRepo/my_projects/dynamic-markdown"
    }
  }
}
```

## Claude Code CLI

Edit `~/.claude.json` or `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "dmd-memory": {
      "command": "/Users/leks/codeRepo/my_projects/dynamic-markdown/.venv/bin/python",
      "args": ["-m", "phase0.mcp_server"],
      "cwd": "/Users/leks/codeRepo/my_projects/dynamic-markdown"
    }
  }
}
```

If your version of the CLI uses a different file, run `claude mcp
list` to see where it expects the config.

## Verify the connection

In any Claude session that loaded the MCP server, the assistant
should be able to call `dmd-memory.chitchat`. Quick test prompt:

> Use the dmd-memory chitchat tool with default args and tell me
> what the last few messages were about.

The assistant should respond with a summary of recent activity —
the same content you would see by running

```bash
.venv/bin/python -m phase0.mcp_server
```

and sending a `tools/call` for `chitchat`.

## When you open a new agent

The instructions you used to type into every new session — *"this
project is dmd, swarm memory for AI agents, here's what we already
decided..."* — go away. Replace them with one short prompt:

> Use dmd-memory chitchat to see what we've been working on, then
> dmd-memory search if you need older context, then continue.

The agent reads its own memory and resumes. No re-explanation.

## What you still have to tell each new agent

- The **task** for *this* turn (because it didn't happen yet).
- Any **secrets** that don't live in the log (API keys, paths to
  private dumps).
- **Permission** to act (the human is still in the loop).

That is the irreducible minimum. Everything else lives in the log.
