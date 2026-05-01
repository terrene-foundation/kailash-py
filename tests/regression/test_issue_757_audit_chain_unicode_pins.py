# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #757 — audit-chain canonical-input Unicode byte pins.

The PACT audit-chain canonical-input contract (per ``kailash-rs#449`` §2 and
``schemas/audit-anchor.v1.json``) builds the SHA-256 input as a colon-delimited
string ending in JSON-serialized metadata. The metadata uses
``sort_keys=True, separators=(",", ":"), ensure_ascii=True``  so that Python's
``json.dumps`` output matches Rust's ``serde_json::to_string(&BTreeMap)``
byte-for-byte.

These tests pin two cross-SDK byte vectors (U1 BMP non-ASCII metadata, U2
above-BMP/emoji metadata) and assert both:

1. The exact canonical-input string ``AuditAnchor.compute_hash`` would feed to
   SHA-256 (reconstructed via the documented format).
2. The SHA-256 hex digest matches the pinned cross-SDK contract.

Two algorithmic-drift failure modes this guards against:

A. ``ensure_ascii=False`` regression — non-ASCII metadata keys/values would
   emit raw UTF-8 instead of ``\\uXXXX`` escapes, breaking PACT N4 audit-chain
   correlation between Python and Rust SDKs.

B. Above-BMP surrogate-pair drift — emoji and other above-BMP codepoints
   in metadata values would emit as 4-byte UTF-8 rather than UTF-16 surrogate
   pairs, silently breaking cross-SDK SHA-256 parity.

Vectors live in ``test-vectors/audit-chain-canonical.json`` (cross-SDK
contract — kailash-rs reads the same file). This module asserts named U1/U2
cases per the issue's acceptance criteria and includes an auto-iterating
fixture-parity test.

Cross-SDK alignment per ``rules/cross-sdk-inspection.md`` MUST Rule 4 (byte
vectors pinned). Sibling of #756 (TraceEvent fingerprint Unicode pins) and
#731 (TraceEvent timestamp microsecond padding).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.trust.pact.audit import GENESIS_HASH, AuditAnchor
from kailash.trust.pact.config import VerificationLevel

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "test-vectors" / "audit-chain-canonical.json"
)


def _build_canonical_input(anchor: AuditAnchor) -> str:
    """Reproduce the canonical-input string that ``AuditAnchor.compute_hash``
    feeds to SHA-256. Mirrors ``src/kailash/trust/pact/audit.py::compute_hash``
    so the test asserts the inputs to the hash, not just the digest."""
    content = (
        f"{anchor.anchor_id}:{anchor.sequence}:"
        f"{anchor.previous_hash or GENESIS_HASH}:"
        f"{anchor.agent_id}:{anchor.action}:{anchor.verification_level.value}:"
        f"{anchor.envelope_id or ''}:{anchor.result}:"
        f"{anchor.timestamp.isoformat()}"
    )
    if anchor.metadata:
        content += ":" + json.dumps(
            anchor.metadata,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
    return content


@pytest.mark.regression
class TestU1BMPMetadata:
    """U1 pinned vector — BMP non-ASCII codepoints in metadata KEY and VALUE.

    Codepoints exercised:
      - Latin-1 supplement U+00E9 (é) in value
      - CJK U+4E2D (中) + U+6587 (文) in key

    Sort order: ``role`` (starts U+0072) sorts before ``中文`` (starts U+4E2D)
    by codepoint comparison — this is the order ``sort_keys=True`` produces
    and what kailash-rs's ``BTreeMap`` produces.

    All MUST emit as ``\\uXXXX`` escapes per RFC 8259 §7.
    """

    EXPECTED_CANONICAL_INPUT = (
        "anc-u1-001:0:" + "0" * 64 + ":agent-u1:envelope_created:AUTO_APPROVED:"
        "env-u1:success:2026-01-15T11:00:00+00:00:"
        '{"role":"caf\\u00e9","\\u4e2d\\u6587":"value"}'
    )
    EXPECTED_SHA256 = "6946e734daa8279d4dc173918109995e0d10b647a7d3cd0b36aeb4114e8e12c3"

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
        assert (
            _build_canonical_input(self._make_anchor()) == self.EXPECTED_CANONICAL_INPUT
        )

    def test_compute_hash_matches_pinned_sha256(self) -> None:
        assert self._make_anchor().compute_hash() == self.EXPECTED_SHA256

    def test_canonical_input_emits_ascii_only_bytes(self) -> None:
        """Structural invariant: ASCII-only output proves
        ``ensure_ascii=True`` on metadata serialization is not silently
        regressed to ``False``."""
        canonical = _build_canonical_input(self._make_anchor())
        assert canonical.isascii(), (
            "canonical-input must be pure ASCII; non-ASCII byte means "
            "ensure_ascii=True regressed in metadata json.dumps — "
            "cross-SDK SHA-256 parity broken."
        )

    def test_compute_hash_equals_sha256_of_canonical_input(self) -> None:
        """The on-disk hash MUST equal SHA-256 of the documented canonical
        input string — no transformation other than the pinned step."""
        anchor = self._make_anchor()
        expected = hashlib.sha256(
            _build_canonical_input(anchor).encode("utf-8")
        ).hexdigest()
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
        "env-u2:success:2026-01-15T12:00:00+00:00:"
        '{"celebration":"\\ud83c\\udf89\\ud83d\\ude80"}'
    )
    EXPECTED_SHA256 = "4bba3681171049d96f6ba5863ae33dafdfa6bc0d82e26dca5267f21021872427"

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
        assert (
            _build_canonical_input(self._make_anchor()) == self.EXPECTED_CANONICAL_INPUT
        )

    def test_compute_hash_matches_pinned_sha256(self) -> None:
        assert self._make_anchor().compute_hash() == self.EXPECTED_SHA256

    def test_above_bmp_emits_surrogate_pairs(self) -> None:
        """Structural invariant: each above-BMP codepoint MUST emit as
        ``\\uXXXX\\uXXXX``. A regression that emits a single ``\\uXXXXX`` or
        raw 4-byte UTF-8 would diverge from kailash-rs's surrogate-pair
        output and break cross-SDK SHA-256 parity."""
        canonical = _build_canonical_input(self._make_anchor())
        # U+1F389 🎉 → high surrogate D83C + low surrogate DF89
        assert "\\ud83c\\udf89" in canonical
        # U+1F680 🚀 → high surrogate D83D + low surrogate DE80
        assert "\\ud83d\\ude80" in canonical
        # And no raw above-BMP characters survive in the canonical output.
        assert "🎉" not in canonical
        assert "🚀" not in canonical


@pytest.mark.regression
class TestCrossSDKFixtureParity:
    """Cross-SDK canonical-fixture conformance tests for the audit chain.

    The fixture at ``test-vectors/audit-chain-canonical.json`` pins vectors
    that BOTH kailash-py and kailash-rs MUST produce byte-for-byte. These
    tests exercise the kailash-py side; the kailash-rs side has the symmetric
    tests at ``crates/kailash-audit-vectors/`` (per #757 issue body).
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
        return AuditAnchor(
            anchor_id=input_repr["anchor_id"],
            sequence=input_repr["sequence"],
            previous_hash=input_repr.get("previous_hash"),
            agent_id=input_repr["agent_id"],
            action=input_repr["action"],
            verification_level=VerificationLevel(input_repr["verification_level"]),
            envelope_id=input_repr.get("envelope_id"),
            result=input_repr["result"],
            metadata=input_repr.get("metadata") or {},
            timestamp=datetime.fromisoformat(input_repr["timestamp"]),
        )

    def test_fixture_loads(self, fixture: dict) -> None:
        assert fixture["spec_version"] == "1.0"
        # U1 + U2 (#757). Floor stays >= so future cross-SDK additions land cleanly.
        assert len(fixture["vectors"]) >= 2

    def test_fixture_pins_canonical_genesis_hash(self, fixture: dict) -> None:
        """The cross-SDK genesis-hash sentinel is part of the contract. Drift
        here would re-open the legacy ``"genesis"`` literal silently."""
        assert fixture["genesis_hash"] == GENESIS_HASH

    def test_every_vector_canonical_input_byte_equal(self, fixture: dict) -> None:
        for v in fixture["vectors"]:
            anchor = self._construct_anchor(v["input_repr"])
            actual = _build_canonical_input(anchor)
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
