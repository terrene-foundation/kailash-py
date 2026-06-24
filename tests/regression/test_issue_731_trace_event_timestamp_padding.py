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

2. :class:`TestCrossSDKFixtureParity` — conformance test that loads the
   canonical fixture file at ``test-vectors/trace-event-canonical.json`` and
   asserts that the corrected ``to_dict()`` produces byte-equal canonical JSON
   AND a matching SHA-256 fingerprint for every pinned vector. The fixture is
   python-self-consistent (issue #1402): kailash-rs is expected to emit
   identical bytes for identical inputs (per ``rules/cross-sdk-inspection.md``
   MUST Rule 4 — byte-vector pin contract), but the independent rust digest is
   verified at the post-Wave-6 cross-SDK gate, NOT in this repo's CI.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    _canonical_json,
    compute_trace_event_fingerprint,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "test-vectors" / "trace-event-canonical.json"
)

# Required named vectors — removing any fails loudly naming the missing vector
# (issue #1407); a count floor cannot detect a silently-deleted pinned vector.
_REQUIRED_VECTOR_NAMES = frozenset(
    {
        "V1_zero_microsecond",
        "V2_nonzero_microsecond",
        "V3_full_event",
        "V4_bmp_non_ascii_agent_id",
        "V5_above_bmp_emoji_tool_name",
        "V6_typed_scalar_payload",
    }
)


def _decode_typed(obj: object) -> object:
    """Reconstruct ``__pytype__``-tagged typed scalars from the fixture JSON.

    Inverse of ``test-vectors/regenerate_canonical_vectors.py::encode_typed``;
    the round-trip is validated by the byte pins below.
    """
    if isinstance(obj, dict):
        tag = obj.get("__pytype__")
        if tag == "Decimal":
            return Decimal(obj["repr"])
        if tag == "UUID":
            return UUID(obj["repr"])
        if tag == "datetime":
            return datetime.fromisoformat(obj["repr"])
        if tag == "set":
            return {_decode_typed(v) for v in obj["items"]}
        if tag == "bytes":
            return base64.b64decode(obj["b64"])
        return {k: _decode_typed(v) for k, v in obj.items()}
    return obj


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
    """Canonical-fixture conformance tests (Python side).

    The fixture at ``test-vectors/trace-event-canonical.json`` pins six vectors
    (V1: zero microsecond, V2: nonzero microsecond, V3: full event, V4: BMP
    non-ASCII agent_id, V5: above-BMP emoji tool_name, V6: typed-scalar payload)
    — see ``_REQUIRED_VECTOR_NAMES``. The fixture is python-self-consistent
    (issue #1402): these tests assert the kailash-py production path reproduces
    its bytes. kailash-rs is expected to emit identical bytes and has symmetric
    tests at ``crates/kailash-kaizen/tests/cross_sdk_trace_event.rs``, but that
    cross-SDK equality is verified at the post-Wave-6 cross-SDK gate, NOT in
    this repo's CI.
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
                value = input_repr[field_name]
                if field_name == "payload" and value is not None:
                    value = _decode_typed(value)  # __pytype__ → real Python objects
                kwargs[field_name] = value
        if "status" in input_repr:
            kwargs["status"] = TraceEventStatus(input_repr["status"])
        return TraceEvent(**kwargs)

    def test_fixture_loads(self, fixture: dict) -> None:
        assert fixture["spec_version"] == "1.1"

    def test_required_vectors_present(self, fixture: dict) -> None:
        """Issue #1407: assert each REQUIRED named vector is present. A count
        floor cannot detect a silently-deleted pinned vector; this names it."""
        present = {v["name"] for v in fixture["vectors"]}
        missing = _REQUIRED_VECTOR_NAMES - present
        assert not missing, f"trace-event fixture missing required vectors: {missing}"

    def test_every_vector_canonical_json_byte_equal(self, fixture: dict) -> None:
        # Assert against the PRODUCTION canonicalizer (issue #1404), not an
        # inline json.dumps duplicate — a production drift must fail here.
        for v in fixture["vectors"]:
            evt = self._construct_event(v["input_repr"])
            canonical = _canonical_json(evt)
            assert canonical == v["expected_canonical_json"], (
                f"vector {v['name']}: byte-divergence — "
                f"got {canonical!r}, expected {v['expected_canonical_json']!r}"
            )

    def test_every_vector_fingerprint_matches(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            evt = self._construct_event(v["input_repr"])
            fp = compute_trace_event_fingerprint(evt)
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


@pytest.mark.regression
class TestTypedScalarPayload:
    """The free ``payload`` dict is the one field ``to_dict()`` does not
    pre-normalize, so typed scalars in it MUST route through the canonical
    ``canonical_scalars`` whitelist, never ``default=str`` (issue #1403/#1405).
    """

    def _make_event(self, payload: dict) -> TraceEvent:
        return TraceEvent(
            event_id="evt-typed",
            event_type=TraceEventType.AGENT_STEP,
            timestamp=datetime(2026, 4, 20, 12, 0, 0, 654321, tzinfo=timezone.utc),
            run_id="run-typed",
            agent_id="agent-typed",
            cost_microdollars=0,
            payload=payload,
        )

    def test_typed_payload_uses_canonical_whitelist(self) -> None:
        evt = self._make_event(
            {
                "amount": Decimal("3.14"),
                "deadline": datetime.fromisoformat("2026-05-06T07:08:09.000999+00:00"),
                "labels": {"z", "a", "m"},
            }
        )
        canonical = _canonical_json(evt)
        # Decimal full precision, datetime isoformat, set → sorted list — never
        # implementation-defined str().
        assert '"amount":"3.14"' in canonical, canonical
        assert '"deadline":"2026-05-06T07:08:09.000999+00:00"' in canonical, canonical
        assert '"labels":["a","m","z"]' in canonical, canonical

    def test_non_whitelisted_payload_raises_not_str_coerced(self) -> None:
        """A non-JSON-native, non-whitelisted value MUST raise (no silent
        ``str()`` coercion) — the structural proof ``default=str`` is gone."""
        evt = self._make_event({"obj": object()})
        with pytest.raises(TypeError):
            compute_trace_event_fingerprint(evt)
