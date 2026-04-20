# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Audit-chain genesis sentinel canonical form (B2 / kailash-rs#449).

Verifies the PACT audit chain uses the canonical ``GENESIS_HASH = "0"*64``
sentinel and that multi-anchor chains round-trip through the ``AuditChain``
facade (per ``rules/orphan-detection.md`` §2a — crypto pair round-trip
through facade).

Breaking change history (2026-04-20): genesis sentinel moved from the
legacy ``"genesis"`` literal to ``"0" * 64`` per cross-SDK fingerprint
reconciliation with kailash-rs (issue #449). Chains rooted at the legacy
sentinel no longer verify.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from kailash.trust.pact.audit import GENESIS_HASH, AuditAnchor, AuditChain
from kailash.trust.pact.config import VerificationLevel


class TestGenesisHashCanonical:
    """The module-level GENESIS_HASH constant is the EATP D6 contract."""

    def test_genesis_hash_is_64_hex_zeros(self) -> None:
        """Cross-SDK contract: 64 hex zeros, same byte shape as a SHA-256 digest."""
        assert GENESIS_HASH == "0" * 64
        assert len(GENESIS_HASH) == 64
        assert all(c == "0" for c in GENESIS_HASH)

    def test_genesis_hash_is_valid_hex(self) -> None:
        """Must parse as hex so cross-SDK binary serialisation is unambiguous."""
        assert int(GENESIS_HASH, 16) == 0


class TestFirstAnchorUsesCanonicalGenesis:
    """The FIRST anchor in any chain hashes its previous_hash slot as GENESIS_HASH."""

    def _first_anchor(self) -> AuditAnchor:
        """Build the N4 conformance vector — sequence=0, previous_hash=None."""
        return AuditAnchor(
            anchor_id="anc-canonical-001",
            sequence=0,
            previous_hash=None,
            agent_id="agent-canonical",
            action="envelope_created",
            verification_level=VerificationLevel.AUTO_APPROVED,
            envelope_id="env-001",
            result="success",
            metadata={"pact_action": "envelope_created", "role_address": "D1-R1"},
            timestamp=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

    def test_first_anchor_hash_uses_canonical_sentinel(self) -> None:
        """compute_hash() substitutes GENESIS_HASH when previous_hash is None."""
        anchor = self._first_anchor()
        actual_hash = anchor.compute_hash()

        # Reproduce the canonical content string with GENESIS_HASH inline.
        # Metadata uses compact separators per kailash-rs#449 §3 — this is
        # what Rust's serde_json::to_string(&BTreeMap) emits byte-for-byte.
        content = (
            f"{anchor.anchor_id}:{anchor.sequence}:{GENESIS_HASH}:"
            f"{anchor.agent_id}:{anchor.action}:{anchor.verification_level.value}:"
            f"{anchor.envelope_id}:{anchor.result}:{anchor.timestamp.isoformat()}"
        )
        import json

        content += ":" + json.dumps(
            anchor.metadata,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        )
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        assert actual_hash == expected_hash

    def test_first_anchor_hash_is_not_the_legacy_sentinel(self) -> None:
        """Legacy "genesis" literal is no longer used — chains rooted at it fail."""
        anchor = self._first_anchor()
        actual_hash = anchor.compute_hash()

        # What the hash WOULD be under the legacy "genesis" literal
        # (legacy form used the default json.dumps with spaced separators).
        content = (
            f"{anchor.anchor_id}:{anchor.sequence}:genesis:"
            f"{anchor.agent_id}:{anchor.action}:{anchor.verification_level.value}:"
            f"{anchor.envelope_id}:{anchor.result}:{anchor.timestamp.isoformat()}"
        )
        import json

        content += ":" + json.dumps(anchor.metadata, sort_keys=True, default=str)
        legacy_hash = hashlib.sha256(content.encode()).hexdigest()

        assert actual_hash != legacy_hash, (
            "First anchor hash must NOT match the legacy 'genesis' sentinel. "
            "If this assertion is passing the legacy value, the breaking change "
            "in pact/audit.py regressed."
        )


class TestMultiAnchorChainRoundTrip:
    """End-to-end: build a chain via the AuditChain facade, verify integrity.

    This is the ``rules/orphan-detection.md`` §2a crypto-pair round-trip test:
    the Python side MUST exercise ``AuditChain.append`` + ``verify_chain_integrity``
    end-to-end, not each half in isolation. A divergence between how a new anchor
    stores its previous_hash and how the verifier reads it (e.g., one using the
    new sentinel, the other the old) would be invisible to isolated unit tests.
    """

    def test_three_anchor_chain_verifies(self) -> None:
        chain = AuditChain("chain-rt-001")
        chain.append("agent-0", "envelope_created", VerificationLevel.AUTO_APPROVED)
        chain.append("agent-0", "clearance_granted", VerificationLevel.FLAGGED)
        chain.append("agent-0", "clearance_revoked", VerificationLevel.HELD)

        is_valid, errors = chain.verify_chain_integrity()
        assert is_valid, f"Chain failed verification: {errors}"
        assert errors == []
        assert chain.length == 3

    def test_first_anchor_previous_hash_is_none_not_genesis_string(self) -> None:
        """The STORED previous_hash is None for anchor 0 — GENESIS_HASH only
        appears inside compute_hash()'s content string, never on the record."""
        chain = AuditChain("chain-rt-002")
        chain.append("agent-0", "envelope_created", VerificationLevel.AUTO_APPROVED)

        assert chain.anchors[0].previous_hash is None
        assert chain.anchors[0].previous_hash != "genesis"
        assert chain.anchors[0].previous_hash != GENESIS_HASH

    def test_subsequent_anchor_previous_hash_links_to_predecessor(self) -> None:
        chain = AuditChain("chain-rt-003")
        a0 = chain.append(
            "agent-0", "envelope_created", VerificationLevel.AUTO_APPROVED
        )
        a1 = chain.append("agent-0", "clearance_granted", VerificationLevel.FLAGGED)

        assert a1.previous_hash == a0.content_hash
        assert a1.previous_hash != GENESIS_HASH

    def test_tampered_anchor_fails_verification(self) -> None:
        """Integrity verification catches an anchor whose stored content_hash
        doesn't match its computed hash — a baseline crypto-pair assertion."""
        chain = AuditChain("chain-rt-004")
        chain.append("agent-0", "envelope_created", VerificationLevel.AUTO_APPROVED)
        chain.append("agent-0", "clearance_granted", VerificationLevel.FLAGGED)

        # Tamper by rewriting the content after sealing.
        chain.anchors[1].action = "clearance_revoked"

        is_valid, errors = chain.verify_chain_integrity()
        assert not is_valid
        assert any("content hash mismatch" in e for e in errors)

    def test_legacy_sentinel_rooted_chain_fails_verification(self) -> None:
        """A chain whose anchor 0 was hashed against the legacy "genesis" literal
        no longer verifies — proves the breaking change is actually breaking."""
        # Construct an anchor the way the legacy code path would have.
        anchor = AuditAnchor(
            anchor_id="legacy-0",
            sequence=0,
            previous_hash=None,
            agent_id="legacy-agent",
            action="envelope_created",
            verification_level=VerificationLevel.AUTO_APPROVED,
            envelope_id="env-legacy",
            result="success",
            metadata={"pact_action": "envelope_created"},
            timestamp=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        )

        # Forge the content_hash using the LEGACY sentinel string.
        import hashlib
        import json

        legacy_content = (
            f"{anchor.anchor_id}:{anchor.sequence}:genesis:"
            f"{anchor.agent_id}:{anchor.action}:{anchor.verification_level.value}:"
            f"{anchor.envelope_id}:{anchor.result}:{anchor.timestamp.isoformat()}"
        )
        legacy_content += ":" + json.dumps(anchor.metadata, sort_keys=True, default=str)
        anchor.content_hash = hashlib.sha256(legacy_content.encode()).hexdigest()

        # verify_integrity recomputes against the NEW sentinel and mismatches.
        assert anchor.is_sealed
        assert not anchor.verify_integrity(), (
            "A legacy-rooted anchor must fail verification under the new sentinel. "
            "If this passes, the breaking-change semantics regressed."
        )
