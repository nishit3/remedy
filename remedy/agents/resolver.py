from __future__ import annotations

import anthropic

from remedy.agents.base import ToolSpec, run_agent
from remedy.agents.diagnostician import clarify
from remedy.tools.file_ops import read_file
from remedy.tools.edit import apply_edit
from remedy.tools.search import search_code

SYSTEM_PROMPT = """You are the resolver for a coding agent. You've been \
given a diagnosis of a bug and the files involved. Fix it using apply_edit.

You do NOT have access to test files -- you'll only ever see test failure \
output if your fix doesn't work, never the test source. If the diagnosis \
is unclear, use ask_diagnostician (limited uses) before guessing. Make one \
focused edit, then stop and briefly describe what you changed.
"""


def _is_blocked(path: str, blocked_paths: set[str]) -> bool:
    return any(path.endswith(b) or b in path for b in blocked_paths)


def _make_tools(
    repo_root: str,
    blocked_paths: set[str],
    client: anthropic.Anthropic,
    diagnostician_model: str,
    diagnosis: dict,
    max_clarifications: int = 2,
) -> list[ToolSpec]:
    def guarded_read(path: str, start_line=None, end_line=None):
        if _is_blocked(path, blocked_paths):
            return {"success": False, "message": "blocked: cannot read test files"}
        return read_file(path, start_line, end_line).__dict__

    def guarded_search(query: str):
        result = search_code(query, repo_root).__dict__
        result["matches"] = [m for m in result.get("matches", []) if not _is_blocked(m.split(":")[0], blocked_paths)]
        return result

    def guarded_edit(path: str, search: str, replace: str):
        if _is_blocked(path, blocked_paths):
            return {"success": False, "message": "blocked: cannot edit test files"}
        return apply_edit(path, search, replace).__dict__

    clarifications_used = 0

    def ask_diagnostician(question: str):
        nonlocal clarifications_used
        if clarifications_used >= max_clarifications:
            return {"error": "clarification budget exhausted -- proceed with what you have"}
        clarifications_used += 1
        answer = clarify(client, diagnostician_model, repo_root, diagnosis, question)
        return {"answer": answer}

    return [
        ToolSpec("read_file", "Read a file, optionally a line range.",
                 {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]},
                 guarded_read),
        ToolSpec("search_code", "Search the repo for a literal string or regex.",
                 {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                 guarded_search),
        ToolSpec("apply_edit", "Replace exact text in a file with new text.",
                 {"type": "object", "properties": {"path": {"type": "string"}, "search": {"type": "string"}, "replace": {"type": "string"}}, "required": ["path", "search", "replace"]},
                 guarded_edit),
        ToolSpec("ask_diagnostician", f"Ask a specific follow-up question if the diagnosis is unclear. Limited to {max_clarifications} uses.",
                 {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
                 ask_diagnostician),
    ]


def resolve(
    client: anthropic.Anthropic,
    model: str,
    repo_root: str,
    diagnosis: dict,
    blocked_paths: set[str],
    diagnostician_model: str | None = None,
    failure_feedback: str | None = None,
    verifier_feedback: str | None = None,
) -> str:
    """One resolver attempt. Returns its own summary of what it changed --
    not trusted as ground truth, the tester decides that."""
    tools = _make_tools(repo_root, blocked_paths, client, diagnostician_model or model, diagnosis)

    user_message = f"Relevant files: {diagnosis.get('relevant_files')}\nDiagnosis: {diagnosis.get('diagnosis')}"
    if failure_feedback:
        user_message += f"\n\nYour last attempt still failed. Test output:\n{failure_feedback}"
    if verifier_feedback:
        user_message += f"\n\nThe verifier flagged issues with your last attempt:\n{verifier_feedback}"

    return run_agent(client, model, SYSTEM_PROMPT, user_message, tools)
