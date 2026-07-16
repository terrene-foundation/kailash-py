# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-1b — bedrock_invoke completion-shaping EMISSION + PARSE.

Behavioral tests for the AWS Bedrock ``InvokeModel`` wire adapter's
Wave-1b additions. Bedrock tool support on the native (non-Anthropic)
InvokeModel body is PER-FAMILY and OMIT-DON'T-FAKE:

* ``mistral.*`` — the one native family with a documented ``tools`` +
  ``tool_choice`` field on the InvokeModel body (OpenAI-shaped tools,
  Mistral tool_choice vocabulary — force-a-tool is ``"any"``, not
  OpenAI's ``"required"``). EMITTED.
* ``meta.*`` (Llama) / ``amazon.*`` (Titan) / ``cohere.*`` (classic
  Cohere Command) — no documented tools field on the InvokeModel body
  this shaper builds. Tools are deliberately OMITTED (key absent, never
  a fake/empty placeholder).

``parse_response`` normalizes Bedrock-Mistral's ``outputs[0].tool_calls``
into the canonical shape shared with the other wire shards (``arguments``
is always a JSON-encoded string; a missing id is synthesized as
``call_{index}``), surfaced under the ``"tool_calls"`` key ONLY when
present so a plain-text response stays byte-identical to the pre-Wave-1b
parsed shape.

Also covers the ``_flatten_prompt`` image/non-text content block drop,
upgraded from a silent drop to a structured WARN log
(observability.md Rule 7 / zero-tolerance Rule 3).

All assertions are behavioral (construct -> call -> assert the produced
dict / normalized tool_calls / log record), not source-grep. No real
model names are hardcoded (env-models.md) — the tests use Bedrock-shaped
but synthetic model ids (``meta.test-model``, ``mistral.test-model``, etc).
"""

import json
import logging

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import bedrock_invoke


def _base_messages():
    return [{"role": "user", "content": "hi"}]


def _tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
            },
        }
    ]


# --------------------------------------------------------------------------
# (a) mistral family emits tools + tool_choice mapping
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_mistral_emits_tools_verbatim():
    """Mistral's Bedrock InvokeModel body carries `tools` verbatim (OpenAI
    function-schema shape passthrough), same as mistral_chat.py."""
    tools = _tools()
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
        tools=tools,
        tool_choice="auto",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


@pytest.mark.unit
def test_mistral_tool_choice_required_maps_to_any():
    """OpenAI's forced-tool value 'required' MUST map to Mistral's 'any'."""
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="required",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert payload["tool_choice"] == "any"


@pytest.mark.unit
def test_mistral_tool_choice_auto_none_any_pass_through():
    """Mistral-native string values pass through unchanged."""
    for choice in ("auto", "none", "any"):
        request = CompletionRequest(
            model="mistral.mistral-large-2407-v1:0",
            messages=_base_messages(),
            tools=_tools(),
            tool_choice=choice,
        )
        payload = bedrock_invoke.build_request_payload(request)
        assert payload["tool_choice"] == choice


@pytest.mark.unit
def test_mistral_tool_choice_unknown_string_falls_back_to_any():
    """An unknown tool_choice string falls back to the safe forced default
    'any' (never a shape Mistral would reject)."""
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="banana",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert payload["tool_choice"] == "any"


@pytest.mark.unit
def test_mistral_tool_choice_named_tool_dict_passes_through():
    """A named-tool forced-selection dict passes through verbatim."""
    named = {"type": "function", "function": {"name": "get_weather"}}
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice=named,
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert payload["tool_choice"] == named


@pytest.mark.unit
def test_mistral_tool_choice_defaults_to_any_when_tools_set_and_choice_none():
    """tools present + tool_choice unset -> tool_choice='any' (force a
    tool), the pinned Wave-1a legacy default expressed in Mistral's
    vocabulary."""
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
        tools=_tools(),
        # tool_choice deliberately unset
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert payload["tool_choice"] == "any"


# --------------------------------------------------------------------------
# (b) meta/amazon OMIT tools (assert key absent) — cohere too
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_llama_omits_tools_even_when_set():
    """meta.* (Llama) has no documented tools field on Bedrock InvokeModel —
    tools MUST be absent from the payload even when the request sets them."""
    request = CompletionRequest(
        model="meta.llama3-70b-instruct-v1:0",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="auto",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert "tools" not in payload
    assert "tool_choice" not in payload
    # The Llama body shape is otherwise unaffected.
    assert "prompt" in payload
    assert "max_gen_len" in payload


@pytest.mark.unit
def test_titan_omits_tools_even_when_set():
    """amazon.* (Titan) has no tools field at all on Bedrock InvokeModel —
    tools MUST be absent from the payload even when the request sets them."""
    request = CompletionRequest(
        model="amazon.titan-text-express-v1",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="auto",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert "textGenerationConfig" not in payload or "tools" not in payload.get(
        "textGenerationConfig", {}
    )
    assert "inputText" in payload


@pytest.mark.unit
def test_cohere_omits_tools_even_when_set():
    """cohere.* (classic Command, prompt-based) has no documented tools
    field on Bedrock InvokeModel — tools MUST be absent even when set."""
    request = CompletionRequest(
        model="cohere.command-text-v14",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="auto",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert "tools" not in payload
    assert "tool_choice" not in payload
    assert "prompt" in payload


# --------------------------------------------------------------------------
# (c) empty tools=[] emits nothing (mistral family)
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_mistral_empty_tools_emits_nothing():
    """An explicitly-set EMPTY tools list emits neither tools nor
    tool_choice (truthiness guard, not `is not None`)."""
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
        tools=[],
        tool_choice="any",
    )
    payload = bedrock_invoke.build_request_payload(request)
    assert "tools" not in payload
    assert "tool_choice" not in payload


# --------------------------------------------------------------------------
# (d) tool_choice-without-tools emits nothing (mistral family)
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_mistral_tool_choice_not_emitted_without_tools():
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
            model="mistral.mistral-large-2407-v1:0",
            messages=_base_messages(),
            tool_choice=choice,
        )
        payload = bedrock_invoke.build_request_payload(request)
        assert (
            "tool_choice" not in payload
        ), f"tool_choice={choice!r} leaked without tools"
        assert "tools" not in payload


# --------------------------------------------------------------------------
# (e) parse normalizes tool_calls with arguments as JSON string +
#     synthesized id
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_response_surfaces_mistral_tool_calls_in_canonical_shape():
    """A fake Bedrock-Mistral response with outputs[0].tool_calls parses
    into the canonical normalized shape; arguments stays a JSON-encoded
    string; entries are plain JSON-serializable dicts."""
    arguments_json = json.dumps({"city": "Paris"})
    response = {
        "outputs": [
            {
                "text": "",
                "stop_reason": "tool_calls",
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
            }
        ]
    }

    parsed = bedrock_invoke.parse_response(response)

    assert parsed["tool_calls"] == [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": arguments_json},
        }
    ]
    tc = parsed["tool_calls"][0]
    assert isinstance(tc["function"]["arguments"], str)
    assert json.loads(tc["function"]["arguments"]) == {"city": "Paris"}
    # The result must be JSON-serializable (plain dicts, no SDK objects).
    json.dumps(parsed)
    assert parsed["text"] == ""
    assert parsed["stop_reason"] == "tool_calls"


@pytest.mark.unit
def test_parse_response_coerces_dict_arguments_to_json_string():
    """A non-conformant response returning `arguments` as a dict is coerced
    to a JSON string so the canonical invariant holds."""
    response = {
        "outputs": [
            {
                "text": "",
                "stop_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_xyz",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": {"q": "kailash"}},
                    }
                ],
            }
        ]
    }
    parsed = bedrock_invoke.parse_response(response)
    tc = parsed["tool_calls"][0]
    assert isinstance(tc["function"]["arguments"], str)
    assert json.loads(tc["function"]["arguments"]) == {"q": "kailash"}


@pytest.mark.unit
def test_parse_response_synthesizes_id_when_provider_omits_it():
    """When Bedrock-Mistral omits the tool-call id, synthesize `call_{i}`."""
    response = {
        "outputs": [
            {
                "text": "",
                "stop_reason": "tool_calls",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                    },
                    {
                        "type": "function",
                        "function": {"name": "g", "arguments": "{}"},
                    },
                ],
            }
        ]
    }
    parsed = bedrock_invoke.parse_response(response)
    assert parsed["tool_calls"][0]["id"] == "call_0"
    assert parsed["tool_calls"][1]["id"] == "call_1"


# --------------------------------------------------------------------------
# (f) plain-text parse has no tool_calls key (byte-neutral)
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_response_omits_tool_calls_key_when_absent_mistral():
    """No tool_calls in a Mistral response -> no 'tool_calls' key in the
    parsed dict; the pre-Wave-1b {text, usage, stop_reason, model} shape is
    unchanged (byte-neutral)."""
    response = {"outputs": [{"text": "hello", "stop_reason": "stop"}]}
    parsed = bedrock_invoke.parse_response(response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "hello"
    assert set(parsed.keys()) == {"text", "usage", "stop_reason", "model"}


@pytest.mark.unit
def test_parse_response_omits_tool_calls_key_for_llama_titan_cohere():
    """Non-Mistral family response shapes never carry tool_calls at all —
    parse never surfaces the key for them."""
    llama_response = {
        "generation": "hi",
        "stop_reason": "stop",
        "prompt_token_count": 3,
        "generation_token_count": 1,
    }
    titan_response = {
        "results": [{"outputText": "hi", "completionReason": "FINISH"}],
        "inputTextTokenCount": 3,
    }
    cohere_response = {"generations": [{"text": "hi", "finish_reason": "COMPLETE"}]}

    for response in (llama_response, titan_response, cohere_response):
        parsed = bedrock_invoke.parse_response(response)
        assert "tool_calls" not in parsed
        assert parsed["text"] == "hi"


# --------------------------------------------------------------------------
# (g) image-block drop logs a warning (caplog)
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_flatten_prompt_drops_image_block_with_warning(
    caplog: pytest.LogCaptureFixture,
):
    """A non-text content block (e.g. an image) is dropped from the
    flattened prompt AND logs a structured WARNING naming the family as
    vision-unsupported — not a silent drop."""
    request = CompletionRequest(
        model="meta.llama3-70b-instruct-v1:0",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {
                        "type": "image",
                        "source": {"type": "base64", "data": "AAAA"},
                    },
                ],
            }
        ],
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.bedrock_invoke"
    ):
        payload = bedrock_invoke.build_request_payload(request)

    # The image block never appears in the rendered prompt.
    assert "describe this" in payload["prompt"]
    assert "AAAA" not in payload["prompt"]

    record = next(
        (
            r
            for r in caplog.records
            if r.message == "bedrock_invoke.non_text_block_dropped"
        ),
        None,
    )
    assert record is not None
    assert record.levelno == logging.WARNING
    assert record.family == "meta"
    assert record.reason == "vision_unsupported"


@pytest.mark.unit
def test_flatten_prompt_no_warning_for_plain_text_messages(
    caplog: pytest.LogCaptureFixture,
):
    """A plain-text-only request never logs the dropped-block warning."""
    request = CompletionRequest(
        model="mistral.mistral-large-2407-v1:0",
        messages=_base_messages(),
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.bedrock_invoke"
    ):
        bedrock_invoke.build_request_payload(request)

    assert not any(
        r.message == "bedrock_invoke.non_text_block_dropped" for r in caplog.records
    )
