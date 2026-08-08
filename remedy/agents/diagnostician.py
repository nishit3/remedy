from __future__ import annotations

import anthropic

from remedy.agents.base import ToolSpec, run_agent
from remedy.tools.file_ops import read_file, list_directory
from remedy.tools.search import search_code

SYSTEM_PROMPT = """You are the diagnostician for a coding agent. Given a \
GitHub issue and a repo, figure out which files are relevant and why -- \
you do not fix anything, only locate and explain.

Use search_code to find code by keyword, list_directory to browse \
structure if search isn't finding what you need (or isn't available), \
and read_file to inspect specific files.

You must call a tool on every turn. When you have enough information, \
call submit_diagnosis -- that's how you finish, not by replying with \
plain text.
"""

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "paths to the files that need to change",
        },
        "diagnosis": {
            "type": "string",
            "description": "what's wrong and where, in enough detail for someone else to act on",
        },
    },
    "required": ["relevant_files", "diagnosis"],
    "additionalProperties": False,
}


def _make_tools(repo_root: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            "search_code",
            "Search the repo for a literal string or regex.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
            lambda query: search_code(query, repo_root).__dict__,
        ),
        ToolSpec(
            "list_directory",
            "List files/subdirs in a directory (non-recursive). Use when search isn't finding things.",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
            lambda path: list_directory(path).__dict__,
        ),
        ToolSpec(
            "read_file",
            "Read a file, optionally a line range.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            lambda path, start_line=None, end_line=None: read_file(path, start_line, end_line).__dict__,
        ),
        ToolSpec(
            "submit_diagnosis",
            "Submit your final diagnosis. Call this exactly once, when you're done investigating.",
            SUBMIT_SCHEMA,
            lambda **_: None,  # terminal tool -- run_agent intercepts this call before dispatch, fn is never actually invoked
        ),
    ]


CLARIFY_SYSTEM_PROMPT = """You are the diagnostician, answering a targeted \
follow-up question from the resolver who is currently fixing the bug. \
Use search_code, list_directory, and read_file to answer precisely. Keep \
it short and specific -- just answer the question, no json needed.
"""


def clarify(
    client: anthropic.Anthropic,
    model: str,
    repo_root: str,
    diagnosis: dict,
    question: str,
    tool_log: list[dict] | None = None,
) -> str:
    """Resolver hit ambiguity mid-fix and asked a specific question.
    Cheaper than a full re-diagnosis, and genuinely free-text (a short
    answer, not a structured record), so no terminal tool here."""
    tools = [t for t in _make_tools(repo_root) if t.name != "submit_diagnosis"]
    user_message = (
        f"Original diagnosis: {diagnosis.get('diagnosis')}\n"
        f"Relevant files: {diagnosis.get('relevant_files')}\n\n"
        f"Resolver's question: {question}"
    )
    return run_agent(client, model, CLARIFY_SYSTEM_PROMPT, user_message, tools, max_turns=4, tool_log=tool_log)


def diagnose(
    client: anthropic.Anthropic,
    model: str,
    repo_root: str,
    issue: str,
    tool_log: list[dict] | None = None,
) -> dict:
    """Runs once. Returns {"relevant_files": [...], "diagnosis": "..."},
    guaranteed to have that shape by submit_diagnosis's schema rather than
    by hoping a json fence parses cleanly."""
    tools = _make_tools(repo_root)
    user_message = f"Repo root: {repo_root}\n\nIssue:\n{issue}"
    result = run_agent(
        client, model, SYSTEM_PROMPT, user_message, tools,
        tool_log=tool_log, terminal_tool="submit_diagnosis",
    )
    if not result:
        return {"relevant_files": [], "diagnosis": "(gave up: hit max_turns without submitting a diagnosis)"}
    return result
