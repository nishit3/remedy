from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SearchResult:
    success: bool
    matches: list[str] = field(default_factory=list)
    message: str = ""


def search_code(query: str, root: str | Path, max_results: int = 50) -> SearchResult:
    """rg wrapper. This is how localization happens instead of a vector index."""
    if shutil.which("rg") is None:
        return SearchResult(False, message="ripgrep not installed (rg not on PATH)")

    try:
        proc = subprocess.run(
            ["rg", "--line-number", "--no-heading", query, str(root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return SearchResult(False, message="search timed out")

    # rg returns 1 for "no matches", not an error
    if proc.returncode not in (0, 1):
        return SearchResult(False, message=proc.stderr.strip())

    matches = [line for line in proc.stdout.splitlines() if line.strip()]
    return SearchResult(True, matches[:max_results])
