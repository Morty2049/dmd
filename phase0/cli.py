# PHASE0: this file is throwaway — replaced in Phase 2 by a production
# CLI / MCP connector that lets agents "join the swarm" in one command.
# See ADR-0003 and ADR-0005.
"""``dmd`` command-line interface — Phase 0 stub.

The real implementation lands in the next commit. This file exists so
that ``pyproject.toml`` has a valid ``[project.scripts]`` entrypoint
and ``uv sync`` succeeds against a published package.

Planned commands:

- ``dmd append --author ... --role ... --text ...``
- ``dmd tail [--from-offset N]``
- ``dmd search "query"``
- ``dmd export``  — rebuild the Obsidian vault
- ``dmd watch --as agent_42``  — simulate a durable consumer locally
"""

from __future__ import annotations

import sys


def main() -> int:
    """Entrypoint referenced by ``pyproject.toml``."""
    print(
        "dmd Phase 0 CLI — scaffolding commit. Commands are not wired up yet.\n"
        "Planned: append, tail, search, export, watch. See phase0/cli.py.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
