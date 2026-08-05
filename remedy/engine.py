from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import anthropic

from remedy.agents import diagnostician, resolver, verifier
from remedy.tools.testing import run_tests


@dataclass
class SolveResult:
    resolved: bool
    iterations_used: int
    patch: str
    diagnosis: dict
    last_test_output: str
    trajectory: list[dict] = field(default_factory=list)


def _git_diff(repo_root: str) -> str:
    proc = subprocess.run(["git", "diff"], cwd=repo_root, capture_output=True, text=True)
    return proc.stdout


def solve(
    client: anthropic.Anthropic,
    repo_root: str,
    issue: str,
    test_cmd: str,
    blocked_paths: set[str],
    diagnostician_model: str,
    resolver_model: str,
    verifier_model: str,
    max_iterations: int = 5,
    max_verifier_rounds: int = 2,
) -> SolveResult:
    """Diagnostician runs once. Resolver<->verifier is a bounded quality
    gate that sits inside resolver<->tester, the bounded correctness loop.
    Assumes repo_root is a clean git working tree -- the final diff is
    only meaningful if nothing else was dirty going in."""
    trajectory: list[dict] = []

    diagnosis = diagnostician.diagnose(client, diagnostician_model, repo_root, issue)
    trajectory.append({"step": "diagnose", "diagnosis": diagnosis})

    failure_feedback: str | None = None
    last_test_output = ""

    for iteration in range(max_iterations):
        verifier_feedback: str | None = None
        resolver_summary = ""

        for round_ in range(max_verifier_rounds):
            resolver_summary = resolver.resolve(
                client, resolver_model, repo_root, diagnosis, blocked_paths,
                diagnostician_model=diagnostician_model,
                failure_feedback=failure_feedback,
                verifier_feedback=verifier_feedback,
            )
            trajectory.append({"step": "resolve", "iteration": iteration, "round": round_, "summary": resolver_summary})

            verdict = verifier.verify(client, verifier_model, repo_root, diagnosis, resolver_summary, blocked_paths)
            trajectory.append({"step": "verify", "iteration": iteration, "round": round_, "verdict": verdict})

            if verdict.get("approved", True):
                break
            verifier_feedback = "; ".join(verdict.get("must_fix", [])) or verdict.get("quality_notes", "")
        # either approved or ran out of quality rounds -- test either way

        result = run_tests(repo_root, test_cmd)
        last_test_output = result.output
        trajectory.append({"step": "test", "iteration": iteration, "passed": result.passed})

        if result.passed:
            return SolveResult(
                resolved=True,
                iterations_used=iteration + 1,
                patch=_git_diff(repo_root),
                diagnosis=diagnosis,
                last_test_output=last_test_output,
                trajectory=trajectory,
            )

        failure_feedback = result.failure_summary

    return SolveResult(
        resolved=False,
        iterations_used=max_iterations,
        patch=_git_diff(repo_root),
        diagnosis=diagnosis,
        last_test_output=last_test_output,
        trajectory=trajectory,
    )
