# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #757 — audit-chain canonical-input Unicode byte pins.

The PACT audit-chain canonical-input contract (per ``kailash-rs#449`` §2 and
``schemas/audit-anchor.v1.json``) builds the SHA-256 input as a colon-delimited
string ending in JSON-serialized metadata. The metadata uses
``sort_keys=True, separators=(",", ":"), ensure_ascii=True`` so that Python's
canonical output matches Rust's ``serde_json::to_string(&BTreeMap)``
byte-for-byte. The timestamp is ALWAYS rendered
``isoformat(timespec="microseconds")`` (six fractional digits + ``+00:00``).

These tests pin the Python canonical-input bytes for the audit chain and
assert both:

1. The exact canonical-input string ``AuditAnchor.compute_hash`` feeds to
   SHA-256 — asserted against the PRODUCTION builder ``_canonical_input()``,
   NOT a test-side mirror (issue #1404). A production format drift fails these
   tests instead of being silently mirrored.
2. The SHA-256 hex digest matches the pinned value.

Scope (issue #1402): these assertions prove **Python self-consistency** — the
production path reproduces the pinned fixture bytes. They do NOT ingest an
independently-produced kailash-rs digest; the cross-SDK byte equality is
verified at the post-Wave-6 cross-SDK gate, NOT in this repo's CI (see the
fixture's ``provenance.cross_impl_note``).

Drift failure modes guarded:

A. ``ensure_ascii=False`` regression — non-ASCII metadata keys/values would
   emit raw UTF-8 instead of ``\\uXXXX`` escapes, breaking PACT N4 audit-chain
   correlation between Python and Rust SDKs.
B. Above-BMP surrogate-pair drift — emoji and other above-BMP codepoints in
   metadata values would emit as 4-byte UTF-8 rather than UTF-16 surrogate pairs.
C. Microsecond elision (issue #1400) — a whole-second timestamp without the
   fixed-width ``.000000`` fraction would hash-diverge from a peer that always
   emits six digits.
D. ``default=str`` typed-scalar drift (issue #1405) — a ``Decimal`` / ``UUID`` /
   ``datetime`` / ``set`` in metadata routed through implementation-defined
   ``str()`` instead of the canonical ``canonical_scalars`` whitelist.

Vectors live in ``test-vectors/audit-chain-canonical.json`` (a
python-self-consistent golden — kailash-rs is expected to reproduce the same
bytes, but the independent rust digest is verified at the post-Wave-6 cross-SDK
gate, not here; regenerate via
``test-vectors/regenerate_canonical_vectors.py``). Cross-SDK alignment per
``rules/cross-sdk-inspection.md`` MUST Rule 4. Siblings: #756 (TraceEvent
fingerprint Unicode pins), #731 (TraceEvent timestamp microsecond padding).
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from kailash.trust.pact.audit import GENESIS_HASH, AuditAnchor
from kailash.trust.pact.config import VerificationLevel

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "test-vectors" / "audit-chain-canonical.json"
)

# Required named vectors — removing any from the fixture fails loudly naming
# the missing vector (issue #1407); a count floor alone cannot detect a
# silently-deleted pinned vector.
_REQUIRED_VECTOR_NAMES = frozenset(
    {
        "U1_bmp_metadata_key_and_value",
        "U2_above_bmp_emoji_metadata_value",
        "U3_nonzero_microsecond",
        "U4_whole_second_explicit_000000",
        "U5_typed_scalar_metadata",
        "U6_whole_second_metadata_datetime",
    }
)


def _decode_typed(obj: object) -> object:
    """Reconstruct ``__pytype__``-tagged typed scalars from the fixture JSON.

    Inverse of ``test-vectors/regenerate_canonical_vectors.py::encode_typed``.
    Kept minimal + self-contained; the round-trip is validated by the byte pins
    below, which fail loudly if this drifts from the generator.
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
class TestU1BMPMetadata:
    """U1 pinned vector — BMP non-ASCII codepoints in metadata KEY and VALUE.

    Codepoints exercised:
      - Latin-1 supplement U+00E9 (é) in value
      - CJK U+4E2D (中) + U+6587 (文) in key

    Sort order: ``role`` (starts U+0072) sorts before ``中文`` (starts U+4E2D)
    by codepoint comparison — what ``sort_keys=True`` and kailash-rs's
    ``BTreeMap`` both produce. All MUST emit as ``\\uXXXX`` escapes per RFC 8259.
    """

    EXPECTED_CANONICAL_INPUT = (
        "anc-u1-001:0:" + "0" * 64 + ":agent-u1:envelope_created:AUTO_APPROVED:"
        "env-u1:success:2026-01-15T11:00:00.000000+00:00:"
        '{"role":"caf\\u00e9","\\u4e2d\\u6587":"value"}'
    )
    EXPECTED_SHA256 = "f1c755c8c5ae77c7cd4d99c8e3e19a10de925f1336f7dd1826573bc675e9ff71"

    def _make_anchor(self) -> AuditAnchor:
        return AuditAnchor(
            anchor_id="anc-u1-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u1",
            action="envelope_created",
            verification_level=VerificationLevel.AUTO_APPROVED,
            envelope_id="env-u1",
            result="success",
            metadata={"role": "café", "中文": "value"},
            timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
        )

    def test_canonical_input_byte_equal(self) -> None:
        assert self._make_anchor()._canonical_input() == self.EXPECTED_CANONICAL_INPUT

    def test_compute_hash_matches_pinned_sha256(self) -> None:
        assert self._make_anchor().compute_hash() == self.EXPECTED_SHA256

    def test_canonical_input_emits_ascii_only_bytes(self) -> None:
        """Structural invariant: ASCII-only output proves ``ensure_ascii=True``
        on metadata serialization is not silently regressed to ``False``."""
        canonical = self._make_anchor()._canonical_input()
        assert canonical.isascii(), (
            "canonical-input must be pure ASCII; non-ASCII byte means "
            "ensure_ascii=True regressed in metadata json.dumps — "
            "cross-SDK SHA-256 parity broken."
        )

    def test_compute_hash_equals_sha256_of_canonical_input(self) -> None:
        """The on-disk hash MUST equal SHA-256 of the production canonical input
        — proving compute_hash hashes exactly what _canonical_input builds
        (issue #1404, no transformation other than the pinned step)."""
        anchor = self._make_anchor()
        expected = hashlib.sha256(anchor._canonical_input().encode("utf-8")).hexdigest()
        assert anchor.compute_hash() == expected


@pytest.mark.regression
class TestU2AboveBMPEmojiMetadata:
    """U2 pinned vector — above-BMP emoji codepoints in metadata VALUE.

    Codepoints exercised (each requires a UTF-16 surrogate pair):
      - U+1F389 🎉 → ``\\ud83c\\udf89``
      - U+1F680 🚀 → ``\\ud83d\\ude80``

    Both MUST emit as surrogate-pair ``\\uXXXX\\uXXXX`` sequences per
    RFC 8259 §7.
    """

    EXPECTED_CANONICAL_INPUT = (
        "anc-u2-001:0:" + "0" * 64 + ":agent-u2:envelope_created:AUTO_APPROVED:"
        "env-u2:success:2026-01-15T12:00:00.000000+00:00:"
        '{"celebration":"\\ud83c\\udf89\\ud83d\\ude80"}'
    )
    EXPECTED_SHA256 = "efd824a248fbc469e1850efde6b9e0639fe30cea3d3b70cfb386f7eb107b35d9"

    def _make_anchor(self) -> AuditAnchor:
        return AuditAnchor(
            anchor_id="anc-u2-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u2",
            action="envelope_created",
            verification_level=VerificationLevel.AUTO_APPROVED,
            envelope_id="env-u2",
            result="success",
            metadata={"celebration": "🎉🚀"},
            timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

    def test_canonical_input_byte_equal(self) -> None:
        assert self._make_anchor()._canonical_input() == self.EXPECTED_CANONICAL_INPUT

    def test_compute_hash_matches_pinned_sha256(self) -> None:
        assert self._make_anchor().compute_hash() == self.EXPECTED_SHA256

    def test_above_bmp_emits_surrogate_pairs(self) -> None:
        """Structural invariant: each above-BMP codepoint MUST emit as
        ``\\uXXXX\\uXXXX``. A regression that emits a single ``\\uXXXXX`` or
        raw 4-byte UTF-8 would diverge from kailash-rs's surrogate-pair output
        and break cross-SDK SHA-256 parity."""
        canonical = self._make_anchor()._canonical_input()
        assert "\\ud83c\\udf89" in canonical
        assert "\\ud83d\\ude80" in canonical
        assert "🎉" not in canonical
        assert "🚀" not in canonical


@pytest.mark.regression
class TestU5TypedScalarMetadata:
    """U5 pinned vector — typed-scalar metadata routed through the canonical
    whitelist instead of ``default=str`` (issue #1405 / #1403).

    A ``Decimal`` / ``UUID`` / ``datetime`` / ``set`` in metadata MUST encode
    deterministically (``Decimal`` full precision, ``UUID`` 8-4-4-4-12,
    ``datetime`` isoformat, ``set`` → sorted list) — never via Python's
    implementation-defined ``str()`` which a peer SDK has no reason to reproduce.
    """

    EXPECTED_METADATA_SEGMENT = (
        '{"amount":"1.50","id":"12345678-1234-5678-1234-567812345678",'
        '"tags":["alpha","beta","gamma"],'
        '"when":"2026-03-04T05:06:07.000123+00:00"}'
    )

    def _make_anchor(self) -> AuditAnchor:
        return AuditAnchor(
            anchor_id="anc-u5-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-u5",
            action="budget_check",
            verification_level=VerificationLevel.AUTO_APPROVED,
            envelope_id="env-u5",
            result="success",
            metadata={
                "amount": Decimal("1.50"),
                "id": UUID("12345678-1234-5678-1234-567812345678"),
                "when": datetime.fromisoformat("2026-03-04T05:06:07.000123+00:00"),
                "tags": {"beta", "alpha", "gamma"},
            },
            timestamp=datetime(2026, 1, 15, 15, 0, 0, 500000, tzinfo=timezone.utc),
        )

    def test_typed_scalars_use_canonical_whitelist(self) -> None:
        canonical = self._make_anchor()._canonical_input()
        meta_segment = canonical.split("2026-01-15T15:00:00.500000+00:00:", 1)[1]
        assert meta_segment == self.EXPECTED_METADATA_SEGMENT, meta_segment

    def test_non_whitelisted_metadata_raises_not_str_coerced(self) -> None:
        """A non-JSON-native, non-whitelisted value MUST raise (no silent
        ``str()`` coercion) — the structural proof that ``default=str`` is gone."""
        anchor = AuditAnchor(
            anchor_id="anc-u5-bad",
            sequence=0,
            agent_id="agent-u5",
            action="budget_check",
            verification_level=VerificationLevel.AUTO_APPROVED,
            result="success",
            metadata={"obj": object()},
            timestamp=datetime(2026, 1, 15, 15, 0, 0, tzinfo=timezone.utc),
        )
        with pytest.raises(TypeError):
            anchor.compute_hash()


@pytest.mark.regression
class TestCrossSDKFixtureParity:
    """Canonical-fixture conformance tests for the audit chain (Python side).

    The fixture at ``test-vectors/audit-chain-canonical.json`` is
    python-self-consistent: its ``expected_*`` bytes are reproduced by the
    PRODUCTION ``_canonical_input()``, which is what these tests assert.
    kailash-rs is expected to reproduce the same bytes, but its independent
    digest is verified at the post-Wave-6 cross-SDK gate, NOT in this repo's CI
    (see the fixture's ``provenance.cross_impl_note``).
    """

    @pytest.fixture(scope="class")
    def fixture(self) -> dict:
        assert _FIXTURE_PATH.exists(), (
            f"cross-SDK audit-chain fixture missing at {_FIXTURE_PATH}; "
            f"this fixture is the cross-SDK byte contract — its absence "
            f"means the U1/U2 contract from #757 is not enforced."
        )
        return json.loads(_FIXTURE_PATH.read_text())

    def _construct_anchor(self, input_repr: dict) -> AuditAnchor:
        metadata = _decode_typed(input_repr.get("metadata") or {})
        assert isinstance(metadata, dict)  # decoded fixture metadata is a dict
        return AuditAnchor(
            anchor_id=input_repr["anchor_id"],
            sequence=input_repr["sequence"],
            previous_hash=input_repr.get("previous_hash"),
            agent_id=input_repr["agent_id"],
            action=input_repr["action"],
            verification_level=VerificationLevel(input_repr["verification_level"]),
            envelope_id=input_repr.get("envelope_id"),
            result=input_repr["result"],
            metadata=metadata,
            timestamp=datetime.fromisoformat(input_repr["timestamp"]),
        )

    def test_fixture_loads(self, fixture: dict) -> None:
        assert fixture["spec_version"] == "1.1"

    def test_required_vectors_present(self, fixture: dict) -> None:
        """Issue #1407: assert each REQUIRED named vector is present. A count
        floor cannot detect a silently-deleted pinned vector; this names it."""
        present = {v["name"] for v in fixture["vectors"]}
        missing = _REQUIRED_VECTOR_NAMES - present
        assert not missing, f"audit-chain fixture missing required vectors: {missing}"

    def test_fixture_pins_canonical_genesis_hash(self, fixture: dict) -> None:
        """The cross-SDK genesis-hash sentinel is part of the contract. Drift
        here would re-open the legacy ``"genesis"`` literal silently."""
        assert fixture["genesis_hash"] == GENESIS_HASH

    def test_every_vector_canonical_input_byte_equal(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            anchor = self._construct_anchor(v["input_repr"])
            actual = anchor._canonical_input()
            assert actual == v["expected_canonical_input"], (
                f"vector {v['name']}: canonical-input byte-divergence — "
                f"got {actual!r}, expected {v['expected_canonical_input']!r}"
            )

    def test_every_vector_sha256_matches(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            anchor = self._construct_anchor(v["input_repr"])
            assert anchor.compute_hash() == v["expected_sha256"], (
                f"vector {v['name']}: SHA-256 divergence — "
                f"got {anchor.compute_hash()}, expected {v['expected_sha256']}"
            )
