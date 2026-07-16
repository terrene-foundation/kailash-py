"""#1720 Wave-1b — anthropic_messages tool emission + tool_use parse.

Behavioral coverage for the AnthropicMessages wire adapter's completion-shaping
translation (OpenAI-shaped CompletionRequest fields -> Anthropic /v1/messages
schema) and the canonical tool_use -> tool_calls parse.

Anthropic supports ``tools`` (shape ``{name, description, input_schema}``),
``tool_choice`` (``{"type": ...}``), and ``top_k`` natively; it does NOT support
``response_format`` / ``seed`` / ``logit_bias`` / ``frequency_penalty`` /
``presence_penalty`` / ``n`` — those MUST never appear in the payload.
"""

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import anthropic_messages


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


# --- Emission: tools -> Anthropic input_schema shape --------------------------


def test_tools_translated_to_anthropic_shape():
    req = _base_request(
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
        tool_choice="required",
        top_k=40,
    )
    payload = anthropic_messages.build_request_payload(req)

    assert payload["tools"] == [
        {
            "name": "get_weather",
            "description": "Look up the weather",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        }
    ]
    # "required" maps to Anthropic's {"type": "any"}.
    assert payload["tool_choice"] == {"type": "any"}
    # Anthropic supports top_k natively.
    assert payload["top_k"] == 40


def test_tools_missing_description_and_parameters_default():
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f"}}],
    )
    payload = anthropic_messages.build_request_payload(req)
    assert payload["tools"] == [{"name": "f", "description": "", "input_schema": {}}]


def test_tool_choice_default_when_tools_set_is_any():
    # tools set, tool_choice unset -> legacy "required" semantics: {"type": "any"}.
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
    )
    payload = anthropic_messages.build_request_payload(req)
    assert payload["tool_choice"] == {"type": "any"}


def test_tool_choice_auto():
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice="auto",
    )
    payload = anthropic_messages.build_request_payload(req)
    assert payload["tool_choice"] == {"type": "auto"}


def test_tool_choice_none_omits_tools():
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice="none",
    )
    payload = anthropic_messages.build_request_payload(req)
    # "none" -> Anthropic offers no tools; both keys are absent.
    assert "tools" not in payload
    assert "tool_choice" not in payload


def test_tool_choice_forced_tool_dict():
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        tool_choice={"type": "function", "function": {"name": "f"}},
    )
    payload = anthropic_messages.build_request_payload(req)
    assert payload["tool_choice"] == {"type": "tool", "name": "f"}


def test_top_k_emitted_without_tools():
    req = _base_request(top_k=25)
    payload = anthropic_messages.build_request_payload(req)
    assert payload["top_k"] == 25


# --- Emission: unsupported fields are NEVER emitted ---------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("seed", 7),
        ("logit_bias", {"123": -1.0}),
        ("frequency_penalty", 0.5),
        ("presence_penalty", 0.25),
        ("n", 2),
        ("response_format", {"type": "json_object"}),
    ],
)
def test_unsupported_fields_never_emitted(field, value):
    req = _base_request(
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
        **{field: value},
    )
    payload = anthropic_messages.build_request_payload(req)
    assert field not in _all_keys(payload), (
        f"anthropic_messages emitted unsupported field {field!r} — Anthropic "
        f"/v1/messages does not accept it."
    )


def test_response_format_emits_no_bogus_key():
    # Anthropic has no response_format param; setting it must add NO new key vs
    # a request that omits it (honest: no fake feature).
    with_rf = _base_request(response_format={"type": "json_object"})
    without_rf = _base_request()
    assert anthropic_messages.build_request_payload(
        with_rf
    ) == anthropic_messages.build_request_payload(without_rf)


# --- Parse: tool_use block -> canonical tool_calls ----------------------------


def test_tool_use_block_parses_to_canonical_shape():
    fake_response = {
        "content": [
            {"type": "text", "text": "Let me check."},
            {
                "type": "tool_use",
                "id": "toolu_abc123",
                "name": "get_weather",
                "input": {"city": "Paris", "unit": "c"},
            },
        ],
        "stop_reason": "tool_use",
        "model": "test-model",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    parsed = anthropic_messages.parse_response(fake_response)

    assert parsed["tool_calls"] == [
        {
            "id": "toolu_abc123",
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

    # Existing parsed keys are unchanged.
    assert parsed["text"] == "Let me check."
    assert parsed["stop_reason"] == "tool_use"
    assert parsed["model"] == "test-model"
    assert parsed["usage"] == {"input_tokens": 10, "output_tokens": 5}
    # tool_use block is still passed through on raw_blocks.
    assert any(b.get("type") == "tool_use" for b in parsed["raw_blocks"])


def test_multiple_tool_use_blocks_all_parsed():
    fake_response = {
        "content": [
            {"type": "tool_use", "id": "t1", "name": "a", "input": {"x": 1}},
            {"type": "tool_use", "id": "t2", "name": "b", "input": {}},
        ],
    }
    parsed = anthropic_messages.parse_response(fake_response)
    assert [tc["id"] for tc in parsed["tool_calls"]] == ["t1", "t2"]
    assert parsed["tool_calls"][1]["function"]["arguments"] == json.dumps({})


def test_no_tool_use_block_omits_tool_calls_key():
    fake_response = {"content": [{"type": "text", "text": "just text"}]}
    parsed = anthropic_messages.parse_response(fake_response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "just text"
