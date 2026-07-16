# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-2 — `kaizen.llm._legacy_shape` pure-function tests.

Covers the legacy/four-axis response shape reconciliation used by the
dual-run shadow validation in
``kaizen.nodes.ai.llm_agent.LLMAgentNode._run_llm_dual_run_shadow``:

* ``to_legacy_shape`` — maps an ``LlmClient.complete()`` result onto legacy
  response field names (token-key remap, ``tool_calls`` passthrough).
* ``diff_legacy_vs_fouraxis`` — field-level divergence detection, empty list
  on parity, and (governance requirement) divergence strings that never
  embed raw generated text, tool-call arguments, or any credential.

Both functions are pure (no I/O); these are plain Tier-1 unit tests.
"""

from __future__ import annotations

from kaizen.llm._legacy_shape import diff_legacy_vs_fouraxis, to_legacy_shape

# ---------------------------------------------------------------------------
# to_legacy_shape
# ---------------------------------------------------------------------------


def test_to_legacy_shape_maps_text_and_stop_reason():
    four_axis = {
        "text": "pong",
        "stop_reason": "stop",
        "model": "gpt-4o-mini",
        "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
    }
    legacy = to_legacy_shape(four_axis)
    assert legacy["content"] == "pong"
    assert legacy["finish_reason"] == "stop"
    assert legacy["model"] == "gpt-4o-mini"


def test_to_legacy_shape_remaps_token_keys():
    four_axis = {
        "text": "pong",
        "stop_reason": "stop",
        "model": "gpt-4o-mini",
        "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
    }
    legacy = to_legacy_shape(four_axis)
    assert legacy["usage"] == {
        "prompt_tokens": 5,
        "completion_tokens": 2,
        "total_tokens": 7,
    }


def test_to_legacy_shape_computes_total_tokens_when_absent():
    four_axis = {
        "text": "pong",
        "stop_reason": "stop",
        "model": "gpt-4o-mini",
        "usage": {"input_tokens": 5, "output_tokens": 2},
    }
    legacy = to_legacy_shape(four_axis)
    assert legacy["usage"]["total_tokens"] == 7


def test_to_legacy_shape_computes_total_tokens_with_missing_counts():
    four_axis = {"text": "pong", "stop_reason": "stop", "usage": {}}
    legacy = to_legacy_shape(four_axis)
    assert legacy["usage"] == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": 0,
    }


def test_to_legacy_shape_passes_tool_calls_through_when_present():
    four_axis = {
        "text": "",
        "stop_reason": "tool_calls",
        "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "f", "arguments": "{}"},
            }
        ],
    }
    legacy = to_legacy_shape(four_axis)
    assert legacy["tool_calls"] == four_axis["tool_calls"]


def test_to_legacy_shape_omits_tool_calls_key_when_absent():
    four_axis = {"text": "hi", "stop_reason": "stop", "usage": {}}
    legacy = to_legacy_shape(four_axis)
    assert "tool_calls" not in legacy


def test_to_legacy_shape_defensive_on_missing_keys():
    # Pure defensiveness: no exception on a bare/partial dict.
    assert to_legacy_shape({}) == {
        "content": None,
        "finish_reason": None,
        "model": None,
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": 0,
        },
    }


def test_to_legacy_shape_defensive_on_non_dict_input():
    assert to_legacy_shape(None) == to_legacy_shape({})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# diff_legacy_vs_fouraxis
# ---------------------------------------------------------------------------

_BASE_LEGACY = {
    "content": "pong",
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}
_BASE_MAPPED = {
    "content": "pong",
    "finish_reason": "stop",
    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
}


def test_diff_returns_empty_list_on_parity():
    assert diff_legacy_vs_fouraxis(_BASE_LEGACY, _BASE_MAPPED) == []


def test_diff_detects_content_mismatch():
    mapped = dict(_BASE_MAPPED, content="ping")
    divergences = diff_legacy_vs_fouraxis(_BASE_LEGACY, mapped)
    assert any(d.startswith("content:") for d in divergences)


def test_diff_detects_content_presence_mismatch():
    mapped = dict(_BASE_MAPPED, content=None)
    divergences = diff_legacy_vs_fouraxis(_BASE_LEGACY, mapped)
    assert any(d.startswith("content:") for d in divergences)


def test_diff_detects_tool_calls_presence_mismatch():
    legacy = dict(_BASE_LEGACY, tool_calls=[{"id": "1"}])
    mapped = dict(_BASE_MAPPED)  # no tool_calls key
    divergences = diff_legacy_vs_fouraxis(legacy, mapped)
    assert any(d.startswith("tool_calls:") for d in divergences)


def test_diff_detects_tool_calls_count_mismatch():
    legacy = dict(_BASE_LEGACY, tool_calls=[{"id": "1"}, {"id": "2"}])
    mapped = dict(_BASE_MAPPED, tool_calls=[{"id": "1"}])
    divergences = diff_legacy_vs_fouraxis(legacy, mapped)
    assert any("tool_calls" in d and "count" in d for d in divergences)


def test_diff_tool_calls_parity_when_both_present_and_equal_count():
    legacy = dict(_BASE_LEGACY, tool_calls=[{"id": "1"}])
    mapped = dict(_BASE_MAPPED, tool_calls=[{"id": "1", "type": "function"}])
    divergences = diff_legacy_vs_fouraxis(legacy, mapped)
    assert not any(d.startswith("tool_calls:") for d in divergences)


def test_diff_detects_finish_reason_mismatch():
    mapped = dict(_BASE_MAPPED, finish_reason="length")
    divergences = diff_legacy_vs_fouraxis(_BASE_LEGACY, mapped)
    assert "finish_reason: value mismatch" in divergences


def test_diff_detects_token_count_mismatch():
    mapped = dict(
        _BASE_MAPPED,
        usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    )
    divergences = diff_legacy_vs_fouraxis(_BASE_LEGACY, mapped)
    assert any(d.startswith("usage.completion_tokens:") for d in divergences)
    assert any(d.startswith("usage.total_tokens:") for d in divergences)
    assert not any(d.startswith("usage.prompt_tokens:") for d in divergences)


def test_diff_defensive_on_non_dict_input():
    assert diff_legacy_vs_fouraxis(None, None) == []  # type: ignore[arg-type]


def test_diff_defensive_on_missing_usage_key():
    assert diff_legacy_vs_fouraxis({"content": "hi"}, {"content": "hi"}) == []


# ---------------------------------------------------------------------------
# Governance: divergence strings NEVER embed raw content / secrets.
# ---------------------------------------------------------------------------

_SECRET_CANARY = "sk-super-secret-api-key-do-not-leak"
_RAW_CONTENT_CANARY = "THE-EXACT-GENERATED-RESPONSE-TEXT-CANARY"


def test_diff_divergence_strings_never_contain_raw_content_or_secrets():
    legacy = {
        "content": f"{_RAW_CONTENT_CANARY}-legacy {_SECRET_CANARY}",
        "finish_reason": "stop",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "f",
                    "arguments": f'{{"key": "{_SECRET_CANARY}"}}',
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    mapped = {
        "content": f"{_RAW_CONTENT_CANARY}-four-axis-different",
        "finish_reason": "length",
        # tool_calls presence differs too (absent here).
        "usage": {"prompt_tokens": 90, "completion_tokens": 40, "total_tokens": 130},
    }

    divergences = diff_legacy_vs_fouraxis(legacy, mapped)

    # Sanity: the fixture actually produced multiple divergences to check.
    assert len(divergences) >= 4

    joined = "\n".join(divergences)
    assert _SECRET_CANARY not in joined
    assert _RAW_CONTENT_CANARY not in joined
    assert legacy["content"] not in joined
    assert mapped["content"] not in joined
