from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ReadResult:
    success: bool
    content: str
    message: str = ""


@dataclass
class ListResult:
    success: bool
    entries: list[str] = field(default_factory=list)
    message: str = ""


def list_directory(path: str | Path) -> ListResult:
    """Non-recursive listing, dirs suffixed with '/'. This is the fallback
    exploration tool when search_code (ripgrep) isn't available or the
    agent doesn't know what to search for yet."""
    path = Path(path)
    try:
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
    except FileNotFoundError:
        return ListResult(False, message=f"not found: {path}")
    except NotADirectoryError:
        return ListResult(False, message=f"not a directory: {path}")
    except OSError as e:
        return ListResult(False, message=f"list failed: {e}")
    return ListResult(True, entries)


def read_file(path: str | Path, start_line: int | None = None, end_line: int | None = None) -> ReadResult:
    """Read a file, optionally a 1-indexed inclusive line range."""
    path = Path(path)
    try:
        # errors="replace" so a stray non-utf8 byte (common in Windows-authored
        # files) doesn't crash the read -- the agent gets the text with the
        # bad byte swapped for a placeholder instead of the run dying
        raw = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ReadResult(False, "", f"not found: {path}")
    except OSError as e:
        return ReadResult(False, "", f"read failed: {e}")

    lines = raw.splitlines(keepends=True)

    start = max(0, (start_line - 1) if start_line else 0)
    end = min(len(lines), end_line if end_line else len(lines))

    # prefix line numbers so the agent can point back to exact lines,
    # but apply_edit still matches on raw text so strip this before reuse
    numbered = [f"{i + 1}: {lines[i]}" for i in range(start, end)]
    return ReadResult(True, "".join(numbered))
