# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK streaming event vector tests (SPEC-09 S2.5).

Verifies that each streaming event fixture's ``input`` dict serializes
to canonical JSON matching the fixture's ``expected_canonical_json``.
Both Python and Rust SDKs consume these identical JSON files.
"""

from __future__ import annotations

import json

import pytest

from kailash.trust._json import canonical_json_dumps


@pytest.mark.parametrize(
    "filename",
    [
        "01-text-delta.json",
        "02-tool-call-start.json",
        "03-tool-call-end.json",
        "04-turn-complete.json",
        "05-budget-exhausted.json",
        "06-error-event.json",
    ],
)
def test_streaming_vector_canonical_round_trip(load_vector, filename):
    """Streaming event input dict produces fixture-exact canonical JSON.

    Each fixture defines the wire-format shape both SDKs must agree on.
    """
    vector = load_vector("streaming", filename)
    input_obj = vector["input"]
    expected = vector["expected_canonical_json"]

    actual = canonical_json_dumps(input_obj)
    assert actual == expected, (
        f"Canonical JSON mismatch for {filename}:\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}"
    )

    # Round-trip: parse canonical back and re-serialize
    round_tripped = json.loads(expected, strict=True)
    assert canonical_json_dumps(round_tripped) == expected


def test_budget_exhausted_vector_has_required_fields(load_vector):
    """BudgetExhausted vector has ``budget_usd`` and ``consumed_usd``.

    Per SPEC-09 S8.4, this is the agreed shape for budget exhaustion
    events across both SDKs.
    """
    vector = load_vector("streaming", "05-budget-exhausted.json")
    input_obj = vector["input"]
    assert input_obj["event_type"] == "budget_exhausted"
    assert "budget_usd" in input_obj
    assert "consumed_usd" in input_obj
    assert isinstance(input_obj["budget_usd"], (int, float))
    assert isinstance(input_obj["consumed_usd"], (int, float))


def test_all_streaming_vectors_have_event_type(load_vector):
    """Every streaming vector has an ``event_type`` discriminator."""
    filenames = [
        "01-text-delta.json",
        "02-tool-call-start.json",
        "03-tool-call-end.json",
        "04-turn-complete.json",
        "05-budget-exhausted.json",
        "06-error-event.json",
    ]
    for filename in filenames:
        vector = load_vector("streaming", filename)
        assert "event_type" in vector["input"], f"{filename} missing event_type field"
        assert isinstance(vector["input"]["event_type"], str)
