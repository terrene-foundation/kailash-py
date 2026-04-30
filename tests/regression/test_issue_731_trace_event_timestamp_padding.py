"""Regression tests for #731 — TraceEvent.to_dict() timestamp microsecond padding.

The defect: ``datetime.isoformat()`` in CPython elides the decimal portion
when ``microsecond == 0``, breaking cross-SDK byte-equivalence with kailash-rs
(which always emits six microsecond digits via its own canonical path).

The fix: ``datetime.isoformat(timespec="microseconds")`` always emits six
microsecond digits.

These tests are paired:

1. :class:`TestMicrosecondPaddingBehavior` — direct behavioral assertion
   that the corrected ``to_dict()`` output ALWAYS contains six microsecond
   digits, regardless of the underlying ``datetime`` value.

2. :class:`TestCrossSDKFixtureParity` — Tier-2 conformance test that loads
   the canonical fixture file at ``test-vectors/trace-event-canonical.json``
   and asserts that the corrected ``to_dict()`` produces byte-equal canonical
   JSON AND a matching SHA-256 fingerprint for every pinned vector. The
   fixture is the cross-SDK contract — kailash-rs is expected to emit
   identical bytes for identical inputs (per ``rules/cross-sdk-inspection.md``
   MUST Rule 4 — byte-vector pin contract).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "test-vectors" / "trace-event-canonical.json"
)


@pytest.mark.regression
class TestMicrosecondPaddingBehavior:
    """Direct behavioral guards on ``TraceEvent.to_dict()`` timestamp shape."""

    def _make_event(self, ts: datetime) -> TraceEvent:
        return TraceEvent(
            event_id="evt-731",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=ts,
            run_id="run-731",
            agent_id="agent-731",
            cost_microdollars=0,
        )

    def test_zero_microsecond_is_padded_to_six_digits(self) -> None:
        ts = datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
        out = self._make_event(ts).to_dict()["timestamp"]
        assert out == "2026-04-20T12:00:00.000000+00:00", out

    def test_nonzero_microsecond_round_trips_byte_for_byte(self) -> None:
        ts = datetime(2026, 4, 20, 12, 0, 0, 123456, tzinfo=timezone.utc)
        out = self._make_event(ts).to_dict()["timestamp"]
        assert out == "2026-04-20T12:00:00.123456+00:00", out

    def test_microsecond_999999_is_emitted_in_full(self) -> None:
        ts = datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
        out = self._make_event(ts).to_dict()["timestamp"]
        assert out == "2026-12-31T23:59:59.999999+00:00", out

    def test_to_dict_timestamp_always_has_six_microsecond_digits(self) -> None:
        """Structural invariant: regardless of input, the ``timestamp`` field
        in ``to_dict()`` output always carries six microsecond digits between
        ``.`` and the ``+00:00`` offset.
        """
        for microsecond in (0, 1, 999, 100_000, 999_999):
            ts = datetime(2026, 4, 20, 12, 0, 0, microsecond, tzinfo=timezone.utc)
            out = self._make_event(ts).to_dict()["timestamp"]
            decimal = out.split(".")[1].split("+")[0]
            assert len(decimal) == 6, (
                f"microsecond={microsecond} produced decimal={decimal!r} "
                f"(len={len(decimal)}); expected exactly 6 digits."
            )


@pytest.mark.regression
class TestCrossSDKFixtureParity:
    """Cross-SDK canonical-fixture conformance tests.

    The fixture at ``test-vectors/trace-event-canonical.json`` pins three
    vectors (V1: zero microsecond, V2: nonzero microsecond, V3: full event)
    that BOTH kailash-py and kailash-rs MUST produce byte-for-byte. These
    tests exercise the kailash-py side; the kailash-rs side has the
    symmetric tests at ``crates/kailash-kaizen/tests/cross_sdk_trace_event.rs``.
    """

    @pytest.fixture(scope="class")
    def fixture(self) -> dict:
        assert _FIXTURE_PATH.exists(), (
            f"cross-SDK fixture missing at {_FIXTURE_PATH}; "
            f"regenerate via the snippet in tests/regression/"
            f"test_issue_731_trace_event_timestamp_padding.py docstring."
        )
        return json.loads(_FIXTURE_PATH.read_text())

    def _construct_event(self, input_repr: dict) -> TraceEvent:
        ts = datetime.fromisoformat(input_repr["timestamp"])
        kwargs: dict = {
            "event_id": input_repr["event_id"],
            "event_type": TraceEventType(input_repr["event_type"]),
            "timestamp": ts,
            "run_id": input_repr["run_id"],
            "agent_id": input_repr["agent_id"],
            "cost_microdollars": input_repr["cost_microdollars"],
        }
        # Forward any optional fields present in the fixture.
        optional_fields = (
            "parent_event_id",
            "trace_id",
            "span_id",
            "tenant_id",
            "envelope_id",
            "tool_name",
            "llm_model",
            "prompt_tokens",
            "completion_tokens",
            "duration_ms",
            "payload_hash",
            "payload",
        )
        for field_name in optional_fields:
            if field_name in input_repr:
                kwargs[field_name] = input_repr[field_name]
        if "status" in input_repr:
            kwargs["status"] = TraceEventStatus(input_repr["status"])
        return TraceEvent(**kwargs)

    def test_fixture_loads(self, fixture: dict) -> None:
        assert fixture["spec_version"] == "1.0"
        assert len(fixture["vectors"]) >= 3

    def test_every_vector_canonical_json_byte_equal(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            evt = self._construct_event(v["input_repr"])
            d = evt.to_dict()
            canonical = json.dumps(
                d,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                default=str,
            )
            assert canonical == v["expected_canonical_json"], (
                f"vector {v['name']}: byte-divergence — "
                f"got {canonical!r}, expected {v['expected_canonical_json']!r}"
            )

    def test_every_vector_fingerprint_matches(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            evt = self._construct_event(v["input_repr"])
            d = evt.to_dict()
            canonical = json.dumps(
                d,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                default=str,
            )
            fp = hashlib.sha256(canonical.encode()).hexdigest()
            assert fp == v["expected_fingerprint"], (
                f"vector {v['name']}: fingerprint divergence — "
                f"got {fp}, expected {v['expected_fingerprint']}"
            )

    def test_compute_trace_event_fingerprint_matches_fixture(
        self, fixture: dict
    ) -> None:
        """The public ``compute_trace_event_fingerprint`` helper MUST agree
        with the fixture's expected_fingerprint for every vector. This is
        the consumer-facing API kailash-rs callers will see."""
        for v in fixture["vectors"]:
            evt = self._construct_event(v["input_repr"])
            assert compute_trace_event_fingerprint(evt) == v["expected_fingerprint"], (
                f"vector {v['name']}: compute_trace_event_fingerprint() "
                f"disagrees with fixture expected_fingerprint."
            )
