from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic
import typer

from remedy import config
from remedy.engine import solve

app = typer.Typer(add_completion=False)

DEFAULT_MODEL = "claude-sonnet-4-5"  # swap for whatever your account has access to


def _validate_key(key: str) -> None:
    """Lists models instead of a real message call -- checks the key works
    without spending tokens on it."""
    anthropic.Anthropic(api_key=key).models.list()


def get_api_key() -> str:
    """Env var wins if set (lets you override per-shell). Otherwise use the
    saved key, or prompt once and save it for next time."""
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key

    saved = config.load_key()
    if saved:
        return saved

    for _ in range(3):
        key = typer.prompt("Enter your Anthropic API key", hide_input=True)
        try:
            _validate_key(key)
        except anthropic.AuthenticationError:
            typer.echo("that key was rejected -- check it and try again", err=True)
            continue
        config.save_key(key)
        typer.echo(f"key saved to {config.CONFIG_FILE}")
        return key

    typer.echo("too many failed attempts", err=True)
    raise typer.Exit(1)


def _explain_error(e: Exception) -> str:
    msg = str(e)
    if "credit" in msg.lower() or "balance" in msg.lower():
        return "Insufficient credit balance. Add credits at https://console.anthropic.com/settings/billing"
    if isinstance(e, anthropic.AuthenticationError):
        config.clear_key()
        return "API key invalid or revoked. It's been cleared -- run again to re-enter it."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "API key doesn't have permission for this. Check your account access."
    if isinstance(e, anthropic.RateLimitError):
        return "Rate limit hit. Wait a bit, or check your usage tier."
    if isinstance(e, anthropic.APIConnectionError):
        return "Couldn't reach the Anthropic API. Check your network connection."
    if isinstance(e, anthropic.APIStatusError):
        return f"API error ({e.status_code}): {msg}"
    return f"Unexpected error: {msg}"


@app.command()
def run(
    repo: Path = typer.Option(..., help="Path to the repo to fix"),
    issue: str | None = typer.Option(None, help="Issue text, inline"),
    issue_file: Path | None = typer.Option(None, help="Path to a file containing the issue text"),
    test_cmd: str = typer.Option(..., help="Command to run the tests, e.g. 'pytest tests/ -q'"),
    test_path: list[str] = typer.Option(..., help="Test file(s)/dir(s) the resolver/verifier can't read -- repeatable"),
    diagnostician_model: str = typer.Option(DEFAULT_MODEL),
    resolver_model: str = typer.Option(DEFAULT_MODEL),
    verifier_model: str = typer.Option(DEFAULT_MODEL),
    max_iterations: int = typer.Option(5),
    max_verifier_rounds: int = typer.Option(2),
    output: Path = typer.Option(Path("remedy_result.json"), help="Where to write the full result"),
):
    """Resolve an issue in REPO: diagnostician locates it, resolver fixes
    it, verifier gates quality, tester scores it against test_cmd."""
    if not issue and not issue_file:
        typer.echo("provide --issue or --issue-file", err=True)
        raise typer.Exit(1)
    issue_text = issue or issue_file.read_text(encoding="utf-8")

    client = anthropic.Anthropic(api_key=get_api_key())

    try:
        result = solve(
            client=client,
            repo_root=str(repo),
            issue=issue_text,
            test_cmd=test_cmd,
            blocked_paths=set(test_path),
            diagnostician_model=diagnostician_model,
            resolver_model=resolver_model,
            verifier_model=verifier_model,
            max_iterations=max_iterations,
            max_verifier_rounds=max_verifier_rounds,
        )
    except anthropic.APIError as e:
        typer.echo(_explain_error(e), err=True)
        raise typer.Exit(1)

    output.write_text(
        json.dumps(
            {
                "resolved": result.resolved,
                "iterations_used": result.iterations_used,
                "patch": result.patch,
                "diagnosis": result.diagnosis,
                "last_test_output": result.last_test_output,
                "trajectory": result.trajectory,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    typer.echo(f"resolved={result.resolved} iterations={result.iterations_used}")
    typer.echo(f"full result -> {output}")


def main():
    if "--help" not in sys.argv[1:] and "-h" not in sys.argv[1:]:
        get_api_key()  # prompt/validate/save before Typer checks any other args
    app()


if __name__ == "__main__":
    main()
