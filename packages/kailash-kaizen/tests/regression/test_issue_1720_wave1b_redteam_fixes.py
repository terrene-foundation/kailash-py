"""#1720 Wave-1b — /redteam finding fixes (PR #1776).

Pins the four fixes the Wave-1b convergence round surfaced:
1. Gemini camelCase tool keys (toolConfig / functionCallingConfig / allowedFunctionNames).
2. Gemini response_format text-mode: {"type":"text"} must NOT force JSON mode.
3. Empty-but-set tools=[] emits nothing on openai + anthropic (no invalid
   required-with-no-tools request).
4. openai_chat defensive arguments coercion for OpenAI-COMPATIBLE providers that
   return tool-call arguments as a dict rather than a JSON string.
"""

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import (
    anthropic_messages,
    google_generate_content,
    openai_chat,
)


def _req(**kw):
    base: dict = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "hi"}],
    }
    base.update(kw)
    return CompletionRequest(**base)


_TOOL = {"type": "function", "function": {"name": "f", "parameters": {}}}


@pytest.mark.regression
def test_gemini_tool_keys_are_camelcase():
    """Finding 1 — Gemini tool_config keys use camelCase (documented shape)."""
    payload = google_generate_content.build_request_payload(
        _req(tools=[_TOOL], tool_choice="required")
    )
    assert "toolConfig" in payload, "must use camelCase toolConfig"
    assert "tool_config" not in payload
    fcc = payload["toolConfig"]["functionCallingConfig"]
    assert fcc["mode"] == "ANY"
    # forced-tool → allowedFunctionNames camelCase
    forced = google_generate_content.build_request_payload(
        _req(tools=[_TOOL], tool_choice={"type": "function", "function": {"name": "f"}})
    )
    assert "allowedFunctionNames" in forced["toolConfig"]["functionCallingConfig"]


@pytest.mark.regression
def test_gemini_response_format_text_does_not_force_json():
    """Finding 2 — a text response_format must NOT set responseMimeType."""
    payload = google_generate_content.build_request_payload(
        _req(response_format={"type": "text"})
    )
    gc = payload.get("generationConfig", {})
    assert "responseMimeType" not in gc, "text response_format must not force JSON mode"
    # json_object DOES force it
    payload_json = google_generate_content.build_request_payload(
        _req(response_format={"type": "json_object"})
    )
    assert payload_json["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.regression
@pytest.mark.parametrize(
    "shaper",
    [openai_chat, anthropic_messages, google_generate_content],
    ids=["openai", "anthropic", "google"],
)
def test_empty_tools_list_emits_nothing(shaper):
    """Finding 3 (+ round-2 gap) — tools=[] (set but empty) emits no tools +
    no forced tool-choice/config on ALL THREE adapters. Round-2 caught that the
    Gemini adapter had missed this same-class guard."""
    payload = shaper.build_request_payload(_req(tools=[]))
    assert "tools" not in payload, "empty tools list must not emit a tools key"
    # openai/anthropic use `tool_choice`; gemini uses `toolConfig` — neither
    # forced-selection surface may appear with no tools.
    assert "tool_choice" not in payload, "must not force tool_choice with no tools"
    assert "toolConfig" not in payload, "must not force toolConfig with no tools"


@pytest.mark.regression
@pytest.mark.parametrize(
    "shaper",
    [openai_chat, anthropic_messages, google_generate_content],
    ids=["openai", "anthropic", "google"],
)
@pytest.mark.parametrize("tools", [None, []], ids=["none", "empty"])
def test_tool_choice_set_without_tools_emits_no_forced_selection(shaper, tools):
    """Round-3 gap — a tool_choice/forced selection with tools unset OR empty
    must NOT be emitted on ANY adapter (tool_choice is meaningless without
    tools; a forced 'required' with no tools is an invalid request). All three
    adapters MUST agree — the four-axis consistency contract."""
    payload = shaper.build_request_payload(_req(tools=tools, tool_choice="required"))
    assert "tool_choice" not in payload, "tool_choice leaked without tools"
    assert "toolConfig" not in payload, "toolConfig leaked without tools"
    assert "tools" not in payload


@pytest.mark.regression
@pytest.mark.parametrize(
    "shaper",
    [openai_chat, anthropic_messages, google_generate_content],
    ids=["openai", "anthropic", "google"],
)
def test_empty_collection_fields_emit_nothing(shaper):
    """Round-4 observation B — a set-but-empty collection field (``response_format={}``,
    ``logit_bias={}``) must NOT emit a degenerate key on any adapter (same
    empty-collection discipline as the tools guard; the emptiness leak class)."""
    payload = shaper.build_request_payload(_req(response_format={}, logit_bias={}))
    assert "response_format" not in payload
    assert "logit_bias" not in payload


@pytest.mark.regression
def test_openai_coerces_dict_arguments_to_json_string():
    """Finding 4 — an OpenAI-compatible provider returning arguments as a dict
    is coerced to a JSON string (canonical contract holds fleet-wide)."""
    response = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            # non-conformant: arguments as a dict, not a JSON string
                            "function": {"name": "f", "arguments": {"city": "SF"}},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    parsed = openai_chat.parse_response(response)
    args = parsed["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str), "dict arguments must be coerced to a JSON string"
    assert json.loads(args) == {"city": "SF"}
