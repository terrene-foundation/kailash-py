# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2121 — the google_generate_content wire must represent a tool turn in history.

Two independent defects on this wire (the four-axis path ``LLMAgentNode`` /
``BaseAgent`` take, distinct from the ``Delegate`` adapter path of #2120) which
together made a multi-turn tool loop impossible:

1. ``build_request_payload`` built ``contents`` as a comprehension emitting
   TEXT PARTS ONLY, so an assistant turn carrying ``tool_calls`` serialised to
   ``{"role": "model", "parts": [{"text": ""}]}`` — the function call DROPPED —
   and a tool result became plain user text instead of a ``functionResponse``
   part. It failed SILENTLY: no error, the model simply never saw that a tool
   had been called or what it returned.

2. ``_tool_config_from_choice`` defaulted an unset ``tool_choice`` to ``ANY``,
   which forces a function call on EVERY turn, so the model could never emit
   the final text answer that ends the loop.

Asserted on the CONSTRUCTED REQUEST PAYLOAD — deterministic, credential-free,
and it pins the exact part shapes.
"""

from __future__ import annotations

import base64

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.thought_signature import THOUGHT_SIGNATURE_KEY
from kaizen.llm.wire_protocols import google_generate_content as gg

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_number",
            "description": "Return the secret number.",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]

_SIGNATURE = b"\x01\x02gemini-3-opaque-thought\xff"


def _tool_loop_messages(*, with_signature: bool = False, tool_name: bool = False):
    """A realistic 2-turn tool history, in the shape LLMAgentNode's loop emits."""
    tool_call = {
        "id": "call_0",
        "type": "function",
        "function": {"name": "get_number", "arguments": '{"base": 1}'},
    }
    if with_signature:
        tool_call[THOUGHT_SIGNATURE_KEY] = base64.b64encode(_SIGNATURE).decode("ascii")
    tool_msg = {"role": "tool", "tool_call_id": "call_0", "content": '{"number": 41}'}
    if tool_name:
        tool_msg["name"] = "get_number"
    return [
        {"role": "user", "content": "Call get_number and state the value."},
        {"role": "assistant", "content": None, "tool_calls": [tool_call]},
        tool_msg,
    ]


def _payload(messages, **kwargs):
    return gg.build_request_payload(
        CompletionRequest(model="test-gemini-model", messages=messages, **kwargs)
    )


# ---------------------------------------------------------------------------
# Defect 1 — a tool turn must be representable in history.
# ---------------------------------------------------------------------------


def test_assistant_tool_call_turn_serialises_as_a_function_call_part():
    payload = _payload(_tool_loop_messages(), tools=_TOOLS)
    model_turn = payload["contents"][1]
    assert model_turn["role"] == "model"
    assert model_turn["parts"] == [
        {"functionCall": {"name": "get_number", "args": {"base": 1}}}
    ]
    # The OpenAI arguments JSON *string* became a real object, as Gemini needs.
    assert isinstance(model_turn["parts"][0]["functionCall"]["args"], dict)


def test_tool_result_serialises_as_a_function_response_part():
    payload = _payload(_tool_loop_messages(), tools=_TOOLS)
    tool_turn = payload["contents"][2]
    # Gemini's own schema puts functionResponse inside a user-role turn.
    assert tool_turn["role"] == "user"
    assert tool_turn["parts"] == [
        {
            "functionResponse": {
                "name": "get_number",
                "response": {"result": '{"number": 41}'},
            }
        }
    ]


def test_function_response_name_is_resolved_from_the_assistant_turn():
    """LLMAgentNode's tool messages carry ``tool_call_id`` and NO ``name``.

    Gemini keys a functionResponse by NAME, so the wire must resolve it from the
    preceding assistant turn's ``tool_calls`` — otherwise every tool result on
    the node's own loop would be nameless.
    """
    messages = _tool_loop_messages(tool_name=False)
    assert "name" not in messages[2]
    payload = _payload(messages, tools=_TOOLS)
    assert (
        payload["contents"][2]["parts"][0]["functionResponse"]["name"] == "get_number"
    )


def test_explicit_tool_result_name_is_honoured():
    payload = _payload(_tool_loop_messages(tool_name=True), tools=_TOOLS)
    assert (
        payload["contents"][2]["parts"][0]["functionResponse"]["name"] == "get_number"
    )


def test_unresolvable_tool_result_name_raises_instead_of_flattening_to_text():
    """zero-tolerance Rule 3: silent flattening to user text IS the defect.

    There is no correct Gemini representation for a nameless tool result, so a
    typed error naming the problem beats an opaque provider 400.
    """
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "call_nonexistent", "content": "{}"},
    ]
    with pytest.raises(ValueError, match="matches no preceding assistant tool_calls"):
        _payload(messages, tools=_TOOLS)


def test_assistant_text_precedes_its_function_call_parts():
    """A tool-call turn that also carried reasoning text keeps both, in order."""
    messages = _tool_loop_messages()
    messages[1]["content"] = "Let me look that up."
    payload = _payload(messages, tools=_TOOLS)
    parts = payload["contents"][1]["parts"]
    assert parts[0] == {"text": "Let me look that up."}
    assert "functionCall" in parts[1]


def test_empty_assistant_content_emits_no_empty_text_part():
    """Gemini rejects an empty text part; a tool-call turn commonly has none."""
    payload = _payload(_tool_loop_messages(), tools=_TOOLS)
    parts = payload["contents"][1]["parts"]
    assert all("text" not in p for p in parts)


def test_malformed_tool_call_arguments_raise_rather_than_silently_emptying():
    messages = _tool_loop_messages()
    messages[1]["tool_calls"][0]["function"]["arguments"] = "{not json"
    with pytest.raises(ValueError, match="malformed JSON arguments"):
        _payload(messages, tools=_TOOLS)


def test_tool_less_history_is_byte_identical_to_the_pre_fix_shape():
    """Opposite pole: an ordinary conversation must be untouched.

    A fix that rerouted every message through the tool-turn builder would show
    up here.
    """
    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]
    payload = _payload(messages)
    assert payload["contents"] == [
        {"role": "user", "parts": [{"text": "hi"}]},
        {"role": "model", "parts": [{"text": "hello"}]},
        {"role": "user", "parts": [{"text": "bye"}]},
    ]
    assert payload["systemInstruction"] == {"parts": [{"text": "be brief"}]}


def test_assistant_turn_without_tool_calls_still_takes_the_text_path():
    """Opposite pole at the branch itself: ``tool_calls`` absent/empty -> text."""
    for tool_calls in (None, []):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello", "tool_calls": tool_calls},
        ]
        payload = _payload(messages)
        assert payload["contents"][1] == {"role": "model", "parts": [{"text": "hello"}]}


# ---------------------------------------------------------------------------
# Defect 1b — the shared #2120 root cause on THIS wire.
# ---------------------------------------------------------------------------


def test_thought_signature_round_trips_through_parse_and_replay():
    """Gemini 3.x rejects a replayed functionCall part with no thoughtSignature.

    Same root cause as #2120 (the Delegate adapter): the Google request builder
    discarded the part of a tool turn that Gemini needs in order to replay it.
    Fixing the history representation WITHOUT this would still 400 on 3.x.
    """
    parsed = gg.parse_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {"name": "get_number", "args": {}},
                                "thoughtSignature": base64.b64encode(_SIGNATURE).decode(
                                    "ascii"
                                ),
                            }
                        ]
                    },
                    "finishReason": "STOP",
                }
            ]
        }
    )
    stashed = parsed["tool_calls"][0][THOUGHT_SIGNATURE_KEY]
    assert base64.b64decode(stashed) == _SIGNATURE

    payload = _payload(
        [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": None, "tool_calls": parsed["tool_calls"]},
        ],
        tools=_TOOLS,
    )
    part = payload["contents"][1]["parts"][0]
    # PART-LEVEL SIBLING, base64 string (the REST wire is JSON-serialised).
    assert part["thoughtSignature"] == base64.b64encode(_SIGNATURE).decode("ascii")
    assert "thoughtSignature" not in part["functionCall"]


def test_no_thought_signature_is_emitted_when_the_model_issued_none():
    """Opposite pole: Gemini 2.5 emits none, so the replay must carry none."""
    parsed = gg.parse_response(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"functionCall": {"name": "get_number", "args": {}}}]
                    }
                }
            ]
        }
    )
    assert THOUGHT_SIGNATURE_KEY not in parsed["tool_calls"][0]
    payload = _payload(
        [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": None, "tool_calls": parsed["tool_calls"]},
        ],
        tools=_TOOLS,
    )
    assert payload["contents"][1]["parts"][0] == {
        "functionCall": {"name": "get_number", "args": {}}
    }


# ---------------------------------------------------------------------------
# Defect 2 — an unset tool_choice must not force a call on every turn.
# ---------------------------------------------------------------------------


def test_unset_tool_choice_defaults_to_auto_so_the_loop_can_terminate():
    payload = _payload(_tool_loop_messages(), tools=_TOOLS)
    assert payload["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}


@pytest.mark.parametrize(
    "choice,mode",
    [("auto", "AUTO"), ("required", "ANY"), ("none", "NONE")],
)
def test_explicit_tool_choice_still_maps_verbatim(choice, mode):
    """Opposite pole: a caller who WANTS forced calling still gets ANY.

    A fix that hardcoded AUTO would break ``tool_choice="required"``, which is
    a different bug.
    """
    payload = _payload(_tool_loop_messages(), tools=_TOOLS, tool_choice=choice)
    assert payload["toolConfig"] == {"functionCallingConfig": {"mode": mode}}


def test_forced_named_tool_still_maps_to_any_plus_allowed_names():
    payload = _payload(
        _tool_loop_messages(),
        tools=_TOOLS,
        tool_choice={"type": "function", "function": {"name": "get_number"}},
    )
    assert payload["toolConfig"] == {
        "functionCallingConfig": {
            "mode": "ANY",
            "allowedFunctionNames": ["get_number"],
        }
    }


def test_no_tool_config_at_all_without_tools():
    """Opposite pole: a mode with no tools is meaningless and must not be emitted."""
    payload = _payload([{"role": "user", "content": "hi"}])
    assert "toolConfig" not in payload
    assert "tools" not in payload
