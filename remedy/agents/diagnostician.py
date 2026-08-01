from __future__ import annotations

import json

import anthropic

from remedy.agents.base import ToolSpec, run_agent
from remedy.tools.file_ops import read_file
from remedy.tools.search import search_code

SYSTEM_PROMPT = """You are the diagnostician for a coding agent. Given a \
GitHub issue and a repo, figure out which files are relevant and why -- \
you do not fix anything, only locate and explain.

Use search_code and read_file to find the code the issue describes.

When done, respond with ONLY a fenced json block, nothing else:

```json
{"relevant_files": ["path/to/file.py"], "diagnosis": "what's wrong and where"}
```
"""


def _make_tools(repo_root: str) -> list[ToolSpec]:
    return [
        ToolSpec(
            "search_code",
            "Search the repo for a literal string or regex.",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            lambda query: search_code(query, repo_root).__dict__,
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
            },
            lambda path, start_line=None, end_line=None: read_file(path, start_line, end_line).__dict__,
        ),
    ]


CLARIFY_SYSTEM_PROMPT = """You are the diagnostician, answering a targeted \
follow-up question from the resolver who is currently fixing the bug. \
Use search_code and read_file to answer precisely. Keep it short and \
specific -- just answer the question, no json needed.
"""


def clarify(client: anthropic.Anthropic, model: str, repo_root: str, diagnosis: dict, question: str) -> str:
    """Resolver hit ambiguity mid-fix and asked a specific question.
    Cheaper than a full re-diagnosis -- reuses the same read-only tools,
    just answers one thing instead of localizing from scratch."""
    tools = _make_tools(repo_root)
    user_message = (
        f"Original diagnosis: {diagnosis.get('diagnosis')}\n"
        f"Relevant files: {diagnosis.get('relevant_files')}\n\n"
        f"Resolver's question: {question}"
    )
    return run_agent(client, model, CLARIFY_SYSTEM_PROMPT, user_message, tools, max_turns=4)


def diagnose(client: anthropic.Anthropic, model: str, repo_root: str, issue: str) -> dict:
    """Runs once. Returns {"relevant_files": [...], "diagnosis": "..."}."""
    tools = _make_tools(repo_root)
    user_message = f"Repo root: {repo_root}\n\nIssue:\n{issue}"
    raw = run_agent(client, model, SYSTEM_PROMPT, user_message, tools)

    start, end = raw.find("{"), raw.rfind("}") + 1
    try:
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"relevant_files": [], "diagnosis": raw}
