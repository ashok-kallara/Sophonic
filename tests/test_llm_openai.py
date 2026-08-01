"""Tests for the OpenAI-compatible LLM backend."""

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sophonic.config import Config, LLMConfig


# ── fakes ──────────────────────────────────────────────────────────────────────

class _FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeOpenAIClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=_FakeCompletions(responses))


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _response(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


# ── _build_openai_tools ─────────────────────────────────────────────────────────

def _sample(text: str, count: int = 1) -> dict:
    """Sample tool."""
    return {"text": text, "count": count}


def test_build_openai_tools_wraps_anthropic_schema():
    from sophonic.llm import _build_openai_tools, _build_tools

    reg = {"sample": _sample}
    anthropic_tools = _build_tools(reg)
    openai_tools = _build_openai_tools(reg)

    assert len(openai_tools) == 1
    t = openai_tools[0]
    assert t["type"] == "function"
    assert t["function"]["name"] == "sample"
    assert t["function"]["description"] == "Sample tool."
    # same JSON Schema is reused verbatim
    assert t["function"]["parameters"] == anthropic_tools[0]["input_schema"]
    assert t["function"]["parameters"]["properties"]["count"]["type"] == "integer"


# ── _ask_openai tool loop ─────────────────────────────────────────────────────

def test_ask_openai_runs_tool_loop():
    from sophonic import llm

    calls: list[dict] = []

    def echo(text: str) -> dict:
        """Echo tool."""
        calls.append({"text": text})
        return {"echoed": text}

    responses = [
        _response(tool_calls=[_tool_call("call_1", "echo", '{"text": "hi"}')]),
        _response(content="all done"),
    ]
    fake = _FakeOpenAIClient(responses)
    cfg = LLMConfig(provider="openai", model="gpt-4o")

    with patch.object(llm, "_openai_client", return_value=fake):
        result = llm._ask_openai("hello", {"echo": echo}, "system", cfg)

    assert result == "all done"
    assert calls == [{"text": "hi"}]  # tool actually executed with parsed args

    # first request carried system + user messages and function tools
    first = fake.chat.completions.calls[0]
    assert first["model"] == "gpt-4o"
    assert first["max_tokens"] == 4096
    assert first["messages"][0] == {"role": "system", "content": "system"}
    assert first["messages"][1] == {"role": "user", "content": "hello"}
    assert first["tools"][0]["type"] == "function"

    # second request appended the assistant tool_call turn and the tool result
    second = fake.chat.completions.calls[1]
    roles = [m["role"] for m in second["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert second["messages"][3]["tool_call_id"] == "call_1"


def test_ask_openai_returns_text_without_tool_calls():
    from sophonic import llm

    fake = _FakeOpenAIClient([_response(content="just text")])
    cfg = LLMConfig(provider="openai", model="gpt-4o")

    with patch.object(llm, "_openai_client", return_value=fake):
        result = llm._ask_openai("hi", {}, "system", cfg)

    assert result == "just text"


def test_ask_openai_handles_bad_tool_arguments():
    from sophonic import llm

    def noargs() -> dict:
        """No-arg tool."""
        return {"ok": True}

    responses = [
        _response(tool_calls=[_tool_call("call_1", "noargs", "not-json")]),
        _response(content="recovered"),
    ]
    fake = _FakeOpenAIClient(responses)
    cfg = LLMConfig(provider="openai", model="gpt-4o")

    with patch.object(llm, "_openai_client", return_value=fake):
        result = llm._ask_openai("go", {"noargs": noargs}, "system", cfg)

    assert result == "recovered"


# ── dispatch ──────────────────────────────────────────────────────────────────

def test_ask_dispatches_to_openai_when_provider_is_openai():
    from sophonic import llm

    fake = _FakeOpenAIClient([_response(content="from openai")])
    cfg = Config(llm=LLMConfig(provider="openai", model="gpt-4o"))

    with patch.object(llm, "load_config", return_value=cfg), \
         patch.object(llm, "_openai_client", return_value=fake), \
         patch("sophonic.tools.build_registry", return_value={}), \
         patch("sophonic.skills.discover", return_value=[]):
        result = llm.ask("hello")

    assert result == "from openai"


def test_ask_dispatches_to_openai_client_when_provider_is_litellm():
    """litellm speaks the OpenAI wire format, so it routes through the OpenAI client."""
    from sophonic import llm

    fake = _FakeOpenAIClient([_response(content="via litellm")])
    cfg = Config(llm=LLMConfig(provider="litellm", model="bedrock/claude", api_base="http://proxy"))

    with patch.object(llm, "load_config", return_value=cfg), \
         patch.object(llm, "_openai_client", return_value=fake), \
         patch("sophonic.tools.build_registry", return_value={}), \
         patch("sophonic.skills.discover", return_value=[]):
        result = llm.ask("hello")

    assert result == "via litellm"


def test_ask_defaults_to_anthropic():
    """Default config (no provider) must still use the Anthropic client."""
    from sophonic import llm

    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text="from anthropic")],
            )

    fake_anthropic = SimpleNamespace(messages=FakeMessages())

    with patch.object(llm, "load_config", return_value=Config()), \
         patch.object(llm, "_client", return_value=fake_anthropic), \
         patch("sophonic.tools.build_registry", return_value={}), \
         patch("sophonic.skills.discover", return_value=[]):
        result = llm.ask("hello")

    assert result == "from anthropic"


# ── missing dependency guard ───────────────────────────────────────────────────

def test_openai_client_missing_package_raises_clear_error():
    from sophonic import llm

    cfg = LLMConfig(provider="openai")
    # openai is a core dependency; if it can't import, surface a clear reinstall message.
    with patch.dict(sys.modules, {"openai": None}):
        with pytest.raises(RuntimeError, match=r"reinstall Sophonic"):
            llm._openai_client(cfg)


# ── config validation ──────────────────────────────────────────────────────────

def test_llm_config_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Invalid llm provider"):
        LLMConfig(provider="bad")


def test_llm_config_accepts_litellm():
    assert LLMConfig(provider="litellm").provider == "litellm"


def test_llm_config_defaults_unchanged():
    cfg = LLMConfig()
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.max_tokens == 4096
    assert cfg.api_base is None
