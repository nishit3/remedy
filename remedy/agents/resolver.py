from __future__ import annotations

import anthropic

from remedy.agents.base import ToolSpec, run_agent
from remedy.agents.diagnostician import clarify
from remedy.tools.file_ops import read_file, list_directory
from remedy.tools.edit import apply_edit
from remedy.tools.search import search_code

SYSTEM_PROMPT = """You are the resolver for a coding agent. You've been \
given a diagnosis of a bug and the files involved. Fix it using apply_edit.

Aim for the minimal, root-cause fix:
- Fix the actual underlying cause, not just the symptom. Do NOT hardcode \
or special-case specific values to make a failure go away -- that's a hack \
that breaks on the next input. The fix should be correct in general.
- Change as little as possible. Don't refactor surrounding code, rename \
things, or restructure files that aren't part of the bug. A small, \
surgical diff is the goal, not a rewrite.
- Stay consistent with the existing code's style and structure rather \
than imposing a different design.

You do NOT have access to test files -- you'll only ever see test failure \
output if your fix doesn't work, never the test source. If search_code \
isn't finding what you need, try list_directory to browse instead. If the \
diagnosis is unclear, use ask_diagnostician (limited uses) before \
guessing.

If the verifier later flags a genuine design or scalability concern, \
you'll get one chance to address it -- but default to minimal until then.

You must call a tool on every turn. When you're done -- whether you made \
an edit or decided not to -- call submit_fix with the files you actually \
changed and a short summary. That's how you finish, not by replying with \
plain text.
"""

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "changed_files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "files you actually edited with apply_edit -- empty if you made no change",
        },
        "summary": {
            "type": "string",
            "description": "what you changed and why, or why you made no change",
        },
    },
    "required": ["changed_files", "summary"],
    "additionalProperties": False,
}


def _is_blocked(path: str, blocked_paths: set[str]) -> bool:
    return any(path.endswith(b) or b in path for b in blocked_paths)


def _make_tools(
    repo_root: str,
    blocked_paths: set[str],
    client: anthropic.Anthropic,
    diagnostician_model: str,
    diagnosis: dict,
    max_clarifications: int = 2,
    tool_log: list[dict] | None = None,
) -> list[ToolSpec]:
    def guarded_read(path: str, start_line=None, end_line=None):
        if _is_blocked(path, blocked_paths):
            return {"success": False, "message": "blocked: cannot read test files"}
        return read_file(path, start_line, end_line).__dict__

    def guarded_list(path: str):
        result = list_directory(path).__dict__
        result["entries"] = [e for e in result.get("entries", []) if not _is_blocked(e, blocked_paths)]
        return result

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
        answer = clarify(client, diagnostician_model, repo_root, diagnosis, question, tool_log=tool_log)
        return {"answer": answer}

    return [
        ToolSpec("read_file", "Read a file, optionally a line range.",
                 {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"], "additionalProperties": False},
                 guarded_read),
        ToolSpec("list_directory", "List files/subdirs in a directory (non-recursive). Use when search isn't finding things.",
                 {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
                 guarded_list),
        ToolSpec("search_code", "Search the repo for a literal string or regex.",
                 {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
                 guarded_search),
        ToolSpec("apply_edit", "Replace exact text in a file with new text.",
                 {"type": "object", "properties": {"path": {"type": "string"}, "search": {"type": "string"}, "replace": {"type": "string"}}, "required": ["path", "search", "replace"], "additionalProperties": False},
                 guarded_edit),
        ToolSpec("ask_diagnostician", f"Ask a specific follow-up question if the diagnosis is unclear. Limited to {max_clarifications} uses.",
                 {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"], "additionalProperties": False},
                 ask_diagnostician),
        ToolSpec("submit_fix", "Submit when done -- required to finish, whether or not you made a change.",
                 SUBMIT_SCHEMA,
                 lambda **_: None),  # terminal tool, never actually invoked
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
    tool_log: list[dict] | None = None,
) -> dict:
    """One resolver attempt. Returns {"changed_files": [...], "summary": "..."}
    -- self-reported, not verified (the tester and tool_log are the real
    ground truth), but now schema-enforced instead of free prose."""
    tools = _make_tools(repo_root, blocked_paths, client, diagnostician_model or model, diagnosis, tool_log=tool_log)

    user_message = f"Relevant files: {diagnosis.get('relevant_files')}\nDiagnosis: {diagnosis.get('diagnosis')}"
    if failure_feedback:
        user_message += f"\n\nYour last attempt still failed. Test output:\n{failure_feedback}"
    if verifier_feedback:
        user_message += f"\n\nThe verifier flagged issues with your last attempt:\n{verifier_feedback}"

    result = run_agent(client, model, SYSTEM_PROMPT, user_message, tools, tool_log=tool_log, terminal_tool="submit_fix")
    if not result:
        return {"changed_files": [], "summary": "(gave up: hit max_turns without submitting)"}
    return result
