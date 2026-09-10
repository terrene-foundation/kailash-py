# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for #2120 — GoogleStreamAdapter dropped ``thought_signature``.

Gemini 3.x REQUIRES every replayed ``functionCall`` part to carry back the
``thought_signature`` the model issued with it. The adapter captured neither
(it built the tool-call dict from ``fc.name`` / ``fc.args`` only) nor replayed
it (it emitted a bare ``{"function_call": {...}}``), so the FIRST request
succeeded and returned a tool call and the SECOND — replaying that call as
history — was rejected::

    google.genai.errors.ClientError: 400 INVALID_ARGUMENT
    "Function call is missing a thought_signature in functionCall parts."

No tool ever executed, and there was no caller-side workaround: the adapter
owns both halves. Gemini 2.5 was unaffected (it issues no signature).

Verified at the WIRE-CONSTRUCTION boundary — the ``contents`` the adapter hands
``google.genai`` — rather than by a live call: deterministic, credential-free,
and it pins the exact field and its exact position.

BOTH POLES, because a test that only checks the signature is PRESENT could not
distinguish this fix from one that fabricates a signature unconditionally:

* Gemini 3.x (signature issued)  -> captured, and replayed on the part
* Gemini 2.5 (no signature)      -> nothing captured, replay byte-identical
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest
from google.genai import types

from kaizen.llm.thought_signature import THOUGHT_SIGNATURE_KEY
from kaizen_agents.delegate.adapters.google_adapter import _convert_messages_for_gemini

_SIGNATURE = b"\x01\x02gemini-3-opaque-thought\xff"


# ---------------------------------------------------------------------------
# Replay — the second request of the tool loop.
# ---------------------------------------------------------------------------


def _assistant_turn(*, with_signature: bool) -> list[dict[str, Any]]:
    tool_call: dict[str, Any] = {
        "id": "call_abc123",
        "type": "function",
        "function": {"name": "get_number", "arguments": "{}"},
    }
    if with_signature:
        tool_call[THOUGHT_SIGNATURE_KEY] = base64.b64encode(_SIGNATURE).decode("ascii")
    return [
        {"role": "user", "content": "Call get_number."},
        {"role": "assistant", "content": "", "tool_calls": [tool_call]},
        {"role": "tool", "name": "get_number", "content": '{"number": 41}'},
    ]


@pytest.mark.regression
def test_replayed_function_call_carries_the_thought_signature():
    _system, contents = _convert_messages_for_gemini(
        _assistant_turn(with_signature=True)
    )
    model_turn = next(c for c in contents if c["role"] == "model")
    part = model_turn["parts"][0]

    assert part["function_call"]["name"] == "get_number"
    # PART-LEVEL SIBLING of function_call, never nested inside it: in
    # google-genai's model the signature sits on the Part.
    assert part["thought_signature"] == _SIGNATURE
    assert "thought_signature" not in part["function_call"]


@pytest.mark.regression
def test_google_genai_accepts_the_replayed_part_and_round_trips_the_signature():
    """The emitted dict must validate as a real ``types.Content``.

    Asserting on our own dict alone would not prove the SDK accepts the key or
    preserves the bytes; this drives the actual pydantic model.
    """
    _system, contents = _convert_messages_for_gemini(
        _assistant_turn(with_signature=True)
    )
    model_turn = next(c for c in contents if c["role"] == "model")
    validated = types.Content.model_validate(model_turn)
    assert validated.parts[0].thought_signature == _SIGNATURE
    assert validated.parts[0].function_call.name == "get_number"


@pytest.mark.regression
def test_gemini_25_replay_is_unchanged_when_no_signature_was_issued():
    """Opposite pole: no signature captured -> no signature replayed.

    Gemini 2.5 issues none; emitting a key there would change a working path.
    """
    _system, contents = _convert_messages_for_gemini(
        _assistant_turn(with_signature=False)
    )
    model_turn = next(c for c in contents if c["role"] == "model")
    part = model_turn["parts"][0]
    assert part["function_call"]["name"] == "get_number"
    assert "thought_signature" not in part
    assert part == {"function_call": {"name": "get_number", "args": {}}}


@pytest.mark.regression
def test_malformed_stashed_signature_raises_instead_of_being_dropped():
    """zero-tolerance Rule 3: a dropped signature is the opaque 400 we fixed."""
    messages = _assistant_turn(with_signature=True)
    messages[1]["tool_calls"][0][THOUGHT_SIGNATURE_KEY] = "!!!not-base64!!!"
    with pytest.raises(ValueError, match="not valid base64"):
        _convert_messages_for_gemini(messages)


# ---------------------------------------------------------------------------
# Capture — the first request of the tool loop.
# ---------------------------------------------------------------------------


def _chunk_with(part: types.Part) -> Any:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


class _StubModels:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def generate_content_stream(self, **_kwargs: Any) -> Any:
        chunks = self._chunks

        async def _gen():
            for chunk in chunks:
                yield chunk

        return _gen()


class _StubClient:
    def __init__(self, chunks: list[Any]) -> None:
        self.aio = type("_Aio", (), {"models": _StubModels(chunks)})()


def _capture_tool_calls(part: types.Part) -> list[dict[str, Any]]:
    from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter

    adapter = GoogleStreamAdapter(api_key="dummy-key", default_model="test-model")
    adapter._client = _StubClient([_chunk_with(part)])

    async def _run() -> list[dict[str, Any]]:
        done = None
        async for event in adapter.stream_chat(
            [{"role": "user", "content": "call it"}]
        ):
            if event.event_type == "done":
                done = event
        assert done is not None, "adapter never emitted a done event"
        return done.tool_calls

    return asyncio.run(_run())


@pytest.mark.regression
def test_capture_stashes_the_part_level_thought_signature():
    tool_calls = _capture_tool_calls(
        types.Part(
            function_call=types.FunctionCall(name="get_number", args={}),
            thought_signature=_SIGNATURE,
        )
    )
    assert len(tool_calls) == 1
    stashed = tool_calls[0][THOUGHT_SIGNATURE_KEY]
    # Stored base64-ENCODED so the tool-call dict stays JSON-serializable for
    # session persistence / event emission.
    assert isinstance(stashed, str)
    assert base64.b64decode(stashed) == _SIGNATURE


@pytest.mark.regression
def test_capture_stashes_nothing_when_the_model_issued_no_signature():
    """Opposite pole: Gemini 2.5's tool-call dict is byte-identical to pre-#2120."""
    tool_calls = _capture_tool_calls(
        types.Part(function_call=types.FunctionCall(name="get_number", args={}))
    )
    assert len(tool_calls) == 1
    assert THOUGHT_SIGNATURE_KEY not in tool_calls[0]
    assert set(tool_calls[0]) == {"id", "type", "function"}


@pytest.mark.regression
def test_full_capture_then_replay_round_trip():
    """The end-to-end contract: what turn 1 captured is what turn 2 replays."""
    tool_calls = _capture_tool_calls(
        types.Part(
            function_call=types.FunctionCall(name="get_number", args={"x": 1}),
            thought_signature=_SIGNATURE,
        )
    )
    _system, contents = _convert_messages_for_gemini(
        [
            {"role": "user", "content": "Call get_number."},
            {"role": "assistant", "content": "", "tool_calls": tool_calls},
        ]
    )
    model_turn = next(c for c in contents if c["role"] == "model")
    assert model_turn["parts"][0]["thought_signature"] == _SIGNATURE
    assert model_turn["parts"][0]["function_call"]["args"] == {"x": 1}
