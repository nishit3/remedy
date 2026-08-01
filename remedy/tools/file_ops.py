from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReadResult:
    success: bool
    content: str
    message: str = ""


def read_file(path: str | Path, start_line: int | None = None, end_line: int | None = None) -> ReadResult:
    """Read a file, optionally a 1-indexed inclusive line range."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        return ReadResult(False, "", f"not found: {path}")
    except OSError as e:
        return ReadResult(False, "", f"read failed: {e}")

    start = max(0, (start_line - 1) if start_line else 0)
    end = min(len(lines), end_line if end_line else len(lines))

    # prefix line numbers so the agent can point back to exact lines,
    # but apply_edit still matches on raw text so strip this before reuse
    numbered = [f"{i + 1}: {lines[i]}" for i in range(start, end)]
    return ReadResult(True, "".join(numbered))
