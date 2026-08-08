from __future__ import annotations

import difflib
from pathlib import Path

# skip dirs that are never the fix and would make snapshotting slow/noisy
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", ".pytest_cache"}


def snapshot(root: str | Path) -> dict[str, str]:
    """Map of relative-path -> file contents for every text file under root.
    Taken before and after the run so we can diff without needing git."""
    root = Path(root)
    snap: dict[str, str] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        try:
            snap[str(p.relative_to(root))] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return snap


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> str:
    """Unified diff across everything that changed between two snapshots.
    Covers modified, added, and deleted files."""
    parts: list[str] = []
    for path in sorted(before.keys() | after.keys()):
        old = before.get(path, "")
        new = after.get(path, "")
        if old == new:
            continue
        diff = difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        parts.append("".join(diff))
    if not parts:
        return "(no changes made)"
    return "\n".join(parts)
