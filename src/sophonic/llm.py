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

from sophonic.config import OPENAI_COMPATIBLE_PROVIDERS, load_config, resolve_llm_api_key

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


def _build_openai_tools(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Wrap the Anthropic-format tools as OpenAI function tools (same JSON Schema)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in _build_tools(registry)
    ]


def _execute_tool(registry: dict[str, Any], name: str, tool_input: dict[str, Any]) -> Any:
    """Look up and call a tool by name, returning its result or an error dict."""
    fn = registry.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**tool_input)
    except Exception as exc:  # surface tool failures back to the model
        return {"error": str(exc)}


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=resolve_llm_api_key("anthropic"))


def _openai_client(cfg: Any):
    """Build an OpenAI-compatible client. Lazily imports the optional `openai` package."""
    try:
        import openai
    except ImportError as exc:  # openai is a core dependency; a miss means a broken install
        raise RuntimeError(
            "The 'openai' package failed to import — reinstall Sophonic "
            "(`uv sync`, or `uv tool install --force .`)."
        ) from exc
    return openai.OpenAI(
        api_key=resolve_llm_api_key(cfg.provider),
        base_url=cfg.api_base or None,
    )


def ask(prompt: str, registry: dict[str, Any] | None = None) -> str:
    """Run a prompt through the configured LLM with the tool-use loop. Return the final text."""
    from sophonic.tools import build_registry
    from sophonic import skills as _skills

    reg = registry or build_registry()
    reg = {**reg, "skill_load": _skills.skill_load}
    cfg = load_config().llm
    system_prompt = _build_system_prompt()

    # openai and litellm both speak the OpenAI wire format (LiteLLM proxy is compatible).
    if cfg.provider in OPENAI_COMPATIBLE_PROVIDERS:
        return _ask_openai(prompt, reg, system_prompt, cfg)
    return _ask_anthropic(prompt, reg, system_prompt, cfg)


def _ask_anthropic(prompt: str, reg: dict[str, Any], system_prompt: str, cfg: Any) -> str:
    """Anthropic native tool-use loop with prompt caching."""
    client = _client()
    tools = _build_tools(reg)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]

    while True:
        response = client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
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
            result = _execute_tool(reg, tu["name"], tu["input"])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result, default=str),
            })
        messages.append({"role": "user", "content": tool_results})


def _ask_openai(prompt: str, reg: dict[str, Any], system_prompt: str, cfg: Any) -> str:
    """OpenAI-compatible chat-completions tool-use loop (works with any OpenAI-format endpoint)."""
    client = _openai_client(cfg)
    tools = _build_openai_tools(reg)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    while True:
        response = client.chat.completions.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            messages=messages,
            tools=tools,  # type: ignore[arg-type]
        )
        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            return msg.content or ""

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _execute_tool(reg, tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, default=str),
            })
