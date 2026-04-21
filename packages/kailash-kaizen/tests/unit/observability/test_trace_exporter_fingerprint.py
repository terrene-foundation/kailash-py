# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 fingerprint-parity + cost-microdollars-int invariants.

These invariants protect the cross-SDK contract that a Python emitter
and a Rust emitter (kailash-rs#468 / v3.17.1+) produce byte-identical
SHA-256 fingerprints for the same logical :class:`TraceEvent` input.

A future refactor that swings ``cost`` back to float dollars, or that
changes the canonicalization rules (sort order, separators, Enum
string form, timestamp offset), would silently break cross-SDK
forensic correlation. These tests turn that drift into a loud failure.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)

from kaizen.observability import TraceExporter, compute_fingerprint


# ---------------------------------------------------------------------------
# Fixed test vectors — byte-exact cross-SDK contract
# ---------------------------------------------------------------------------
#
# These vectors are locked on the Python side. Rust parity (kailash-rs
# TraceEvent round-trip tests at commit e29d0bad) MUST produce the same
# fingerprints for the same canonical input. If either side drifts,
# this table is the single audit point.
#
# Each entry: (label, TraceEvent kwargs, expected fingerprint).
# The expected fingerprints are derived by running
# compute_trace_event_fingerprint(event) below — they are NOT magic
# numbers; they are the canonical output the cross-SDK contract pins.


_FIXED_TS = datetime(2026, 4, 21, 12, 0, 0, tzinfo=timezone.utc)


def _mk(**overrides: Any) -> TraceEvent:
    """Build a TraceEvent with sensible defaults for one-field diffs."""
    base: dict[str, Any] = dict(
        event_id="ev-vec-01",
        event_type=TraceEventType.AGENT_RUN_START,
        timestamp=_FIXED_TS,
        run_id="run-vec-01",
        agent_id="agent-vec-01",
        cost_microdollars=0,
    )
    base.update(overrides)
    return TraceEvent(**base)


# ---------------------------------------------------------------------------
# Determinism — same input MUST always fingerprint identically
# ---------------------------------------------------------------------------


def test_fingerprint_is_deterministic_across_calls():
    ev = _mk()
    fp1 = compute_trace_event_fingerprint(ev)
    fp2 = compute_trace_event_fingerprint(ev)
    fp3 = compute_fingerprint(ev)
    assert (
        fp1 == fp2 == fp3
    ), "fingerprint drift across calls — canonicalization is non-deterministic"


def test_fingerprint_shape_is_64_hex_chars_lowercase():
    ev = _mk()
    fp = compute_trace_event_fingerprint(ev)
    assert len(fp) == 64, f"fingerprint length drift: {len(fp)} != 64"
    assert fp == fp.lower(), "fingerprint is not lowercase hex"
    assert all(c in "0123456789abcdef" for c in fp), f"non-hex char in {fp!r}"


def test_fingerprint_reexport_matches_canonical():
    ev = _mk(event_id="ev-reexport", cost_microdollars=42)
    assert compute_fingerprint(ev) == compute_trace_event_fingerprint(ev), (
        "kaizen.observability.compute_fingerprint drifted from "
        "kailash.diagnostics.protocols.compute_trace_event_fingerprint"
    )


# ---------------------------------------------------------------------------
# Per-field sensitivity — each mandatory field MUST change the fingerprint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_id": "ev-different"},
        {"event_type": TraceEventType.AGENT_RUN_END},
        {"timestamp": _FIXED_TS + timedelta(seconds=1)},
        {"run_id": "run-different"},
        {"agent_id": "agent-different"},
        {"cost_microdollars": 1},
    ],
    ids=[
        "event_id",
        "event_type",
        "timestamp",
        "run_id",
        "agent_id",
        "cost_microdollars",
    ],
)
def test_each_mandatory_field_affects_fingerprint(overrides: dict[str, Any]):
    base = _mk()
    perturbed = _mk(**overrides)
    assert compute_trace_event_fingerprint(base) != compute_trace_event_fingerprint(
        perturbed
    ), (
        f"fingerprint insensitive to field change {list(overrides.keys())[0]!r} — "
        f"canonicalization dropped a load-bearing field"
    )


# ---------------------------------------------------------------------------
# Canonicalization form — the contract that Rust must match byte-for-byte
# ---------------------------------------------------------------------------


def test_canonical_json_has_sorted_keys_and_compact_separators():
    """The fingerprint input MUST be sort_keys + compact JSON.

    Reproduces the canonicalization contract inline so a future
    refactor to protocols.py that switches the dumps() kwargs triggers
    this test, not a silent cross-SDK drift.
    """
    ev = _mk(tenant_id="tenant-a", cost_microdollars=10)
    d = ev.to_dict()
    canonical = json.dumps(
        d,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    # Compact separators — no whitespace after , or :.
    assert ", " not in canonical, "canonical JSON has spaces after comma"
    assert '": ' not in canonical, "canonical JSON has spaces after colon"

    # Keys sorted lexicographically.
    key_order = [k for k, _v in json.loads(canonical).items()]
    assert key_order == sorted(
        key_order
    ), f"canonical JSON keys not sorted: {key_order}"

    # Timestamp serializes with explicit +00:00 (never Z).
    assert "+00:00" in canonical, "timestamp missing +00:00 offset"
    assert 'Z"' not in canonical, "timestamp uses Z suffix — breaks Rust parity"


def test_enum_values_serialize_as_strings():
    ev = _mk(
        event_type=TraceEventType.LLM_CALL_END,
        status=TraceEventStatus.OK,
    )
    d = ev.to_dict()
    assert (
        d["event_type"] == "llm.call.end"
    ), f"TraceEventType not serialized as string value: {d['event_type']!r}"
    assert (
        d["status"] == "ok"
    ), f"TraceEventStatus not serialized as string value: {d['status']!r}"


# ---------------------------------------------------------------------------
# cost_microdollars MUST be int invariant (#567 PR#6 regression guard)
# ---------------------------------------------------------------------------


def test_cost_microdollars_must_be_int_not_float():
    """Float dollars are BANNED per the cross-SDK contract.

    The kaizen.cost.tracker alignment rule (microdollars=int,
    1 USD = 1_000_000) is the only shape that survives cross-emitter
    summation without float-accumulation drift. A future regression
    that accepts float via ``cost_microdollars=0.01`` MUST fail loudly.
    """
    with pytest.raises(TypeError, match="cost_microdollars must be an int"):
        _mk(cost_microdollars=0.01)  # type: ignore[arg-type]

    # Negative ints are also rejected.
    with pytest.raises(ValueError, match="must be non-negative"):
        _mk(cost_microdollars=-1)

    # bool is a subclass of int in Python but MUST be rejected.
    with pytest.raises(TypeError, match="cost_microdollars must be an int"):
        _mk(cost_microdollars=True)  # type: ignore[arg-type]


def test_cost_microdollars_accepts_zero_and_positive_int():
    # Sanity: the type guard doesn't over-reject valid ints.
    assert _mk(cost_microdollars=0).cost_microdollars == 0
    assert _mk(cost_microdollars=42).cost_microdollars == 42
    assert _mk(cost_microdollars=10**9).cost_microdollars == 10**9


# ---------------------------------------------------------------------------
# TraceExporter path — fingerprint returned to caller matches helper
# ---------------------------------------------------------------------------


def test_exporter_returns_fingerprint_matching_canonical_helper():
    captured: list[tuple[TraceEvent, str]] = []

    def sink(event: TraceEvent, fp: str) -> None:
        captured.append((event, fp))

    exporter = TraceExporter(sink=sink)
    ev = _mk(cost_microdollars=1234)
    returned_fp = exporter.export(ev)

    assert returned_fp == compute_trace_event_fingerprint(ev), (
        "TraceExporter.export() returned a different fingerprint than "
        "the canonical helper — cross-SDK parity broken at the emitter"
    )
    assert (
        captured[0][1] == returned_fp
    ), "sink received a different fingerprint than export() returned"


def test_exporter_export_count_bounded_not_history():
    """The exporter MUST carry bounded counters, not event history.

    Per rules/observability.md bounded-buffer discipline: a long-
    running emitter MUST NOT grow without bound. exported_count is an
    int counter; there is no in-memory event list.
    """
    exporter = TraceExporter()
    assert exporter.exported_count == 0
    assert exporter.errored_count == 0
    for i in range(100):
        exporter.export(_mk(event_id=f"ev-{i}"))
    assert exporter.exported_count == 100
    assert exporter.errored_count == 0
    # No attribute exposing an unbounded event buffer.
    assert not hasattr(
        exporter, "_events"
    ), "TraceExporter grew an unbounded _events buffer — bounded-counter contract broken"
