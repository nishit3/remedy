from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import anthropic


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any]


def run_agent(
    client: anthropic.Anthropic,
    model: str,
    system: str,
    user_message: str,
    tools: list[ToolSpec],
    max_turns: int = 15,
    max_tokens: int = 2000,
    tool_log: list[dict] | None = None,
    terminal_tool: str | None = None,
) -> Any:
    """Generic tool-calling loop.

    If terminal_tool is set: every turn is forced to call some tool
    (tool_choice="any"), and the loop ends only when the model calls that
    specific tool -- its schema-validated input is returned directly as
    the structured result. This replaces asking the model to print a json
    fence and parsing it with string search; the API enforces the shape,
    not us.

    Without terminal_tool, behaves as a normal agent that ends by
    replying with plain text (used by the resolver's ask_diagnostician
    sub-calls, where free text is genuinely what's wanted).

    Malformed tool calls (wrong/missing arguments) are caught and turned
    into a tool_result error the model can see and correct, instead of
    crashing the run.
    """
    tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
    tool_map = {t.name: t.fn for t in tools}
    tool_choice = {"type": "any"} if terminal_tool else {"type": "auto"}

    messages = [{"role": "user", "content": user_message}]

    for turn in range(max_turns):
        # on the final turn, force a decision so a long investigation doesn't
        # silently run out mid-exploration without ever submitting
        if terminal_tool and turn == max_turns - 1:
            messages.append({
                "role": "user",
                "content": f"This is your last turn -- call {terminal_tool} now with your best answer from what you've gathered.",
            })

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tool_defs,
            tool_choice=tool_choice,
        )

        tool_calls = [b for b in response.content if b.type == "tool_use"]

        if terminal_tool:
            terminal_call = next((c for c in tool_calls if c.name == terminal_tool), None)
            if terminal_call:
                if tool_log is not None:
                    tool_log.append({"tool": terminal_call.name, "input": terminal_call.input, "result": "submitted"})
                return terminal_call.input

        if not tool_calls:
            if terminal_tool:
                return {}  # shouldn't happen with tool_choice="any", but don't crash if it does
            return "".join(b.text for b in response.content if b.type == "text")

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for call in tool_calls:
            fn = tool_map.get(call.name)
            try:
                result = fn(**call.input) if fn else {"error": f"unknown tool: {call.name}"}
            except TypeError as e:
                result = {"error": f"bad arguments for {call.name}: {e}"}
            if tool_log is not None:
                tool_log.append({"tool": call.name, "input": call.input, "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return {} if terminal_tool else "(gave up: hit max_turns without a final answer)"
