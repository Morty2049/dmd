"""User-global path resolution for dmd storage.

One ``~/.dmd/`` directory per user, shared across every project and
every Claude session on the machine. Environment variable
``DMD_HOME`` overrides the default. See ADR-0009.
"""

from __future__ import annotations

import os
from pathlib import Path


def dmd_home() -> Path:
    """Return the user-global dmd directory.

    Defaults to ``~/.dmd`` but honors ``$DMD_HOME`` when set. Created
    on first access so callers can rely on it existing.
    """
    raw = os.environ.get("DMD_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".dmd"
    home.mkdir(parents=True, exist_ok=True)
    return home


def default_log_path() -> Path:
    """The single append-only hot log shared by all agents on this user."""
    return dmd_home() / "swarm.jsonl"


def default_vault_path() -> Path:
    """The Obsidian vault directory, a derived view over the log."""
    return dmd_home() / "vault"


def default_embedder_state() -> Path:
    """State file tracking the last byte offset the embedder has processed."""
    return dmd_home() / "embedder.state.json"


def qdrant_url() -> str:
    """Qdrant service URL. Override with ``$QDRANT_URL``."""
    return os.environ.get("QDRANT_URL", "http://localhost:6333")


def qdrant_collection() -> str:
    """Qdrant collection name. Override with ``$QDRANT_COLLECTION``."""
    return os.environ.get("QDRANT_COLLECTION", "dmd_messages")
