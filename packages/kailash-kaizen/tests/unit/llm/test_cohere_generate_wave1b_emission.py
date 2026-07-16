# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-1b — cohere_generate tool emission + tool-call parse.

Behavioral coverage for the CohereGenerate (v1 ``/chat``) wire adapter's
completion-shaping translation (OpenAI-shaped ``CompletionRequest`` fields ->
Cohere v1 ``/chat`` schema) and the canonical tool-call parse.

Cohere v1 diverges from OpenAI on documented field names:

* tools -> ``[{name, description, parameter_definitions}]`` (Python-style
  parameter types), NOT the OpenAI function-schema.
* ``tool_choice`` does NOT exist on v1 ``/chat`` (v2-only) -> NEVER emitted.
* structured output -> ``response_format={"type": "json_object"[, "schema"]}``.
* top_k -> ``k``; ``seed`` / ``frequency_penalty`` / ``presence_penalty``
  supported.
* ``n`` and ``logit_bias`` are UNSUPPORTED -> NEVER emitted.
"""

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import cohere_generate


def _base_request(**overrides) -> CompletionRequest:
    fields = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
    }
    fields.update(overrides)
    return CompletionRequest(**fields)


def _all_keys(obj) -> set:
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(k)
            found |= _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _all_keys(v)
    return found


# --- Emission: tools -> Cohere v1 parameter_definitions shape -----------------


def test_tools_translated_to_cohere_v1_shape():
    req = _base_request(
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Look up the weather",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "City name"},
                            "days": {"type": "integer"},
                        },
                        "required": ["city"],
                    },
                },
            }
        ],
        top_k=40,
    )
    payload = cohere_generate.build_request_payload(req)

    assert payload["tools"] == [
        {
            "name": "get_weather",
            "description": "Look up the weather",
            "parameter_definitions": {
                "city": {
                    "description": "City name",
                    "type": "str",
                    "required": True,
                },
                "days": {
                    "description": "",
                    "type": "int",
                    "required": False,
                },
            },
        }
    ]
    # Cohere names top_k `k`.
    assert payload["k"] == 40
    # top_p stays `p` (existing behavior, not clobbered by top_k).
    assert "top_k" not in _all_keys(payload)


def test_tools_missing_description_and_parameters_default():
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f"}}],
    )
    payload = cohere_generate.build_request_payload(req)
    assert payload["tools"] == [
        {"name": "f", "description": "", "parameter_definitions": {}}
    ]


def test_json_schema_type_mapping_covers_families():
    req = _base_request(
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "f",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "s": {"type": "string"},
                            "i": {"type": "integer"},
                            "n": {"type": "number"},
                            "b": {"type": "boolean"},
                            "a": {"type": "array"},
                            "o": {"type": "object"},
                        },
                    },
                },
            }
        ],
    )
    payload = cohere_generate.build_request_payload(req)
    defs = payload["tools"][0]["parameter_definitions"]
    assert defs["s"]["type"] == "str"
    assert defs["i"]["type"] == "int"
    assert defs["n"]["type"] == "float"
    assert defs["b"]["type"] == "bool"
    assert defs["a"]["type"] == "list"
    assert defs["o"]["type"] == "dict"


# --- Emission: empty-collection truthiness guards -----------------------------


def test_empty_tools_list_emits_nothing():
    req = _base_request(tools=[])
    payload = cohere_generate.build_request_payload(req)
    assert "tools" not in payload


def test_empty_response_format_emits_nothing():
    req = _base_request(response_format={})
    payload = cohere_generate.build_request_payload(req)
    assert "response_format" not in payload


def test_empty_logit_bias_emits_nothing():
    # logit_bias is unsupported on v1 anyway; empty must also be silent.
    req = _base_request(logit_bias={})
    payload = cohere_generate.build_request_payload(req)
    assert "logit_bias" not in _all_keys(payload)


# --- Emission: tool_choice is NEVER emitted (v2-only feature) ------------------


@pytest.mark.parametrize("choice", ["auto", "required", "none", None])
def test_tool_choice_never_emitted_even_with_tools(choice):
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice=choice,
    )
    payload = cohere_generate.build_request_payload(req)
    # Cohere v1 /chat has no tool_choice parameter — must never appear.
    assert "tool_choice" not in _all_keys(payload)
    # ...but the tools themselves are still emitted.
    assert "tools" in payload


def test_forced_tool_dict_choice_still_omits_tool_choice():
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice={"type": "function", "function": {"name": "f"}},
    )
    payload = cohere_generate.build_request_payload(req)
    assert "tool_choice" not in _all_keys(payload)


# --- Emission: response_format -> Cohere JSON mode ----------------------------


def test_response_format_json_object():
    req = _base_request(response_format={"type": "json_object"})
    payload = cohere_generate.build_request_payload(req)
    assert payload["response_format"] == {"type": "json_object"}


def test_response_format_json_schema_carries_schema():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    req = _base_request(
        response_format={
            "type": "json_schema",
            "json_schema": {"schema": schema},
        }
    )
    payload = cohere_generate.build_request_payload(req)
    assert payload["response_format"] == {"type": "json_object", "schema": schema}


def test_response_format_text_type_not_coerced():
    # OpenAI {"type": "text"} must NOT force JSON mode (v1 defaults to text).
    req = _base_request(response_format={"type": "text"})
    payload = cohere_generate.build_request_payload(req)
    assert "response_format" not in payload


# --- Emission: sampling fields use Cohere's documented names ------------------


def test_sampling_fields_emitted_with_cohere_names():
    req = _base_request(
        seed=7,
        frequency_penalty=0.5,
        presence_penalty=0.25,
        top_k=30,
    )
    payload = cohere_generate.build_request_payload(req)
    assert payload["seed"] == 7
    assert payload["frequency_penalty"] == 0.5
    assert payload["presence_penalty"] == 0.25
    assert payload["k"] == 30


# --- Emission: unsupported fields are NEVER emitted ---------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("n", 3),
        ("logit_bias", {"123": -1.0}),
    ],
)
def test_unsupported_fields_never_emitted(field, value):
    req = _base_request(**{field: value})
    payload = cohere_generate.build_request_payload(req)
    assert field not in _all_keys(payload), (
        f"cohere_generate emitted unsupported field {field!r} — Cohere v1 "
        f"/chat does not accept it."
    )


def test_unset_new_fields_never_appear():
    # A plain request emits none of the Wave-1b keys.
    payload = cohere_generate.build_request_payload(_base_request())
    leaked = _all_keys(payload) & {
        "tools",
        "tool_choice",
        "response_format",
        "seed",
        "logit_bias",
        "frequency_penalty",
        "presence_penalty",
        "n",
        "k",
    }
    assert not leaked, f"unset Wave-1b field(s) leaked: {sorted(leaked)}"


# --- Parse: Cohere v1 tool_calls -> canonical tool_calls ----------------------


def test_tool_calls_parse_to_canonical_shape():
    fake_response = {
        "text": "",
        "tool_calls": [
            {"name": "get_weather", "parameters": {"city": "Paris", "unit": "c"}},
        ],
        "finish_reason": "COMPLETE",
        "model": "test-model",
        "meta": {"billed_units": {"input_tokens": 10, "output_tokens": 5}},
    }
    parsed = cohere_generate.parse_response(fake_response)

    assert parsed["tool_calls"] == [
        {
            "id": "call_0",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": json.dumps({"city": "Paris", "unit": "c"}),
            },
        }
    ]
    # arguments MUST be a JSON string, not the raw dict.
    args = parsed["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str)
    assert json.loads(args) == {"city": "Paris", "unit": "c"}

    # Existing parsed keys unchanged.
    assert parsed["text"] == ""
    assert parsed["stop_reason"] == "COMPLETE"
    assert parsed["model"] == "test-model"
    assert parsed["usage"] == {"input_tokens": 10, "output_tokens": 5}


def test_multiple_tool_calls_all_parsed_with_synthesized_ids():
    fake_response = {
        "tool_calls": [
            {"name": "a", "parameters": {"x": 1}},
            {"name": "b", "parameters": {}},
        ],
    }
    parsed = cohere_generate.parse_response(fake_response)
    assert [tc["id"] for tc in parsed["tool_calls"]] == ["call_0", "call_1"]
    assert all(isinstance(tc["id"], str) and tc["id"] for tc in parsed["tool_calls"])
    assert parsed["tool_calls"][1]["function"]["arguments"] == json.dumps({})


def test_no_tool_calls_omits_tool_calls_key():
    fake_response = {
        "text": "just text",
        "meta": {"billed_units": {"input_tokens": 1, "output_tokens": 1}},
    }
    parsed = cohere_generate.parse_response(fake_response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "just text"


def test_missing_parameters_defaults_to_empty_json_object():
    fake_response = {"tool_calls": [{"name": "f"}]}
    parsed = cohere_generate.parse_response(fake_response)
    assert parsed["tool_calls"][0]["function"]["arguments"] == json.dumps({})
    assert parsed["tool_calls"][0]["function"]["name"] == "f"
