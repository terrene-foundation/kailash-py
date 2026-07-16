"""#1720 Wave-1b — openai_chat completion-shaping EMISSION + PARSE.

Behavioral tests for the OpenAI chat wire adapter's Wave-1b additions:

* ``build_request_payload`` EMITS the completion-shaping fields
  (``tools``/``tool_choice``/``response_format``/``seed``/``logit_bias``/
  ``frequency_penalty``/``presence_penalty``/``n``) when set, with OpenAI's
  canonical key names; preserves the legacy ``tool_choice="required"``-when-
  tools-present default; and NEVER emits ``top_k`` (unsupported by the OpenAI
  chat API).
* ``parse_response`` surfaces ``choices[0].message.tool_calls`` under the
  ``"tool_calls"`` key in the canonical normalized shape (``arguments`` is a
  JSON-encoded string), as plain JSON-serializable dicts.

All assertions are behavioral (construct → call → assert the produced dict),
not source-grep. No real model names are hardcoded (env-models.md) — the tests
use ``"test-model"``.
"""

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import openai_chat


def _base_messages():
    return [{"role": "user", "content": "hi"}]


@pytest.mark.unit
def test_emits_tools_response_format_and_sampling_fields():
    """Set fields emit under OpenAI's canonical key names with right values."""
    tools = [
        {
            "type": "function",
            "function": {"name": "get_weather", "parameters": {"type": "object"}},
        }
    ]
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=tools,
        tool_choice="auto",
        response_format={"type": "json_object"},
        seed=7,
        logit_bias={"123": -1.0},
        frequency_penalty=0.5,
        presence_penalty=0.25,
        n=2,
    )
    payload = openai_chat.build_request_payload(request)

    assert payload["tools"] == tools
    # Explicit tool_choice is honored (not overridden by the "required" default).
    assert payload["tool_choice"] == "auto"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["seed"] == 7
    assert payload["logit_bias"] == {"123": -1.0}
    assert payload["frequency_penalty"] == 0.5
    assert payload["presence_penalty"] == 0.25
    assert payload["n"] == 2


@pytest.mark.unit
def test_tool_choice_defaults_to_required_when_tools_set_and_choice_none():
    """The pinned Wave-1a legacy default: tools present + tool_choice unset →
    tool_choice='required'."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        # tool_choice deliberately unset
    )
    payload = openai_chat.build_request_payload(request)
    assert payload["tool_choice"] == "required"


@pytest.mark.unit
def test_tool_choice_not_emitted_when_no_tools_and_unset():
    """No tools + no explicit tool_choice → tool_choice key is absent."""
    request = CompletionRequest(model="test-model", messages=_base_messages())
    payload = openai_chat.build_request_payload(request)
    assert "tool_choice" not in payload
    assert "tools" not in payload


@pytest.mark.unit
def test_tool_choice_not_emitted_without_tools():
    """tool_choice is meaningless without tools — emitted ONLY alongside a
    non-empty tools list, matching the anthropic/google adapters (four-axis
    consistency). A standalone tool_choice (even the benign 'none') is dropped;
    a forced 'required'/named choice with no tools would be an invalid request.
    (Round-3 convergence fix on PR #1776.)"""
    for choice in (
        "none",
        "required",
        "auto",
        {"type": "function", "function": {"name": "f"}},
    ):
        request = CompletionRequest(
            model="test-model",
            messages=_base_messages(),
            tool_choice=choice,
        )
        payload = openai_chat.build_request_payload(request)
        assert (
            "tool_choice" not in payload
        ), f"tool_choice={choice!r} leaked without tools"
        assert "tools" not in payload


@pytest.mark.unit
def test_top_k_is_never_emitted():
    """OpenAI chat API does not support top_k — it MUST NOT appear in the
    payload even when the CompletionRequest carries it."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        top_k=40,
    )
    payload = openai_chat.build_request_payload(request)
    assert "top_k" not in payload


@pytest.mark.unit
def test_parse_response_surfaces_tool_calls_in_canonical_shape():
    """A fake OpenAI response with message.tool_calls parses into the canonical
    normalized shape; arguments stays a JSON-encoded string; entries are plain
    JSON-serializable dicts."""
    arguments_json = json.dumps({"city": "Paris"})
    response = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc123",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": arguments_json,
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        "model": "test-model",
    }

    parsed = openai_chat.parse_response(response)

    assert parsed["tool_calls"] == [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": arguments_json},
        }
    ]
    tc = parsed["tool_calls"][0]
    # arguments is a JSON-encoded string, not a dict.
    assert isinstance(tc["function"]["arguments"], str)
    assert json.loads(tc["function"]["arguments"]) == {"city": "Paris"}
    # The result must be JSON-serializable (plain dicts, no SDK objects).
    json.dumps(parsed)
    # Existing keys are unchanged.
    assert parsed["text"] == ""
    assert parsed["stop_reason"] == "tool_calls"
    assert parsed["model"] == "test-model"
    assert parsed["usage"] == {
        "input_tokens": 5,
        "output_tokens": 3,
        "total_tokens": 8,
    }


@pytest.mark.unit
def test_parse_response_omits_tool_calls_key_when_absent():
    """No tool_calls in the response → no 'tool_calls' key in the parsed dict;
    the existing {text, usage, stop_reason, model} keys are intact."""
    response = {
        "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "model": "test-model",
    }
    parsed = openai_chat.parse_response(response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "hello"
    assert set(parsed.keys()) == {"text", "usage", "stop_reason", "model"}
