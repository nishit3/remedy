from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestResult:
    passed: bool
    exit_code: int
    output: str
    failure_summary: str = ""
    timed_out: bool = False


def run_tests(repo_path: str | Path, test_cmd: str, timeout: int = 120) -> TestResult:
    """The one piece of ground truth in the system -- no LLM, just run it and
    parse the exit code. Split instead of shell=True to avoid shell
    injection since test_cmd can come from config/CLI args.

    Windows note: subprocess with shell=False doesn't do the PATHEXT-style
    executable search cmd.exe normally does, so "pytest" on PATH can fail
    to launch even though it works fine when you type it yourself. Resolve
    the executable's full path with shutil.which() first so this works
    consistently cross-platform.
    """
    args = shlex.split(test_cmd, posix=(os.name != "nt"))
    if not args:
        return TestResult(False, -1, "", "empty test command")

    resolved = shutil.which(args[0])
    if resolved:
        args[0] = resolved

    try:
        proc = subprocess.run(
            args,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        output = (e.stdout or "") + (e.stderr or "")
        return TestResult(False, -1, output, f"timed out after {timeout}s", timed_out=True)
    except FileNotFoundError as e:
        return TestResult(False, -1, "", f"'{args[0]}' not found on PATH -- is it installed? ({e})")

    output = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0

    return TestResult(
        passed=passed,
        exit_code=proc.returncode,
        output=output,
        failure_summary="" if passed else _extract_failure(output),
    )


def _extract_failure(output: str, max_chars: int = 4000) -> str:
    """Pull just the FAILURES section out of pytest output -- the resolver
    doesn't need the full run log, just the traceback."""
    idx = output.find("= FAILURES =")
    section = output[idx:] if idx != -1 else output[-max_chars:]
    return section[:max_chars]
