# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-1b — ollama_native completion-shaping EMISSION + PARSE.

Behavioral tests for the Ollama Native wire adapter's Wave-1b additions:

* ``build_request_payload`` EMITS the completion-shaping fields, translated to
  Ollama's ``/api/chat`` schema:
    - ``tools`` -> top-level ``tools`` (OpenAI function-schema passthrough).
    - ``tool_choice`` -> OMITTED (Ollama has no such parameter — never faked).
    - ``response_format`` -> top-level ``format`` ("json" for json_object; the
      schema object for json_schema).
    - ``seed``/``top_k``/``frequency_penalty``/``presence_penalty`` -> merged
      into ``options`` under Ollama's native names, never clobbering
      temperature/top_p/num_predict/stop.
    - ``n`` / ``logit_bias`` -> OMITTED (no Ollama equivalent).
* ``parse_response`` surfaces ``message.tool_calls`` (Ollama gives
  ``function.arguments`` as a DICT and no call id) in the canonical normalized
  shape: ``arguments`` json.dumps'd to a string, a synthesized ``call_{i}`` id.

All assertions are behavioral (construct -> call -> assert the produced dict),
not source-grep. No real model names are hardcoded (env-models.md) — the tests
use ``"test-model"``.
"""

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import ollama_native


def _base_messages():
    return [{"role": "user", "content": "hi"}]


@pytest.mark.unit
def test_emits_tools_passthrough_and_omits_tool_choice():
    """tools pass through verbatim (OpenAI function-schema); tool_choice is
    OMITTED because Ollama's /api/chat has no such parameter."""
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
        tool_choice="required",  # set, but Ollama has no tool_choice — must drop
    )
    payload = ollama_native.build_request_payload(request)

    assert payload["tools"] == tools
    assert "tool_choice" not in payload


@pytest.mark.unit
def test_empty_tools_list_emits_nothing():
    """An explicitly-set empty tools list emits no tools key (truthiness guard)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[],
    )
    payload = ollama_native.build_request_payload(request)
    assert "tools" not in payload
    assert "tool_choice" not in payload


@pytest.mark.unit
def test_response_format_json_object_maps_to_format_json():
    """{"type": "json_object"} -> Ollama's top-level format: "json"."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={"type": "json_object"},
    )
    payload = ollama_native.build_request_payload(request)
    assert payload["format"] == "json"
    # Not emitted under the OpenAI key name.
    assert "response_format" not in payload


@pytest.mark.unit
def test_response_format_json_schema_maps_to_format_schema_object():
    """A json_schema response_format -> Ollama format set to the schema object."""
    schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "loc", "schema": schema},
        },
    )
    payload = ollama_native.build_request_payload(request)
    assert payload["format"] == schema


@pytest.mark.unit
def test_response_format_json_schema_without_schema_falls_back_to_json():
    """A json_schema type carrying no extractable schema falls back to "json"
    (still forces structured output rather than emitting a malformed format)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={"type": "json_schema"},
    )
    payload = ollama_native.build_request_payload(request)
    assert payload["format"] == "json"


@pytest.mark.unit
def test_response_format_text_type_emits_nothing():
    """A non-JSON response_format type must NOT force json mode — Ollama
    defaults to free text, so no format key is emitted."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={"type": "text"},
    )
    payload = ollama_native.build_request_payload(request)
    assert "format" not in payload


@pytest.mark.unit
def test_empty_response_format_emits_nothing():
    """An empty response_format={} (no type) emits nothing (truthiness guard)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={},
    )
    payload = ollama_native.build_request_payload(request)
    assert "format" not in payload


@pytest.mark.unit
def test_sampling_fields_merge_into_options_under_ollama_names():
    """seed/top_k/frequency_penalty/presence_penalty land under options with
    Ollama's native names, MERGED with the pre-existing temperature/top_p/etc.
    without clobbering them."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        temperature=0.7,
        top_p=0.9,
        max_tokens=128,
        stop=["END"],
        seed=7,
        top_k=40,
        frequency_penalty=0.5,
        presence_penalty=0.25,
    )
    payload = ollama_native.build_request_payload(request)
    options = payload["options"]

    # Pre-existing options preserved (not clobbered by the merge).
    assert options["temperature"] == 0.7
    assert options["top_p"] == 0.9
    assert options["num_predict"] == 128
    assert options["stop"] == ["END"]
    # Wave-1b sampling merged under Ollama's native option names.
    assert options["seed"] == 7
    assert options["top_k"] == 40
    assert options["frequency_penalty"] == 0.5
    assert options["presence_penalty"] == 0.25


@pytest.mark.unit
def test_n_and_logit_bias_are_never_emitted():
    """Ollama supports neither multiple completions (n) nor logit_bias — both
    MUST be absent from the payload (and never leak into options)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        n=3,
        logit_bias={"123": -1.0},
    )
    payload = ollama_native.build_request_payload(request)
    assert "n" not in payload
    assert "logit_bias" not in payload
    # No options dict is created solely from unsupported fields.
    assert "n" not in payload.get("options", {})
    assert "logit_bias" not in payload.get("options", {})


@pytest.mark.unit
def test_parse_response_normalizes_dict_arguments_and_synthesizes_id():
    """Ollama returns tool_calls with function.arguments as a DICT and no call
    id; parse normalizes arguments to a JSON string and synthesizes call_{i}."""
    response = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_weather",
                        "arguments": {"city": "Paris"},
                    }
                }
            ],
        },
        "model": "test-model",
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 5,
        "eval_count": 3,
    }

    parsed = ollama_native.parse_response(response)

    assert parsed["tool_calls"] == [
        {
            "id": "call_0",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": json.dumps({"city": "Paris"}),
            },
        }
    ]
    tc = parsed["tool_calls"][0]
    # arguments is a JSON-encoded string, not a dict.
    assert isinstance(tc["function"]["arguments"], str)
    assert json.loads(tc["function"]["arguments"]) == {"city": "Paris"}
    # The result is JSON-serializable (plain dicts, no SDK objects).
    json.dumps(parsed)
    # Existing keys unchanged.
    assert parsed["text"] == ""
    assert parsed["stop_reason"] == "stop"
    assert parsed["model"] == "test-model"
    assert parsed["usage"] == {"input_tokens": 5, "output_tokens": 3}


@pytest.mark.unit
def test_parse_response_multiple_tool_calls_get_sequential_ids():
    """Two tool calls with no ids get call_0 and call_1."""
    response = {
        "message": {
            "content": "",
            "tool_calls": [
                {"function": {"name": "a", "arguments": {"x": 1}}},
                {"function": {"name": "b", "arguments": {"y": 2}}},
            ],
        },
        "done": True,
    }
    parsed = ollama_native.parse_response(response)
    ids = [tc["id"] for tc in parsed["tool_calls"]]
    assert ids == ["call_0", "call_1"]
    assert parsed["tool_calls"][1]["function"]["arguments"] == json.dumps({"y": 2})


@pytest.mark.unit
def test_parse_response_preserves_provider_supplied_id_and_string_arguments():
    """A variant that already sent an id + string arguments is passed through
    unchanged (no double-encoding, no id overwrite)."""
    args_str = json.dumps({"city": "Berlin"})
    response = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_native_xyz",
                    "function": {"name": "get_weather", "arguments": args_str},
                }
            ],
        },
        "done": True,
    }
    parsed = ollama_native.parse_response(response)
    tc = parsed["tool_calls"][0]
    assert tc["id"] == "call_native_xyz"
    # Already a string -> not re-encoded.
    assert tc["function"]["arguments"] == args_str


@pytest.mark.unit
def test_parse_response_omits_tool_calls_key_when_absent():
    """No tool_calls in the response -> no 'tool_calls' key; the pre-#1720
    parsed keys are intact."""
    response = {
        "message": {"role": "assistant", "content": "hello"},
        "model": "test-model",
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 1,
        "eval_count": 1,
    }
    parsed = ollama_native.parse_response(response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "hello"
    assert set(parsed.keys()) == {"text", "usage", "stop_reason", "model", "done"}
