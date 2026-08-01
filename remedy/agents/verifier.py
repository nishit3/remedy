from __future__ import annotations

import json

import anthropic

from remedy.agents.base import ToolSpec, run_agent
from remedy.tools.file_ops import read_file
from remedy.tools.search import search_code

SYSTEM_PROMPT = """You are the verifier for a coding agent. Review the \
resolver's proposed fix before it's tested. You do NOT have access to \
test files or test source.

Check two things:
1. Correctness plausibility -- does this change actually address the \
diagnosis, or does it look like a guess/unrelated edit?
2. Code quality -- readability, error handling, edge cases, and whether \
the approach scales or is a narrow patch that breaks under slightly \
different inputs.

Use read_file/search_code to inspect the changed files. When done, \
respond with ONLY a fenced json block:

```json
{"approved": true, "must_fix": [], "quality_notes": "short notes"}
```

Only set approved to false for real correctness problems -- wrong fix, \
unrelated change, something that obviously breaks. Quality issues go in \
quality_notes as feedback, not as a blocker -- don't fail a working fix \
over style.
"""


def _is_blocked(path: str, blocked_paths: set[str]) -> bool:
    return any(path.endswith(b) or b in path for b in blocked_paths)


def _make_tools(repo_root: str, blocked_paths: set[str]) -> list[ToolSpec]:
    def guarded_read(path: str, start_line=None, end_line=None):
        if _is_blocked(path, blocked_paths):
            return {"success": False, "message": "blocked: cannot read test files"}
        return read_file(path, start_line, end_line).__dict__

    def guarded_search(query: str):
        result = search_code(query, repo_root).__dict__
        result["matches"] = [m for m in result.get("matches", []) if not _is_blocked(m.split(":")[0], blocked_paths)]
        return result

    return [
        ToolSpec("read_file", "Read a file, optionally a line range.",
                 {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]},
                 guarded_read),
        ToolSpec("search_code", "Search the repo for a literal string or regex.",
                 {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                 guarded_search),
    ]


def verify(
    client: anthropic.Anthropic,
    model: str,
    repo_root: str,
    diagnosis: dict,
    resolver_summary: str,
    blocked_paths: set[str],
) -> dict:
    """Reviews the resolver's latest attempt before tests run. Blind to
    test source -- this is a patch-quality gate, not a ground-truth check,
    the tester still owns that. Fails open (approved=True) if the model's
    output doesn't parse, so a formatting hiccup can't stall the loop."""
    tools = _make_tools(repo_root, blocked_paths)
    user_message = (
        f"Diagnosis: {diagnosis.get('diagnosis')}\n"
        f"Files: {diagnosis.get('relevant_files')}\n\n"
        f"Resolver's summary of its change: {resolver_summary}"
    )
    raw = run_agent(client, model, SYSTEM_PROMPT, user_message, tools)

    start, end = raw.find("{"), raw.rfind("}") + 1
    try:
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"approved": True, "must_fix": [], "quality_notes": raw}
