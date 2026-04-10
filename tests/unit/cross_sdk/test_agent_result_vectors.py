# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK AgentResult equivalence tests (SPEC-09 S3.3).

Verifies that the canonical AgentResult field set round-trips through
JSON serialization identically to the fixture files consumed by both
Python and Rust SDKs for parity validation per EATP D6.

Each fixture has exactly: ``text``, ``model``, ``usage`` (with
``prompt_tokens``, ``completion_tokens``, ``total_tokens``),
``structured``, ``finish_reason``.
"""

from __future__ import annotations

import json

import pytest

from kailash.trust._json import canonical_json_dumps


@pytest.mark.parametrize(
    "filename",
    [
        "01-basic-text.json",
        "02-structured-output.json",
        "03-tool-use.json",
        "04-multi-turn-usage.json",
    ],
)
def test_agent_result_canonical_round_trip(load_vector, filename):
    """AgentResult input dict produces fixture-exact canonical JSON.

    Verifies the canonical field set (text, model, usage, structured,
    finish_reason) serializes to sorted-key JSON matching the fixture.
    """
    vector = load_vector("agent-result", filename)
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    # Canonical JSON of the input dict must match fixture expectation
    actual = canonical_json_dumps(input_obj)
    assert actual == expected, (
        f"Canonical JSON mismatch for {filename}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )

    # Round-trip: parse canonical back and re-serialize
    round_tripped = json.loads(expected, strict=True)
    assert canonical_json_dumps(round_tripped) == expected


@pytest.mark.parametrize(
    "filename",
    [
        "01-basic-text.json",
        "02-structured-output.json",
        "03-tool-use.json",
        "04-multi-turn-usage.json",
    ],
)
def test_agent_result_has_canonical_fields(load_vector, filename):
    """Every AgentResult fixture has exactly the required field set.

    Per SPEC-09 S3.3, every fixture MUST have: text, model, usage
    (with prompt_tokens, completion_tokens, total_tokens), structured,
    finish_reason.
    """
    vector = load_vector("agent-result", filename)
    input_obj = vector["input"]

    required_fields = {"text", "model", "usage", "structured", "finish_reason"}
    assert set(input_obj.keys()) == required_fields, (
        f"Field set mismatch for {filename}: "
        f"expected {required_fields}, got {set(input_obj.keys())}"
    )

    # Usage sub-object has exactly the 3 token count fields (integers)
    usage = input_obj["usage"]
    usage_fields = {"prompt_tokens", "completion_tokens", "total_tokens"}
    assert set(usage.keys()) == usage_fields
    for field_name in usage_fields:
        assert isinstance(
            usage[field_name], int
        ), f"usage.{field_name} must be int, got {type(usage[field_name])}"
