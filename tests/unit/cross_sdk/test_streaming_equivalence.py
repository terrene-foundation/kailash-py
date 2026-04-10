# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK streaming event equivalence tests (SPEC-09 S2.5).

For each Python event class (TextDelta, ToolCallStart, ToolCallEnd,
TurnComplete, BudgetExhausted, ErrorEvent), constructs an instance with
vector data, serializes it, and compares against the loaded vector JSON.
This tests object-to-JSON (complementing test_streaming_vectors.py's
JSON-to-JSON).
"""

from __future__ import annotations

import pytest

from kailash.trust._json import canonical_json_dumps
from kaizen_agents.events import (
    BudgetExhausted,
    ErrorEvent,
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    TurnComplete,
)


def _event_to_wire_dict(event) -> dict:
    """Convert a StreamEvent to the cross-SDK wire dict.

    Strips the ``timestamp`` field (monotonic, not cross-SDK comparable)
    and returns the remaining fields as a dict suitable for canonical
    JSON comparison.
    """
    from dataclasses import asdict

    d = asdict(event)
    d.pop("timestamp", None)
    return d


def test_text_delta_serialization(load_vector):
    """TextDelta instance serializes to match the vector fixture."""
    vector = load_vector("streaming", "01-text-delta.json")
    event = TextDelta(text=vector["input"]["text"])
    wire = _event_to_wire_dict(event)
    assert canonical_json_dumps(wire) == vector["expected_canonical_json"]


def test_tool_call_start_serialization(load_vector):
    """ToolCallStart instance serializes to match the vector fixture."""
    vector = load_vector("streaming", "02-tool-call-start.json")
    inp = vector["input"]
    event = ToolCallStart(call_id=inp["call_id"], name=inp["name"])
    wire = _event_to_wire_dict(event)
    assert canonical_json_dumps(wire) == vector["expected_canonical_json"]


def test_tool_call_end_serialization(load_vector):
    """ToolCallEnd instance serializes to match the vector fixture."""
    vector = load_vector("streaming", "03-tool-call-end.json")
    inp = vector["input"]
    event = ToolCallEnd(
        call_id=inp["call_id"],
        name=inp["name"],
        result=inp["result"],
        error=inp["error"],
    )
    wire = _event_to_wire_dict(event)
    assert canonical_json_dumps(wire) == vector["expected_canonical_json"]


def test_turn_complete_serialization(load_vector):
    """TurnComplete instance serializes to match the vector fixture."""
    vector = load_vector("streaming", "04-turn-complete.json")
    inp = vector["input"]
    event = TurnComplete(text=inp["text"], usage=inp["usage"])
    wire = _event_to_wire_dict(event)
    # TurnComplete has additional fields (structured, iterations) not in
    # the cross-SDK wire format. Strip them for comparison.
    wire.pop("structured", None)
    wire.pop("iterations", None)
    assert canonical_json_dumps(wire) == vector["expected_canonical_json"]


def test_budget_exhausted_serialization(load_vector):
    """BudgetExhausted instance serializes to match the vector fixture."""
    vector = load_vector("streaming", "05-budget-exhausted.json")
    inp = vector["input"]
    event = BudgetExhausted(
        budget_usd=inp["budget_usd"],
        consumed_usd=inp["consumed_usd"],
    )
    wire = _event_to_wire_dict(event)
    assert canonical_json_dumps(wire) == vector["expected_canonical_json"]


def test_error_event_serialization(load_vector):
    """ErrorEvent instance serializes to match the vector fixture."""
    vector = load_vector("streaming", "06-error-event.json")
    inp = vector["input"]
    event = ErrorEvent(error=inp["error"], details=inp["details"])
    wire = _event_to_wire_dict(event)
    assert canonical_json_dumps(wire) == vector["expected_canonical_json"]
