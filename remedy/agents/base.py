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
    max_turns: int = 8,
    max_tokens: int = 2000,
) -> str:
    """Generic tool-calling loop. Sends a message, executes whatever tools
    the model calls, feeds results back, repeats until it stops calling
    tools or we hit max_turns. Both agents share this -- only the system
    prompt and toolset differ between them."""
    tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
    tool_map = {t.name: t.fn for t in tools}

    messages = [{"role": "user", "content": user_message}]

    for _ in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tool_defs,
        )

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if not tool_calls:
            return "".join(b.text for b in response.content if b.type == "text")

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for call in tool_calls:
            fn = tool_map.get(call.name)
            result = fn(**call.input) if fn else {"error": f"unknown tool: {call.name}"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    return "(gave up: hit max_turns without a final answer)"
