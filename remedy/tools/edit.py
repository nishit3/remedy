from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class EditResult:
    success: bool
    message: str


def apply_edit(path: str | Path, search: str, replace: str) -> EditResult:
    """Exact search/replace, not a diff -- avoids the line-number mismatches
    that make LLM-generated unified diffs fail to apply cleanly."""
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return EditResult(False, f"not found: {path}")
    except UnicodeDecodeError:
        # refuse rather than read with errors="replace" and write back --
        # that would silently corrupt the offending byte on disk
        return EditResult(False, f"cannot edit: {path} is not valid UTF-8")
    except OSError as e:
        return EditResult(False, f"read failed: {e}")

    count = content.count(search)
    if count == 0:
        return EditResult(False, "search text not found (must match exactly, whitespace included)")
    if count > 1:
        return EditResult(False, f"ambiguous match, found {count} times -- add more context to disambiguate")

    try:
        path.write_text(content.replace(search, replace, 1), encoding="utf-8")
    except OSError as e:
        return EditResult(False, f"write failed: {e}")

    return EditResult(True, "applied")
