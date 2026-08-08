from __future__ import annotations

from dataclasses import dataclass, field

import anthropic

from remedy.agents import diagnostician, resolver, verifier
from remedy.ticker import ticking
from remedy.tools.testing import run_tests
from remedy.tools.diffing import snapshot, diff_snapshots


@dataclass
class SolveResult:
    resolved: bool
    iterations_used: int
    patch: str
    diagnosis: dict
    review: dict
    last_test_output: str
    trajectory: list[dict] = field(default_factory=list)


def _run_resolver(client, model, repo_root, diagnosis, blocked_paths, diagnostician_model,
                  iteration, label, trajectory, failure_feedback=None, verifier_feedback=None):
    log: list[dict] = []
    with ticking(f"resolving ({label})"):
        result = resolver.resolve(
            client, model, repo_root, diagnosis, blocked_paths,
            diagnostician_model=diagnostician_model,
            failure_feedback=failure_feedback,
            verifier_feedback=verifier_feedback,
            tool_log=log,
        )
    trajectory.append({"step": "resolve", "iteration": iteration, "label": label, "result": result, "tool_calls": log})
    return result


def _run_tests(repo_root, test_cmd, iteration, label, trajectory):
    with ticking(f"testing ({label})"):
        result = run_tests(repo_root, test_cmd)
    trajectory.append({"step": "test", "iteration": iteration, "label": label, "passed": result.passed})
    return result


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
) -> SolveResult:
    """Diagnostician runs once. Then resolver<->tester loops until tests
    pass (the correctness loop -- verifier is NOT in it). Only once tests
    are green does the verifier run once, on working code, to comment on
    quality/scalability. If it raises must-fix items, resolver gets one
    shot to address them, then a re-test guards against the quality fix
    breaking correctness. Terminates to a result either way.

    The patch is computed by snapshotting files before/after and diffing
    in-memory -- no git required, works on any plain folder."""
    trajectory: list[dict] = []

    before = snapshot(repo_root)

    diag_log: list[dict] = []
    with ticking("diagnosing"):
        diagnosis = diagnostician.diagnose(client, diagnostician_model, repo_root, issue, tool_log=diag_log)
    trajectory.append({"step": "diagnose", "diagnosis": diagnosis, "tool_calls": diag_log})

    # --- correctness loop: resolver <-> tester until green (verifier absent) ---
    failure_feedback: str | None = None
    resolver_result: dict = {}
    last_test_output = ""
    tests_passed = False
    iterations_used = 0

    for iteration in range(max_iterations):
        iterations_used = iteration + 1
        resolver_result = _run_resolver(
            client, resolver_model, repo_root, diagnosis, blocked_paths, diagnostician_model,
            iteration, f"iter {iteration + 1}", trajectory, failure_feedback=failure_feedback,
        )
        test_result = _run_tests(repo_root, test_cmd, iteration, f"iter {iteration + 1}", trajectory)
        last_test_output = test_result.output
        if test_result.passed:
            tests_passed = True
            break
        failure_feedback = test_result.failure_summary

    review: dict = {}

    # --- quality pass: verifier runs ONCE, only on green code ---
    if tests_passed:
        verify_log: list[dict] = []
        summary_for_verifier = (
            f"{resolver_result.get('summary', '')}\n"
            f"Files it reports changing: {resolver_result.get('changed_files', [])}"
        )
        with ticking("reviewing quality"):
            review = verifier.verify(
                client, verifier_model, repo_root, diagnosis, summary_for_verifier, blocked_paths,
                tool_log=verify_log,
            )
        trajectory.append({"step": "verify", "verdict": review, "tool_calls": verify_log})

        # verifier asked for changes -> one quality-fix attempt, then re-test
        if not review.get("approved", True) and review.get("must_fix"):
            feedback = "; ".join(review["must_fix"])
            _run_resolver(
                client, resolver_model, repo_root, diagnosis, blocked_paths, diagnostician_model,
                iterations_used, "quality-fix", trajectory, verifier_feedback=feedback,
            )
            requality_test = _run_tests(repo_root, test_cmd, iterations_used, "post-quality-fix", trajectory)
            last_test_output = requality_test.output
            # correctness is the hard gate: if the quality fix broke tests, that's the real outcome
            tests_passed = requality_test.passed

    return SolveResult(
        resolved=tests_passed,
        iterations_used=iterations_used,
        patch=diff_snapshots(before, snapshot(repo_root)),
        diagnosis=diagnosis,
        review=review,
        last_test_output=last_test_output,
        trajectory=trajectory,
    )
