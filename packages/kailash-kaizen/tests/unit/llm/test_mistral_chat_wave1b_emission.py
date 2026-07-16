"""#1720 Wave-1b — mistral_chat completion-shaping EMISSION + PARSE.

Behavioral tests for the Mistral chat wire adapter's Wave-1b additions.
Mistral's ``/v1/chat/completions`` is OpenAI-schema-compatible with a handful
of provider-specific deltas the emission MUST honour:

* ``tools`` — OpenAI function-schema list, verbatim passthrough (truthiness
  guard so ``tools=[]`` emits nothing).
* ``tool_choice`` — Mistral's forced-tool value is ``"any"`` (NOT OpenAI's
  ``"required"``); the adapter maps ``"required"->"any"``, passes
  ``"auto"/"none"/"any"`` through, defaults to ``"any"`` when tools are set +
  choice unset, and emits ``tool_choice`` ONLY alongside a non-empty tools list.
* ``response_format`` — ``{"type": "json_object"}`` verbatim passthrough
  (truthiness guard).
* ``seed`` — emitted under Mistral's ``random_seed`` key (NOT ``seed``);
  ``frequency_penalty`` / ``presence_penalty`` / ``n`` share the OpenAI names.
* ``top_k`` and ``logit_bias`` — UNSUPPORTED by Mistral → NEVER emitted.

``parse_response`` surfaces ``choices[0].message.tool_calls`` under the
``"tool_calls"`` key in the canonical normalized shape (``arguments`` is a
JSON-encoded string), as plain JSON-serializable dicts.

All assertions are behavioral (construct → call → assert the produced dict),
not source-grep. No real model names are hardcoded (env-models.md) — the tests
use ``"test-model"``.
"""

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import mistral_chat


def _base_messages():
    return [{"role": "user", "content": "hi"}]


@pytest.mark.unit
def test_emits_tools_response_format_and_sampling_fields():
    """Set fields emit under Mistral's key names with the right values; seed is
    written under ``random_seed`` (the Mistral delta)."""
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
        frequency_penalty=0.5,
        presence_penalty=0.25,
        n=2,
    )
    payload = mistral_chat.build_request_payload(request)

    assert payload["tools"] == tools
    # Explicit tool_choice is honored ("auto" passes through).
    assert payload["tool_choice"] == "auto"
    assert payload["response_format"] == {"type": "json_object"}
    # Mistral's seed parameter is `random_seed`, NOT `seed`.
    assert payload["random_seed"] == 7
    assert "seed" not in payload
    assert payload["frequency_penalty"] == 0.5
    assert payload["presence_penalty"] == 0.25
    assert payload["n"] == 2


@pytest.mark.unit
def test_tool_choice_required_maps_to_any():
    """OpenAI's forced-tool value 'required' MUST map to Mistral's 'any'."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice="required",
    )
    payload = mistral_chat.build_request_payload(request)
    assert payload["tool_choice"] == "any"


@pytest.mark.unit
def test_tool_choice_defaults_to_any_when_tools_set_and_choice_none():
    """The pinned Wave-1a legacy default expressed in Mistral's vocabulary:
    tools present + tool_choice unset → tool_choice='any' (force a tool)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        # tool_choice deliberately unset
    )
    payload = mistral_chat.build_request_payload(request)
    assert payload["tool_choice"] == "any"


@pytest.mark.unit
def test_tool_choice_auto_none_any_pass_through():
    """Mistral-native string values pass through unchanged."""
    for choice in ("auto", "none", "any"):
        request = CompletionRequest(
            model="test-model",
            messages=_base_messages(),
            tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
            tool_choice=choice,
        )
        payload = mistral_chat.build_request_payload(request)
        assert payload["tool_choice"] == choice


@pytest.mark.unit
def test_tool_choice_unknown_string_falls_back_to_any():
    """An unknown tool_choice string falls back to the safe forced default
    'any' (never a shape Mistral would reject)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice="banana",
    )
    payload = mistral_chat.build_request_payload(request)
    assert payload["tool_choice"] == "any"


@pytest.mark.unit
def test_tool_choice_named_tool_dict_passes_through():
    """A named-tool forced-selection dict passes through in the OpenAI-shaped
    object form Mistral accepts."""
    named = {"type": "function", "function": {"name": "get_weather"}}
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[
            {"type": "function", "function": {"name": "get_weather", "parameters": {}}}
        ],
        tool_choice=named,
    )
    payload = mistral_chat.build_request_payload(request)
    assert payload["tool_choice"] == named


@pytest.mark.unit
def test_empty_tools_emits_nothing():
    """An explicitly-set EMPTY tools list emits neither tools nor tool_choice
    (truthiness guard, not `is not None`)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[],
        tool_choice="any",
    )
    payload = mistral_chat.build_request_payload(request)
    assert "tools" not in payload
    assert "tool_choice" not in payload


@pytest.mark.unit
def test_tool_choice_not_emitted_without_tools():
    """tool_choice is meaningless without tools — emitted ONLY alongside a
    non-empty tools list. A standalone tool_choice (any value) is dropped."""
    for choice in (
        "none",
        "required",
        "auto",
        "any",
        {"type": "function", "function": {"name": "f"}},
    ):
        request = CompletionRequest(
            model="test-model",
            messages=_base_messages(),
            tool_choice=choice,
        )
        payload = mistral_chat.build_request_payload(request)
        assert (
            "tool_choice" not in payload
        ), f"tool_choice={choice!r} leaked without tools"
        assert "tools" not in payload


@pytest.mark.unit
def test_empty_response_format_emits_nothing():
    """An empty response_format={} (set but degenerate) emits nothing."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={},
    )
    payload = mistral_chat.build_request_payload(request)
    assert "response_format" not in payload


@pytest.mark.unit
def test_top_k_is_never_emitted():
    """Mistral's chat API does not support top_k — it MUST NOT appear in the
    payload even when the CompletionRequest carries it."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        top_k=40,
    )
    payload = mistral_chat.build_request_payload(request)
    assert "top_k" not in payload


@pytest.mark.unit
def test_logit_bias_is_never_emitted():
    """Mistral has no logit_bias equivalent — it MUST NOT appear in the payload
    even when the CompletionRequest carries it."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        logit_bias={"123": -1.0},
    )
    payload = mistral_chat.build_request_payload(request)
    assert "logit_bias" not in payload


@pytest.mark.unit
def test_parse_response_surfaces_tool_calls_in_canonical_shape():
    """A fake Mistral response with message.tool_calls parses into the canonical
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

    parsed = mistral_chat.parse_response(response)

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
def test_parse_response_coerces_dict_arguments_to_json_string():
    """A non-conformant Mistral response returning ``arguments`` as a dict is
    coerced to a JSON string so the canonical invariant holds."""
    response = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_xyz",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": {"q": "kailash"},
                            },
                        }
                    ],
                },
            }
        ],
        "model": "test-model",
    }
    parsed = mistral_chat.parse_response(response)
    tc = parsed["tool_calls"][0]
    assert isinstance(tc["function"]["arguments"], str)
    assert json.loads(tc["function"]["arguments"]) == {"q": "kailash"}


@pytest.mark.unit
def test_parse_response_omits_tool_calls_key_when_absent():
    """No tool_calls in the response → no 'tool_calls' key in the parsed dict;
    the existing {text, usage, stop_reason, model} keys are intact."""
    response = {
        "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "model": "test-model",
    }
    parsed = mistral_chat.parse_response(response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "hello"
    assert set(parsed.keys()) == {"text", "usage", "stop_reason", "model"}
