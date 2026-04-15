"""Auto-ingest every Claude transcript for this project, then export.

Designed to be called by a Claude Code Stop hook after every assistant
turn. Finds all ``~/.claude/projects/<project-slug>/*.jsonl`` files
that match the current working directory, runs the transcript mapper
on each (idempotent), and re-exports the Obsidian vault so the user's
view refreshes on disk.

No git operations — the hook should not commit or push. That stays
manual so we don't flood ``main`` with auto-commits.

Safe to run repeatedly. The mapper's deterministic ids dedupe at read
time; re-export overwrites identical files with identical content.

Run manually for debugging::

    .venv/bin/python scripts/auto_ingest.py

Exit code is 0 on success, non-zero on any error so the hook's
telemetry can spot regressions.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ingest_claude_transcript import ingest

from phase0.obsidian_exporter import export
from phase0.paths import default_log_path, default_vault_path

DEFAULT_LOG = default_log_path()
DEFAULT_VAULT = default_vault_path()


def _project_slug(cwd: Path) -> str:
    """Translate an absolute path into Claude Code's project slug.

    ``/Users/leks/codeRepo/my_projects/dynamic-markdown``
    → ``-Users-leks-codeRepo-my-projects-dynamic-markdown``
    """
    return str(cwd.resolve()).replace("/", "-").replace("_", "-")


def _sessions_dir(cwd: Path) -> Path:
    return Path.home() / ".claude" / "projects" / _project_slug(cwd)


def main() -> int:
    cwd = Path.cwd()
    sessions_dir = _sessions_dir(cwd)
    if not sessions_dir.is_dir():
        print(
            f"auto_ingest: no sessions dir at {sessions_dir} — nothing to do",
            file=sys.stderr,
        )
        return 0

    jsonl_files = sorted(sessions_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"auto_ingest: no .jsonl files in {sessions_dir}", file=sys.stderr)
        return 0

    total_appended = 0
    for path in jsonl_files:
        try:
            produced = ingest(path, log_path=DEFAULT_LOG)
            total_appended += len(produced)
            print(
                f"auto_ingest: {len(produced):4d} from {path.name}",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            # A malformed transcript line should not kill the whole
            # hook; log and continue with the other files.
            print(
                f"auto_ingest: ERROR processing {path.name}: {exc}",
                file=sys.stderr,
            )

    try:
        count = export(DEFAULT_LOG, DEFAULT_VAULT)
        print(
            f"auto_ingest: exported {count} vault file(s) "
            f"(appended {total_appended} new lines this run)",
            file=sys.stderr,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"auto_ingest: export failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
