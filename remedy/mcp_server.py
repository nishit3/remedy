"""MCP server exposing the tool layer. Same four functions, callable over
the protocol so both our own loop and external MCP clients (Claude Desktop,
Cursor, etc.) can drive them the same way.

    python -m remedy.mcp_server        # stdio transport
"""
from __future__ import annotations

from dataclasses import asdict

from mcp.server.fastmcp import FastMCP

from remedy.tools.file_ops import read_file as _read_file
from remedy.tools.search import search_code as _search_code
from remedy.tools.edit import apply_edit as _apply_edit
from remedy.tools.testing import run_tests as _run_tests

mcp = FastMCP("remedy-tools")


@mcp.tool()
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> dict:
    """Read a file, optionally a 1-indexed inclusive line range. Returns numbered lines."""
    return asdict(_read_file(path, start_line, end_line))


@mcp.tool()
def search_code(query: str, root: str, max_results: int = 50) -> dict:
    """Search for a literal string or regex under root, ripgrep-backed."""
    return asdict(_search_code(query, root, max_results))


@mcp.tool()
def apply_edit(path: str, search: str, replace: str) -> dict:
    """Replace the first exact occurrence of `search` with `replace` in a file.
    Fails if search text is missing or ambiguous (appears more than once)."""
    return asdict(_apply_edit(path, search, replace))


@mcp.tool()
def run_tests(repo_path: str, test_cmd: str, timeout: int = 120) -> dict:
    """Run a test command in a repo. Returns pass/fail plus the failure
    traceback on failure -- never the test's own source."""
    return asdict(_run_tests(repo_path, test_cmd, timeout))


def run():
    mcp.run()


if __name__ == "__main__":
    run()
