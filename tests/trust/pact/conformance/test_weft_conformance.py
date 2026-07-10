# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""WEFT (#1591) conformance + invariant suite.

Byte-pins the WEFT citable-event schema against committed vectors and exercises
its two load-bearing invariants:

* Reader MUST-IGNORE unknown ``kind`` (forward-compat).
* Distributor fails CLOSED on a missing required ``HumanGate``.

The same vectors are validated by the Rust SDK to ensure cross-implementation
conformance. ``encoding="utf-8"`` on EVERY vector read is LOAD-BEARING (issue
#1590 Windows-CI fix): a locale-default read (cp1252 on Windows) mangles the
unicode payloads and diverges the RFC 8785 (JCS) content hash.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kailash.trust._jcs import jcs_encode, jcs_subject_hash
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.weft import (
    MissingGateError,
    UnknownWeftKindError,
    WeftDistributor,
    WeftError,
    WeftEvent,
    WeftKind,
    read_weft_events,
)

VECTORS_DIR = Path(__file__).parent / "vectors"

# The 10 byte-pinned WEFT serialization vectors (input + canonical + content hash).
WEFT_EVENT_VECTORS = [
    "weft_mint.json",
    "weft_human_gate.json",
    "weft_distribute.json",
    "weft_decline.json",
    "weft_obsolete.json",
    "weft_distribute_chained.json",
    "weft_unicode_payload.json",
    "weft_nested_payload.json",
    "weft_bigint_payload.json",
    "weft_scalar_payload.json",
]

# The full WEFT-family vector set for the integrity check (12 = 10 event vectors
# + the unknown-kind reader vector + the JCS big-integer subject vector).
ALL_WEFT_VECTORS = [
    *WEFT_EVENT_VECTORS,
    "weft_unknown_kind.json",
    "jcs_bigint_subject.json",
]


def _load_vector(filename: str) -> dict[str, Any]:
    """Load a vector JSON file with an explicit utf-8 decode (issue #1590)."""
    with open(VECTORS_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Byte-pinned serialization + round-trip
# ---------------------------------------------------------------------------


class TestWeftEventSerialization:
    """Byte-pin every WEFT event vector's canonical JSON + content hash."""

    @pytest.mark.parametrize("vector_file", WEFT_EVENT_VECTORS)
    def test_weft_event_canonical_and_hash_match_vector(self, vector_file: str) -> None:
        vector = _load_vector(vector_file)
        event = WeftEvent.from_dict(vector["input"])

        assert event.canonical_json() == vector["expected_canonical_json"], (
            f"WEFT canonical JSON mismatch for {vector_file}.\n"
            f"Got:      {event.canonical_json()}\n"
            f"Expected: {vector['expected_canonical_json']}"
        )
        assert event.content_hash() == vector["expected_content_hash"], (
            f"WEFT content hash mismatch for {vector_file}.\n"
            f"Got:      {event.content_hash()}\n"
            f"Expected: {vector['expected_content_hash']}"
        )

    @pytest.mark.parametrize("vector_file", WEFT_EVENT_VECTORS)
    def test_weft_event_roundtrip_byte_stable(self, vector_file: str) -> None:
        """to_dict -> from_dict -> to_dict is byte-stable (canonical unchanged)."""
        vector = _load_vector(vector_file)
        event = WeftEvent.from_dict(vector["input"])
        roundtripped = WeftEvent.from_dict(event.to_dict())

        assert roundtripped.to_dict() == event.to_dict()
        assert roundtripped.canonical_json() == event.canonical_json()
        assert roundtripped.content_hash() == event.content_hash()
        # every field survives the round-trip
        assert roundtripped.kind == event.kind
        assert roundtripped.prev_link == event.prev_link
        assert roundtripped.payload == event.payload

    def test_content_hash_binds_prev_link(self) -> None:
        """prev_link is part of the citable pre-image (chain is tamper-evident)."""
        base = _load_vector("weft_distribute_chained.json")["input"]
        original = WeftEvent.from_dict(base)
        mutated_dict = dict(base)
        mutated_dict["prev_link"] = "sha256:" + "f" * 64
        mutated = WeftEvent.from_dict(mutated_dict)
        assert mutated.content_hash() != original.content_hash()


# ---------------------------------------------------------------------------
# Invariant 1: reader MUST-IGNORE unknown kind (forward-compat)
# ---------------------------------------------------------------------------


class TestWeftUnknownKindMustIgnore:
    """A reader ignores an unrecognized kind; strict from_dict raises."""

    def test_unknown_kind_vector_reader_disposition_is_ignore(self) -> None:
        vector = _load_vector("weft_unknown_kind.json")
        assert vector["expected_reader_disposition"] == "ignore"
        raw = vector["input"]

        # STRICT parse raises the typed forward-compat signal.
        with pytest.raises(UnknownWeftKindError):
            WeftEvent.from_dict(raw)

        # The forgiving reader SKIPS it (never crashes), returning zero events.
        assert read_weft_events([raw]) == []

    def test_reader_skips_unknown_between_known_preserving_continuity(self) -> None:
        """An older reader keeps reading a chain that contains newer kinds."""
        known_before = _load_vector("weft_mint.json")["input"]
        unknown = _load_vector("weft_unknown_kind.json")["input"]
        known_after = _load_vector("weft_obsolete.json")["input"]

        parsed = read_weft_events([known_before, unknown, known_after])

        # cross-schema_version continuity: the two known events survive, the
        # unknown one is dropped WITHOUT breaking the read of what follows.
        assert [e.kind for e in parsed] == [WeftKind.MINT, WeftKind.OBSOLETE]

    def test_reader_still_raises_on_genuinely_malformed_event(self) -> None:
        """A missing required field is corruption, not a forward-compatible kind."""
        malformed = {"kind": "Mint", "ts": "t"}  # missing schema_version/session/...
        with pytest.raises(WeftError):
            read_weft_events([malformed])


# ---------------------------------------------------------------------------
# Invariant 2: distributor fails CLOSED on a missing required gate
# ---------------------------------------------------------------------------


class TestWeftDistributorFailClosed:
    """Distribute without a recorded HumanGate is DENIED (fail-closed)."""

    def test_distribute_without_gate_raises_missing_gate_error(self) -> None:
        dist = WeftDistributor(session="s", identity_ref="Eng-CTO")
        dist.mint("kb-1", ts="2026-01-15T10:00:00+00:00")
        with pytest.raises(MissingGateError) as exc:
            dist.distribute("kb-1", ts="2026-01-15T10:01:00+00:00")
        assert exc.value.details["subject_ref"] == "kb-1"

    def test_gate_for_one_subject_does_not_authorize_another(self) -> None:
        dist = WeftDistributor(session="s", identity_ref="Eng-CTO")
        dist.human_gate("kb-1", ts="2026-01-15T10:00:00+00:00")
        # gate is subject-scoped: kb-2 has no gate -> denied
        with pytest.raises(MissingGateError):
            dist.distribute("kb-2", ts="2026-01-15T10:01:00+00:00")

    def test_gated_distribute_succeeds_and_chains(self) -> None:
        dist = WeftDistributor(session="s", identity_ref="Eng-CTO")
        mint = dist.mint("kb-1", ts="2026-01-15T10:00:00+00:00")
        gate = dist.human_gate("kb-1", ts="2026-01-15T10:01:00+00:00")
        dist_ev = dist.distribute("kb-1", ts="2026-01-15T10:02:00+00:00")

        assert dist_ev.kind == WeftKind.DISTRIBUTE
        # the chain threads: each prev_link is the predecessor's content_hash
        assert mint.prev_link is None
        assert gate.prev_link == mint.content_hash()
        assert dist_ev.prev_link == gate.content_hash()
        assert dist.head == dist_ev.content_hash()
        assert [e.kind for e in dist.log] == [
            WeftKind.MINT,
            WeftKind.HUMAN_GATE,
            WeftKind.DISTRIBUTE,
        ]

    def test_every_emitted_event_is_schema_v3(self) -> None:
        dist = WeftDistributor(session="s", identity_ref="Eng-CTO")
        dist.mint("kb-1", ts="2026-01-15T10:00:00+00:00")
        dist.decline("kb-2", reason="no clearance", ts="2026-01-15T10:01:00+00:00")
        dist.obsolete("kb-3", ts="2026-01-15T10:02:00+00:00")
        assert all(e.schema_version == SCHEMA_VERSION_V3 for e in dist.log)


# ---------------------------------------------------------------------------
# Fail-closed serialization: non-finite floats rejected at the citable pre-image
# (trust-plane-security.md MUST-8 — jcs_encode rejects NaN/Inf)
# ---------------------------------------------------------------------------


class TestWeftNonFiniteFailClosed:
    """A NaN/Inf payload value fails CLOSED before entering the content hash."""

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_payload_rejected_at_content_hash(self, bad: float) -> None:
        event = WeftEvent(
            schema_version=SCHEMA_VERSION_V3,
            kind=WeftKind.MINT,
            ts="2026-01-15T10:00:00+00:00",
            session="s",
            identity_ref="Eng-CTO",
            payload={"subject_ref": "kb-1", "ratio": bad},
            prev_link=None,
        )
        with pytest.raises(ValueError):
            event.content_hash()


# ---------------------------------------------------------------------------
# JCS big-integer subject — the cross-SDK int-path contract (#1590 review)
# ---------------------------------------------------------------------------


class TestJcsBigIntegerSubject:
    """Pin the py-side JCS int-path bytes for a subject with an int >= 10**21."""

    def test_bigint_subject_vector(self) -> None:
        vector = _load_vector("jcs_bigint_subject.json")
        subject = vector["input"]["subject"]

        # the deliberate documented choice: an int >= 10**21 serializes as its
        # exact decimal token, NOT the ECMAScript double form (1e+21).
        assert jcs_encode(subject) == vector["expected_subject_jcs"]
        assert "1000000000000000000000" in vector["expected_subject_jcs"]
        assert "1e+21" not in vector["expected_subject_jcs"]
        assert jcs_subject_hash(subject) == vector["expected_subject_hash"]


# ---------------------------------------------------------------------------
# Vector-file integrity
# ---------------------------------------------------------------------------


class TestWeftVectorIntegrity:
    """Every WEFT-family vector exists and has the required structure."""

    @pytest.mark.parametrize("vector_file", ALL_WEFT_VECTORS)
    def test_vector_file_exists_and_valid_json(self, vector_file: str) -> None:
        vector = _load_vector(vector_file)
        assert "description" in vector, f"{vector_file} missing 'description'"
        assert "pact_type" in vector, f"{vector_file} missing 'pact_type'"

    def test_all_weft_vectors_present(self) -> None:
        actual = sorted(p.name for p in VECTORS_DIR.glob("weft_*.json")) + sorted(
            p.name for p in VECTORS_DIR.glob("jcs_*.json")
        )
        assert sorted(actual) == sorted(ALL_WEFT_VECTORS), (
            f"WEFT vector files mismatch.\n"
            f"Expected: {sorted(ALL_WEFT_VECTORS)}\n"
            f"Actual:   {sorted(actual)}"
        )
