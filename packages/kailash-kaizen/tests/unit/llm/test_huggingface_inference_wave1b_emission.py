"""#1720 Wave-1b — huggingface_inference completion-shaping EMISSION + PARSE.

Behavioral tests for the HuggingFace Inference wire adapter's Wave-1b
additions. The module has TWO request shapes:

* Classic text-generation (default) — ``{inputs, parameters}``. Has NO tools
  concept; ``request.tools`` / ``request.tool_choice`` are deliberately
  OMITTED on this path even when set (no fake capability).
* Chat schema (``use_chat_schema=True``, TGI / Inference Endpoints) —
  OpenAI-compatible. Accepts ``tools`` + ``tool_choice`` (truthiness guard on
  tools; ``tool_choice`` emitted ONLY alongside non-empty tools; unset
  default is the CONSERVATIVE ``"auto"`` — not the OpenAI-family legacy
  ``"required"`` — because TGI's tool support is model-dependent).

``parse_response`` surfaces ``choices[0].message.tool_calls`` (chat-schema
branch only) under the ``"tool_calls"`` key in the canonical normalized
shape (``arguments`` is a JSON-encoded string; a synthesized ``call_{i}`` id
when the provider omits one). The classic list/``generated_text`` branch has
no tool calls at all.

Also covers: ``_flatten_messages_to_prompt`` now logs a WARNING (instead of
silently dropping) when a non-text content block is present.

All assertions are behavioral (construct -> call -> assert the produced
dict/log record), not source-grep. No real model names are hardcoded
(env-models.md) — the tests use ``"test-model"``.
"""

import json
import logging

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.wire_protocols import huggingface_inference


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


# ---------------------------------------------------------------------------
# build_request_payload — chat-schema path (use_chat_schema=True)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chat_schema_emits_tools_and_defaults_tool_choice_to_auto():
    """Chat-schema path emits `tools` verbatim; unset tool_choice defaults to
    the CONSERVATIVE 'auto' (not the OpenAI-family legacy 'required')."""
    tools = _tools()
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=tools,
        # tool_choice deliberately unset
    )
    payload = huggingface_inference.build_request_payload(request, use_chat_schema=True)

    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"


@pytest.mark.unit
def test_chat_schema_explicit_tool_choice_passes_through():
    """An explicit caller-set tool_choice (including OpenAI's 'required')
    passes through verbatim on the chat-schema path."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="required",
    )
    payload = huggingface_inference.build_request_payload(request, use_chat_schema=True)
    assert payload["tool_choice"] == "required"


@pytest.mark.unit
def test_chat_schema_tool_choice_auto_and_none_pass_through():
    """OpenAI-native 'auto' / 'none' string values pass through unchanged."""
    for choice in ("auto", "none"):
        request = CompletionRequest(
            model="test-model",
            messages=_base_messages(),
            tools=_tools(),
            tool_choice=choice,
        )
        payload = huggingface_inference.build_request_payload(
            request, use_chat_schema=True
        )
        assert payload["tool_choice"] == choice


@pytest.mark.unit
def test_chat_schema_named_tool_dict_passes_through():
    """A named-tool forced-selection dict passes through in the OpenAI-shaped
    object form (chat schema is OpenAI-compatible)."""
    named = {"type": "function", "function": {"name": "get_weather"}}
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice=named,
    )
    payload = huggingface_inference.build_request_payload(request, use_chat_schema=True)
    assert payload["tool_choice"] == named


@pytest.mark.unit
def test_chat_schema_empty_tools_emits_nothing():
    """An explicitly-set EMPTY tools list emits neither tools nor tool_choice
    (truthiness guard, not `is not None`)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=[],
        tool_choice="auto",
    )
    payload = huggingface_inference.build_request_payload(request, use_chat_schema=True)
    assert "tools" not in payload
    assert "tool_choice" not in payload


@pytest.mark.unit
def test_chat_schema_tool_choice_not_emitted_without_tools():
    """tool_choice is meaningless without tools — emitted ONLY alongside a
    non-empty tools list. A standalone tool_choice (any value) is dropped."""
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
        payload = huggingface_inference.build_request_payload(
            request, use_chat_schema=True
        )
        assert (
            "tool_choice" not in payload
        ), f"tool_choice={choice!r} leaked without tools"
        assert "tools" not in payload


@pytest.mark.unit
def test_chat_schema_still_emits_existing_fields_alongside_tools():
    """Tool emission does not disturb the pre-existing chat-schema fields."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=_tools(),
        temperature=0.5,
        top_p=0.9,
        max_tokens=128,
        stop=["END"],
        stream=True,
    )
    payload = huggingface_inference.build_request_payload(request, use_chat_schema=True)
    assert payload["model"] == "test-model"
    assert payload["messages"] == _base_messages()
    assert payload["temperature"] == 0.5
    assert payload["top_p"] == 0.9
    assert payload["max_tokens"] == 128
    assert payload["stop"] == ["END"]
    assert payload["stream"] is True
    assert payload["tools"] == _tools()
    assert payload["tool_choice"] == "auto"


# ---------------------------------------------------------------------------
# build_request_payload — classic text-generation path (default)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_classic_path_omits_tools_even_when_set():
    """The classic {inputs, parameters} text-generation schema has NO tools
    concept. request.tools / request.tool_choice MUST be omitted, never
    faked, even when the caller set them."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=_tools(),
        tool_choice="required",
    )
    payload = huggingface_inference.build_request_payload(request)

    assert "tools" not in payload
    assert "tool_choice" not in payload
    # The classic shape is unaffected — inputs is still built.
    assert "inputs" in payload


@pytest.mark.unit
def test_classic_path_tools_dropped_logs_warning_not_silent(caplog):
    """/redteam Round-1 (#1720 Wave-1b): LlmClient has NO production
    mechanism to reach the chat schema (see module docstring "Known scoped
    limitation") -- every tools= call against an hf deployment lands on this
    classic path. The drop MUST be observable (WARN), never silent, per
    rules/observability.md Rule 7 / zero-tolerance Rule 3."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=_tools(),
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        payload = huggingface_inference.build_request_payload(
            request, use_chat_schema=False
        )

    assert "tools" not in payload
    assert any(
        r.levelno == logging.WARNING
        and "huggingface_inference.tools_dropped_classic_path" in r.message
        for r in caplog.records
    )


@pytest.mark.unit
def test_classic_path_response_format_dropped_logs_warning(caplog):
    """Same drop-is-observable contract for response_format on the classic
    path (no structured-output surface on {inputs, parameters})."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        response_format={"type": "json_object"},
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        payload = huggingface_inference.build_request_payload(
            request, use_chat_schema=False
        )

    assert "response_format" not in payload
    assert any(
        r.levelno == logging.WARNING
        and "huggingface_inference.response_format_dropped_classic_path" in r.message
        for r in caplog.records
    )


@pytest.mark.unit
def test_classic_path_no_tools_no_response_format_emits_no_warning(caplog):
    """Byte-neutral: a plain classic-path call with no tools/response_format
    emits neither warning."""
    request = CompletionRequest(model="test-model", messages=_base_messages())
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        huggingface_inference.build_request_payload(request, use_chat_schema=False)

    assert not any(
        "tools_dropped_classic_path" in r.message
        or "response_format_dropped_classic_path" in r.message
        for r in caplog.records
    )


@pytest.mark.unit
def test_classic_path_default_use_chat_schema_is_false():
    """build_request_payload defaults to the classic shape (use_chat_schema
    unset)."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
        tools=_tools(),
    )
    payload = huggingface_inference.build_request_payload(request)
    assert "model" not in payload  # classic shape carries no `model` key
    assert "tools" not in payload


# ---------------------------------------------------------------------------
# parse_response — chat-schema tool_calls normalization
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_response_surfaces_tool_calls_in_canonical_shape():
    """A chat-schema response with message.tool_calls parses into the
    canonical normalized shape; arguments stays a JSON-encoded string;
    entries are plain JSON-serializable dicts."""
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

    parsed = huggingface_inference.parse_response(response)

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
    assert parsed["model"] == "test-model"
    assert parsed["usage"] == {
        "input_tokens": 5,
        "output_tokens": 3,
        "total_tokens": 8,
    }


@pytest.mark.unit
def test_parse_response_synthesizes_call_id_when_missing():
    """A tool_call entry with no `id` gets a synthesized `call_{index}` id."""
    response = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": json.dumps({"city": "Rome"}),
                            },
                        },
                        {
                            "id": "call_explicit",
                            "type": "function",
                            "function": {
                                "name": "get_time",
                                "arguments": json.dumps({"tz": "UTC"}),
                            },
                        },
                    ],
                },
            }
        ],
        "model": "test-model",
    }
    parsed = huggingface_inference.parse_response(response)
    assert parsed["tool_calls"][0]["id"] == "call_0"
    assert parsed["tool_calls"][1]["id"] == "call_explicit"


@pytest.mark.unit
def test_parse_response_coerces_dict_arguments_to_json_string():
    """A non-conformant deployment returning `arguments` as a dict is
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
    parsed = huggingface_inference.parse_response(response)
    tc = parsed["tool_calls"][0]
    assert isinstance(tc["function"]["arguments"], str)
    assert json.loads(tc["function"]["arguments"]) == {"q": "kailash"}


@pytest.mark.unit
def test_parse_response_omits_tool_calls_key_when_absent_chat_schema():
    """No tool_calls in a chat-schema response -> no 'tool_calls' key in the
    parsed dict; the existing {text, usage, stop_reason, model} keys are
    intact (plain-text parse stays byte-identical to pre-Wave-1b shape)."""
    response = {
        "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "model": "test-model",
    }
    parsed = huggingface_inference.parse_response(response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "hello"
    assert set(parsed.keys()) == {"text", "usage", "stop_reason", "model"}


@pytest.mark.unit
def test_parse_response_classic_list_shape_has_no_tool_calls():
    """The classic list[{generated_text}] response shape has no tool calls
    at all — never a 'tool_calls' key, regardless of content."""
    response = [{"generated_text": "hello world"}]
    parsed = huggingface_inference.parse_response(response)
    assert "tool_calls" not in parsed
    assert parsed["text"] == "hello world"


# ---------------------------------------------------------------------------
# _flatten_messages_to_prompt — image-drop now WARNs (not silent)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_image_block_drop_logs_warning(caplog):
    """A non-text content block (e.g. an image_url block) submitted against
    the classic text-generation path is dropped, but now logs a WARNING
    instead of silently disappearing."""
    request = CompletionRequest(
        model="test-model",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe this"},
                    {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
                ],
            }
        ],
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        payload = huggingface_inference.build_request_payload(request)

    # The text block survives; the image block is dropped from the prompt.
    assert "describe this" in payload["inputs"]
    assert "image_url" not in payload["inputs"]
    # The drop is observable via a WARNING log record, not silent.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 1
    assert "non_text_block_dropped" in warning_records[0].message


@pytest.mark.unit
def test_text_only_blocks_emit_no_warning(caplog):
    """A content-block list containing only text blocks emits no warning."""
    request = CompletionRequest(
        model="test-model",
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            }
        ],
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        payload = huggingface_inference.build_request_payload(request)

    assert "hello" in payload["inputs"]
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 0


@pytest.mark.unit
def test_plain_string_content_emits_no_warning(caplog):
    """A plain string `content` (no block list) never triggers the drop
    warning — the warning only fires for typed content-block lists."""
    request = CompletionRequest(
        model="test-model",
        messages=_base_messages(),
    )
    with caplog.at_level(
        logging.WARNING, logger="kaizen.llm.wire_protocols.huggingface_inference"
    ):
        huggingface_inference.build_request_payload(request)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 0
