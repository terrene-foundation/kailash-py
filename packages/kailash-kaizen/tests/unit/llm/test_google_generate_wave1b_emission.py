# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-1b — google_generate_content emission + parse behavioral tests.

Covers the OpenAI-shaped ``CompletionRequest`` -> Gemini translation for the
Wave-1b completion-shaping fields (tools, tool_choice, response_format, top_k,
seed, n, frequency_penalty, presence_penalty), the logit_bias non-emission, the
generationConfig MERGE (no clobber), and the functionCall -> canonical
normalized ``tool_calls`` parse. Wire adapter serves both GoogleGenerateContent
and VertexGenerateContent wires (same shaper).
"""

import json

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import google_generate_content as gg


def _base_messages():
    return [{"role": "user", "content": "hi"}]


def test_tools_translated_to_gemini_function_declarations():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Look up the weather",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    },
                },
            }
        ],
    )
    payload = gg.build_request_payload(req)

    assert "tools" in payload
    decls = payload["tools"][0]["functionDeclarations"]
    assert decls[0]["name"] == "get_weather"
    assert decls[0]["description"] == "Look up the weather"
    assert decls[0]["parameters"]["properties"]["city"]["type"] == "string"


def test_tool_description_and_parameters_default_when_absent():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "f"}}],
    )
    payload = gg.build_request_payload(req)
    decl = payload["tools"][0]["functionDeclarations"][0]
    assert decl["name"] == "f"
    assert decl["description"] == ""
    assert decl["parameters"] == {}


def test_tool_config_default_any_when_tools_set_no_choice():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "f"}}],
    )
    payload = gg.build_request_payload(req)
    assert payload["toolConfig"] == {"functionCallingConfig": {"mode": "ANY"}}


def test_tool_choice_string_modes_map_to_gemini():
    for openai_choice, gemini_mode in [
        ("auto", "AUTO"),
        ("required", "ANY"),
        ("none", "NONE"),
    ]:
        req = CompletionRequest(
            model="test-model",
            messages=_base_messages(),
            tools=[{"type": "function", "function": {"name": "f"}}],
            tool_choice=openai_choice,
        )
        payload = gg.build_request_payload(req)
        assert payload["toolConfig"]["functionCallingConfig"]["mode"] == gemini_mode


def test_forced_tool_dict_maps_to_any_with_allowed_names():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
        tool_choice={"type": "function", "function": {"name": "get_weather"}},
    )
    payload = gg.build_request_payload(req)
    cfg = payload["toolConfig"]["functionCallingConfig"]
    assert cfg["mode"] == "ANY"
    assert cfg["allowedFunctionNames"] == ["get_weather"]


def test_tool_config_absent_when_no_tools():
    # tool_choice with no tools is meaningless -> neither key emitted.
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tool_choice="required",
    )
    payload = gg.build_request_payload(req)
    assert "tools" not in payload
    assert "toolConfig" not in payload


def test_response_format_json_object_sets_response_mime_type():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={"type": "json_object"},
    )
    payload = gg.build_request_payload(req)
    gen = payload["generationConfig"]
    assert gen["responseMimeType"] == "application/json"
    assert "responseSchema" not in gen  # bare json_object has no schema


def test_response_format_json_schema_sets_response_schema():
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "resp", "schema": schema},
        },
    )
    payload = gg.build_request_payload(req)
    gen = payload["generationConfig"]
    assert gen["responseMimeType"] == "application/json"
    assert gen["responseSchema"] == schema


def test_response_format_empty_dict_emits_no_generation_config_keys():
    """/redteam Round-1 FIX 6a (#1720 Wave-1b): truthiness guard (not `is not
    None`) matches every sibling wire — an explicitly-set EMPTY
    `response_format={}` MUST emit nothing, same as an unset one."""
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={},
    )
    payload = gg.build_request_payload(req)
    assert "generationConfig" not in payload


def test_sampling_fields_merge_into_generation_config_without_clobber():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        temperature=0.7,
        top_p=0.9,
        max_tokens=128,
        top_k=40,
        seed=7,
        n=2,
        frequency_penalty=0.5,
        presence_penalty=0.25,
    )
    payload = gg.build_request_payload(req)
    gen = payload["generationConfig"]

    # Pre-#1720 keys survive (no clobber).
    assert gen["temperature"] == 0.7
    assert gen["topP"] == 0.9
    assert gen["maxOutputTokens"] == 128
    # Wave-1b sampling keys merged in with Gemini names.
    assert gen["topK"] == 40
    assert gen["seed"] == 7
    assert gen["candidateCount"] == 2  # Gemini's name for `n`
    assert gen["frequencyPenalty"] == 0.5
    assert gen["presencePenalty"] == 0.25


def test_logit_bias_never_emitted():
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        logit_bias={"123": -1.0},
        top_k=5,
    )
    payload = gg.build_request_payload(req)

    def _all_keys(obj):
        found = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                found.add(k)
                found |= _all_keys(v)
        elif isinstance(obj, list):
            for v in obj:
                found |= _all_keys(v)
        return found

    keys = _all_keys(payload)
    assert "logit_bias" not in keys
    assert "logitBias" not in keys
    # top_k still merged (Gemini supports it), so the request is not a no-op.
    assert payload["generationConfig"]["topK"] == 5


def test_full_wave1b_request_shapes_all_surfaces():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    req = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        temperature=0.3,
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice=None,  # default -> ANY
        response_format={"type": "json_schema", "json_schema": {"schema": schema}},
        top_k=32,
        seed=11,
        n=3,
    )
    payload = gg.build_request_payload(req)

    # Gemini-shaped tools.
    assert payload["tools"][0]["functionDeclarations"][0]["name"] == "f"
    # Default ANY tool_config.
    assert payload["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"
    gen = payload["generationConfig"]
    assert gen["temperature"] == 0.3  # not clobbered
    assert gen["responseMimeType"] == "application/json"
    assert gen["responseSchema"] == schema
    assert gen["topK"] == 32
    assert gen["seed"] == 11
    assert gen["candidateCount"] == 3


def test_parse_function_call_to_canonical_tool_calls():
    fake_gemini_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Let me check."},
                        {
                            "functionCall": {
                                "name": "get_weather",
                                "args": {"city": "Paris", "unit": "c"},
                            }
                        },
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 8,
            "totalTokenCount": 13,
        },
        "modelVersion": "test-model",
    }
    parsed = gg.parse_response(fake_gemini_response)

    assert parsed["text"] == "Let me check."
    assert "tool_calls" in parsed
    call = parsed["tool_calls"][0]
    assert call["id"] == "call_1"  # synthesized from part index
    assert call["type"] == "function"
    assert call["function"]["name"] == "get_weather"
    # arguments MUST be a JSON-encoded STRING, not a dict.
    assert isinstance(call["function"]["arguments"], str)
    assert json.loads(call["function"]["arguments"]) == {"city": "Paris", "unit": "c"}
    # #1720 Wave-B1a — the wire now value-maps the raw Gemini finishReason onto
    # the legacy lowercase form ('STOP' -> 'stop'), matching
    # kaizen.providers.llm.google (behaviour-neutral cutover, DECISION-1A).
    assert parsed["stop_reason"] == "stop"
    assert parsed["usage"]["total_tokens"] == 13


def test_parse_function_call_with_no_args_encodes_empty_object():
    fake = {
        "candidates": [{"content": {"parts": [{"functionCall": {"name": "noop"}}]}}]
    }
    parsed = gg.parse_response(fake)
    call = parsed["tool_calls"][0]
    assert call["id"] == "call_0"
    assert call["function"]["arguments"] == "{}"


def test_parse_text_only_response_has_no_tool_calls_key():
    fake = {
        "candidates": [
            {"content": {"parts": [{"text": "just text"}]}, "finishReason": "STOP"}
        ]
    }
    parsed = gg.parse_response(fake)
    assert parsed["text"] == "just text"
    assert "tool_calls" not in parsed  # only present when ≥1 functionCall part


def test_parse_multiple_function_calls_synthesize_distinct_ids():
    fake = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": "a", "args": {"i": 1}}},
                        {"functionCall": {"name": "b", "args": {"i": 2}}},
                    ]
                }
            }
        ]
    }
    parsed = gg.parse_response(fake)
    ids = [c["id"] for c in parsed["tool_calls"]]
    assert ids == ["call_0", "call_1"]
    assert parsed["tool_calls"][0]["function"]["name"] == "a"
    assert parsed["tool_calls"][1]["function"]["name"] == "b"
