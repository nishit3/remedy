from __future__ import annotations

import anthropic

from remedy.agents.base import ToolSpec, run_agent
from remedy.tools.file_ops import read_file, list_directory
from remedy.tools.search import search_code

SYSTEM_PROMPT = """You are the verifier for a coding agent. The fix has \
ALREADY passed the tests -- correctness is established. Your job is a \
quality review of a working fix, not a pass/fail gate. You do NOT have \
access to test files or test source.

Assess:
1. Does the fix address the root cause, or is it a narrow hack (e.g. \
hardcoded/special-cased values) that happens to pass the tests but would \
break on different valid inputs?
2. Will it generalize -- does it hold for inputs beyond the ones tested, \
or is it brittle?
3. Reasonable design -- readability, obvious edge cases (empty/None/\
boundary), and whether it fits sensible principles (single \
responsibility, not duplicating logic that already exists elsewhere). \
Judge this in proportion to the bug: a one-line fix does not need a \
SOLID refactor, and demanding one is wrong.

Use read_file/search_code/list_directory to inspect the changed files \
directly -- don't just trust the resolver's summary, since it can \
describe something different from what's really on disk.

Reserve must_fix ONLY for real problems: the fix is a hack that won't \
generalize, it introduces a likely new bug, or it clearly violates the \
codebase's own conventions in a way that will cause trouble. Do NOT put \
style preferences, speculative future-proofing, or 'nice to have' \
refactors in must_fix -- those go in quality_notes as advice. Approving \
a working, minimal, correct fix with only quality_notes is the common, \
expected outcome.

You must call a tool on every turn. When done, call submit_review to \
finish.
"""

SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "must_fix": {"type": "array", "items": {"type": "string"}},
        "quality_notes": {"type": "string"},
    },
    "required": ["approved", "must_fix", "quality_notes"],
    "additionalProperties": False,
}


def _is_blocked(path: str, blocked_paths: set[str]) -> bool:
    return any(path.endswith(b) or b in path for b in blocked_paths)


def _make_tools(repo_root: str, blocked_paths: set[str]) -> list[ToolSpec]:
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

    return [
        ToolSpec("read_file", "Read a file, optionally a line range.",
                 {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"], "additionalProperties": False},
                 guarded_read),
        ToolSpec("list_directory", "List files/subdirs in a directory (non-recursive).",
                 {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
                 guarded_list),
        ToolSpec("search_code", "Search the repo for a literal string or regex.",
                 {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
                 guarded_search),
        ToolSpec("submit_review", "Submit your review. Call this exactly once, when done inspecting.",
                 SUBMIT_SCHEMA,
                 lambda **_: None),  # terminal tool, never actually invoked
    ]


def verify(
    client: anthropic.Anthropic,
    model: str,
    repo_root: str,
    diagnosis: dict,
    resolver_summary: str,
    blocked_paths: set[str],
    tool_log: list[dict] | None = None,
) -> dict:
    """Reviews the resolver's latest attempt before tests run. Blind to
    test source -- this is a patch-quality gate, not a ground-truth check,
    the tester still owns that. Fails open (approved=True) if the model
    somehow never submits, so a stuck run can't stall the loop."""
    tools = _make_tools(repo_root, blocked_paths)
    user_message = (
        f"Diagnosis: {diagnosis.get('diagnosis')}\n"
        f"Files: {diagnosis.get('relevant_files')}\n\n"
        f"Resolver's summary of its change: {resolver_summary}"
    )
    result = run_agent(client, model, SYSTEM_PROMPT, user_message, tools, tool_log=tool_log, terminal_tool="submit_review")
    if not result:
        return {"approved": True, "must_fix": [], "quality_notes": "(gave up: hit max_turns without submitting a review)"}
    return result
