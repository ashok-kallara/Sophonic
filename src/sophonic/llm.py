"""Anthropic client with prompt caching and type-aware tool schema generation."""

from __future__ import annotations

import inspect
import json
import os
import types
import typing
from datetime import date
from typing import Any, Union, get_args, get_origin

import anthropic

from sophonic.config import load_config

def _build_system_prompt() -> str:
    """Build system prompt from base preamble + live skill index."""
    from sophonic import skills as _skills
    base = (
        "You are Sophonic, a personal AI assistant integrated with Obsidian and your "
        "productivity tools. You help manage tasks, reminders, calendar, messages, and "
        "meeting notes. Always read from tools before answering about current state.\n\n"
    )
    idx = _skills.index()
    return base + idx if idx else base


def _py_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Map a Python type annotation to a JSON Schema fragment."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[X] / X | None
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            schema = _py_to_json_schema(non_none[0])
            return schema
        return {"type": "string"}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is date:
        return {"type": "string", "description": "ISO date YYYY-MM-DD"}

    if origin is list:
        item_schema = _py_to_json_schema(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    return {"type": "string"}


def _build_tools(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Anthropic tool definitions with proper JSON Schema from type hints."""
    tools = []
    for name, fn in registry.items():
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        sig = inspect.signature(fn)

        props: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            annotation = hints.get(param_name, inspect.Parameter.empty)
            schema = _py_to_json_schema(annotation)
            # Add param name as description if no dedicated description key
            if "description" not in schema:
                schema["description"] = param_name.replace("_", " ")
            props[param_name] = schema
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        tools.append({
            "name": name,
            "description": (fn.__doc__ or name).strip().split("\n")[0],
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        })
    return tools


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=key)


def ask(prompt: str, registry: dict[str, Any] | None = None) -> str:
    """Run a prompt through Claude with the tool-use loop. Return the final text."""
    from sophonic.tools import build_registry
    from sophonic import skills as _skills

    reg = registry or build_registry()
    reg = {**reg, "skill_load": _skills.skill_load}
    client = _client()
    cfg = load_config().llm
    tools = _build_tools(reg)

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    while True:
        response = client.messages.create(
            model=cfg.model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _build_system_prompt(),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=tools,  # type: ignore[arg-type]
            messages=messages,
        )

        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append({"id": block.id, "name": block.name, "input": block.input})

        if response.stop_reason == "end_turn" or not tool_uses:
            return "\n".join(text_parts)

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tu in tool_uses:
            fn = reg.get(tu["name"])
            if fn is None:
                result: Any = {"error": f"Unknown tool: {tu['name']}"}
            else:
                try:
                    result = fn(**tu["input"])
                except Exception as exc:
                    result = {"error": str(exc)}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})
