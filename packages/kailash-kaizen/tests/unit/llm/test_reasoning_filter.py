# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Reasoning-model sampling-param filter tests (#1720 Wave-1b).

Covers `kaizen.llm.reasoning_filter` (the module-level port of the legacy
`OpenAIProvider._filter_reasoning_model_params` family) AND its wiring into
`openai_chat.build_request_payload`:

* o1/o3 reasoning models DROP temperature/top_p/frequency_penalty/
  presence_penalty entirely.
* gpt-5 FORCES temperature=1.0 and drops top_p/frequency_penalty/
  presence_penalty.
* Every other model is an untouched (byte-neutral) passthrough.
* The four-axis `openai_chat` wire payload reflects the filter — including
  preserving the EXACT pre-existing key order for the byte-neutral case.

All assertions are behavioral (call the function / build the payload, assert
the returned value) per `rules/testing.md` — no source-grep.
"""

from __future__ import annotations

import json

import pytest

from kaizen.llm.deployment import CompletionRequest
from kaizen.llm.reasoning_filter import (
    filter_reasoning_model_params,
    is_reasoning_model,
    requires_temperature_1,
)
from kaizen.llm.wire_protocols import openai_chat


# ---------------------------------------------------------------------------
# is_reasoning_model / requires_temperature_1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    ["o1", "o1-mini", "o1-preview", "o3", "o3-mini", "O1-MINI", "O3"],
)
def test_is_reasoning_model_true_for_o1_o3_family(model: str) -> None:
    assert is_reasoning_model(model) is True


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-5",
        "gpt-5-mini",
        "claude-3-5-sonnet",
        "",
        "o4-mini",
    ],
)
def test_is_reasoning_model_false_for_non_o1_o3(model: str) -> None:
    assert is_reasoning_model(model) is False


@pytest.mark.parametrize(
    "model", ["gpt-5", "gpt-5-mini", "gpt5", "GPT-5", "gpt-5.6-sol"]
)
def test_requires_temperature_1_true_for_gpt5_family(model: str) -> None:
    assert requires_temperature_1(model) is True


@pytest.mark.parametrize(
    "model", ["gpt-4o", "gpt-4-turbo", "o1", "o3-mini", "claude-3-5-sonnet", ""]
)
def test_requires_temperature_1_false_for_non_gpt5(model: str) -> None:
    assert requires_temperature_1(model) is False


def test_is_reasoning_model_false_for_falsy_model() -> None:
    assert is_reasoning_model("") is False
    assert is_reasoning_model(None) is False  # type: ignore[arg-type]


def test_requires_temperature_1_false_for_falsy_model() -> None:
    assert requires_temperature_1("") is False
    assert requires_temperature_1(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# filter_reasoning_model_params
# ---------------------------------------------------------------------------


def test_o1_o3_drops_all_four_sampling_params_when_present() -> None:
    params = {
        "temperature": 0.7,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.2,
    }
    filtered = filter_reasoning_model_params("o1-mini", params)
    assert filtered == {}
    # original dict untouched — no in-place mutation.
    assert params == {
        "temperature": 0.7,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.2,
    }


def test_o3_drops_only_the_keys_present() -> None:
    filtered = filter_reasoning_model_params("o3", {"temperature": 0.5})
    assert filtered == {}


def test_o1_o3_does_not_add_any_key() -> None:
    filtered = filter_reasoning_model_params("o1", {})
    assert filtered == {}


def test_o1_o3_leaves_non_sampling_keys_untouched() -> None:
    # filter_reasoning_model_params only knows about the 4 sampling keys —
    # any other key in the dict (defensive: callers only ever pass sampling
    # keys today) passes through unchanged.
    filtered = filter_reasoning_model_params(
        "o1", {"temperature": 0.7, "unrelated": "keep-me"}
    )
    assert filtered == {"unrelated": "keep-me"}


def test_gpt5_forces_temperature_1_and_drops_top_p_and_penalties() -> None:
    params = {
        "temperature": 0.3,
        "top_p": 0.8,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.5,
    }
    filtered = filter_reasoning_model_params("gpt-5", params)
    assert filtered == {"temperature": 1.0}
    # original dict untouched.
    assert params["temperature"] == 0.3


def test_gpt5_forces_temperature_1_even_when_caller_never_set_it() -> None:
    """gpt-5 400s on the server-side default too — force temperature=1.0
    unconditionally, matching the legacy `OpenAIProvider` behavior."""
    filtered = filter_reasoning_model_params("gpt-5", {})
    assert filtered == {"temperature": 1.0}


def test_gpt5_temperature_already_1_stays_1_and_drops_top_p() -> None:
    filtered = filter_reasoning_model_params(
        "gpt-5-mini", {"temperature": 1.0, "top_p": 0.7}
    )
    assert filtered == {"temperature": 1.0}


def test_unknown_model_returns_unchanged_copy() -> None:
    params = {"temperature": 0.7, "top_p": 0.9, "frequency_penalty": 0.1}
    filtered = filter_reasoning_model_params("gpt-4o", params)
    assert filtered == params
    # A COPY — mutating the result must not mutate the caller's dict.
    filtered["temperature"] = 999.0
    assert params["temperature"] == 0.7


def test_unknown_model_empty_params_returns_empty_dict() -> None:
    assert filter_reasoning_model_params("gpt-4o", {}) == {}


def test_empty_model_string_is_unknown_passthrough() -> None:
    params = {"temperature": 0.5}
    assert filter_reasoning_model_params("", params) == params


# ---------------------------------------------------------------------------
# openai_chat.build_request_payload wiring
# ---------------------------------------------------------------------------


def _req(model: str, **kwargs) -> CompletionRequest:
    return CompletionRequest(
        model=model, messages=[{"role": "user", "content": "hi"}], **kwargs
    )


@pytest.mark.parametrize("model", ["o1", "o1-mini", "o3", "o3-mini"])
def test_openai_chat_payload_drops_sampling_for_o1_o3(model: str) -> None:
    req = _req(
        model,
        temperature=0.7,
        top_p=0.9,
        frequency_penalty=0.2,
        presence_penalty=0.3,
        max_tokens=64,
    )
    payload = openai_chat.build_request_payload(req)
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "frequency_penalty" not in payload
    assert "presence_penalty" not in payload
    # unrelated fields still emitted.
    assert payload["max_completion_tokens"] == 64
    assert payload["model"] == model


@pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "gpt-5.6-sol"])
def test_openai_chat_payload_forces_temperature_1_for_gpt5(model: str) -> None:
    req = _req(
        model,
        temperature=0.2,
        top_p=0.9,
        frequency_penalty=0.2,
        presence_penalty=0.3,
    )
    payload = openai_chat.build_request_payload(req)
    assert payload["temperature"] == 1.0
    assert "top_p" not in payload
    assert "frequency_penalty" not in payload
    assert "presence_penalty" not in payload


def test_openai_chat_payload_forces_temperature_1_for_gpt5_even_unset() -> None:
    req = _req("gpt-5")  # caller never set temperature at all
    payload = openai_chat.build_request_payload(req)
    assert payload["temperature"] == 1.0


def test_openai_chat_payload_untouched_for_non_reasoning_model_with_sampling_set() -> (
    None
):
    req = _req(
        "gpt-4o",
        temperature=0.6,
        top_p=0.95,
        frequency_penalty=0.1,
        presence_penalty=0.2,
    )
    payload = openai_chat.build_request_payload(req)
    assert payload["temperature"] == 0.6
    assert payload["top_p"] == 0.95
    assert payload["frequency_penalty"] == 0.1
    assert payload["presence_penalty"] == 0.2


def test_openai_chat_payload_byte_neutral_for_non_reasoning_model_unset_sampling() -> (
    None
):
    """AC: for a NON-reasoning model with unset sampling, the payload MUST
    stay byte-identical to the pre-filter shape."""
    req = _req("gpt-4o", max_tokens=64)
    payload = openai_chat.build_request_payload(req)
    assert payload == {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
    }
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "frequency_penalty" not in payload
    assert "presence_penalty" not in payload
    # And the exact serialized bytes are what a pre-filter build would have
    # produced — key order matters for the cross-SDK byte-parity contract.
    assert list(payload.keys()) == ["model", "messages", "max_tokens"]


def test_openai_chat_payload_key_order_unchanged_full_featured_non_reasoning() -> None:
    """Every #1720 Wave-1a/1b field set on a non-reasoning model preserves
    the EXACT pre-filter key insertion order (byte-parity contract)."""
    req = _req(
        "gpt-4o",
        temperature=0.5,
        top_p=0.9,
        max_tokens=64,
        stop=["END"],
        stream=True,
        user="u1",
        tools=[{"type": "function", "function": {"name": "f"}}],
        response_format={"type": "json_object"},
        seed=7,
        logit_bias={"123": -100.0},
        frequency_penalty=0.1,
        presence_penalty=0.2,
        n=2,
    )
    payload = openai_chat.build_request_payload(req)
    assert list(payload.keys()) == [
        "model",
        "messages",
        "temperature",
        "top_p",
        "max_tokens",
        "stop",
        "stream",
        "user",
        "tools",
        "tool_choice",
        "response_format",
        "seed",
        "logit_bias",
        "frequency_penalty",
        "presence_penalty",
        "n",
    ]
    # And the whole payload round-trips through json.dumps without error —
    # exercising the exact serialization the wire send-path performs.
    json.dumps(payload)


def test_openai_chat_payload_reasoning_model_key_order_has_no_gaps() -> None:
    """o1 drops sampling keys entirely — the remaining keys keep their
    relative order (no empty/None placeholders left behind)."""
    req = _req(
        "o1-mini",
        temperature=0.5,
        top_p=0.9,
        max_tokens=64,
        seed=7,
        frequency_penalty=0.1,
        presence_penalty=0.2,
        n=2,
    )
    payload = openai_chat.build_request_payload(req)
    assert list(payload.keys()) == [
        "model",
        "messages",
        "max_completion_tokens",
        "seed",
        "n",
    ]
