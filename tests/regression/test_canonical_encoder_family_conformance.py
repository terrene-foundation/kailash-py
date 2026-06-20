# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the canonical-encoder family cross-SDK conformance sweep
(2026-06-20 follow-up to the audit-chain #1400-1407 cluster).

After the audit-chain canonical-hash fix, an empirical byte-diff sweep of every
``json.dumps(..., default=str)`` site in the trust plane classified the remaining
signing/hash/cross-SDK-byte sites into two dispositions (see
``specs/trust-canonical-encoders.md`` § "Encoder-family map"):

1. **Byte-neutral conformance (SHIPPED py-side).**
   ``ConstraintEnvelope.envelope_hash`` (``envelope.py``) routes through the shared
   ``canonical_scalars`` whitelist. The constraint ``to_dict()`` layer already
   pre-normalises every divergent type (datetime->isoformat, tuple->list,
   enum->.value) and ``_hashable_dict`` excludes the free-form ``metadata`` dict,
   so the switch changes ZERO currently-emitted bytes — the #1403/#1405 pattern.
   These tests pin that byte-neutrality.

2. **Cross-SDK-blocked (NOT changed py-only — gated on a kailash-rs lockstep).**
   The selective-disclosure witness family (``_hash_value`` /
   ``_compute_chain_hash`` / the export+verify sign-payloads) and
   ``ConstraintEnvelope.to_canonical_json`` (the HMAC sign/verify pre-image) are
   byte-CHANGING under ``canonical_scalars``: a nested ``chain.AuditAnchor``
   dataclass reaches the witness encoders by default, and ``to_canonical_json``
   includes the unvalidated free-form ``metadata`` dict. Both explicitly claim
   byte-for-byte parity with kailash-rs (``kailash-rs#449``). Switching py-only
   would diverge the two SDKs — the same disposition as the audit-chain #1400
   timestamp change (BLOCKED on ``kailash-rs#1448``).

   The tests below pin the CURRENT (``default=str``) bytes so a silent py-only
   canonical switch breaks LOUDLY (per ``cross-sdk-inspection.md`` Rule 4).
   When the cross-SDK canonical migration is authorised, these literals MUST be
   re-pinned IN LOCKSTEP in BOTH kailash-py and kailash-rs together — never
   py-only. These are kailash-py's first tests for ``selective_disclosure.py``.

Every pinned literal here was captured from the live production path, not copied
from a summary.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import kailash.trust.enforce.selective_disclosure as sd
from kailash.trust._canonical import canonical_scalars
from kailash.trust.audit_store import AuditRecord
from kailash.trust.chain import ActionResult, AuditAnchor
from kailash.trust.enforce.selective_disclosure import (
    NON_REDACTABLE_FIELDS,
    export_for_witness,
    verify_witness_export,
)
from kailash.trust.envelope import (
    AgentPosture,
    ConstraintEnvelope,
    FinancialConstraint,
    OperationalConstraint,
    TemporalConstraint,
)
from kailash.trust.signing.crypto import generate_keypair

UTC = timezone.utc


def _fixed_anchor() -> AuditAnchor:
    """A deterministic ``chain.AuditAnchor`` (the type ``AuditRecord`` wraps)."""
    return AuditAnchor(
        id="anc-001",
        agent_id="agent-42",
        action="read",
        timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
        trust_chain_hash="abc123",
        result=ActionResult.SUCCESS,
        signature="sig-1",
        resource="doc-1",
        context={"k": "v"},
    )


def _fixed_record() -> AuditRecord:
    """A deterministic ``AuditRecord`` (fixed id + stored_at -> stable hashes)."""
    return AuditRecord(
        anchor=_fixed_anchor(),
        record_id="rec-001",
        stored_at=datetime(2026, 1, 15, 11, 0, 5, tzinfo=UTC),
        previous_hash=None,
        sequence_number=1,
    )


def _fixed_envelope() -> ConstraintEnvelope:
    """A fully-populated envelope exercising datetime + tuple + enum normalisation."""
    return ConstraintEnvelope(
        financial=FinancialConstraint(budget_limit=100.0, currency="USD"),
        temporal=TemporalConstraint(
            valid_from=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            allowed_hours=(9, 17),
        ),
        operational=OperationalConstraint(
            allowed_actions=("read", "list"), blocked_actions=("delete",)
        ),
        posture_ceiling=AgentPosture.SUPERVISED,
    )


# ---------------------------------------------------------------------------
# 1. Byte-neutral conformance — envelope_hash (SHIPPED py-side)
# ---------------------------------------------------------------------------


class TestEnvelopeHashByteNeutralConformance:
    def test_envelope_hash_pinned_byte_vector(self) -> None:
        """envelope_hash() is byte-IDENTICAL after the canonical_scalars switch.

        This literal was the output of the pre-switch ``default=str`` code; the
        post-switch ``canonical_scalars`` path MUST reproduce it byte-for-byte.
        """
        assert (
            _fixed_envelope().envelope_hash()
            == "698342bb43097a057b3412a7e50fbd69fb6b63edeefaf07618d12562418221f0"
        )

    def test_envelope_hash_encoder_swap_is_byte_neutral(self) -> None:
        """canonical_scalars(payload) and default=str produce identical bytes for
        the constraint-only payload (every value is already JSON-native)."""
        import json

        payload = _fixed_envelope()._hashable_dict()
        legacy = json.dumps(payload, sort_keys=True, default=str)
        conformant = json.dumps(
            canonical_scalars(payload), sort_keys=True, allow_nan=False
        )
        assert legacy == conformant

    def test_hashable_dict_excludes_metadata(self) -> None:
        """Structural invariant: _hashable_dict() MUST exclude the free-form
        metadata dict, so no unvalidated typed scalar can reach envelope_hash and
        silently diverge under canonical_scalars (the no-non-native-ingress lock)."""
        env = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=1.0),
            metadata={"ts": datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC)},
        )
        assert "metadata" not in env._hashable_dict()


# ---------------------------------------------------------------------------
# 2. Cross-SDK-blocked — selective-disclosure witness family
#    (pins CURRENT default=str bytes; re-pin in lockstep with kailash-rs only)
# ---------------------------------------------------------------------------


class TestSelectiveDisclosureCrossSDKBlockedBytes:
    def test_anchor_is_redactable_reachability_invariant(self) -> None:
        """The nested ``anchor`` dataclass reaches the witness encoders by default
        (it is NOT a non-redactable field). This reachability is WHY the family is
        byte-changing under canonical_scalars; pin it so it cannot silently change."""
        assert "anchor" not in NON_REDACTABLE_FIELDS

    def test_hash_value_anchor_pinned_default_str_bytes(self) -> None:
        """_hash_value over the nested AuditAnchor — pinned to the CURRENT
        default=str repr-hash. canonical_scalars would asdict-expand the dataclass
        and produce a DIFFERENT sha256 -> a cross-SDK divergence. Re-pin only under
        an authorised kailash-rs#1448-style lockstep."""
        assert (
            sd._hash_value(_fixed_anchor())
            == "REDACTED:sha256:10f314ecd4a880b3d0676211a35472f2c2ef9ebb20dd01b1db83f052876a03d7"
        )

    def test_compute_chain_hash_all_redacted_pinned(self) -> None:
        """Witness chain hash on the default (all-redacted) export path."""
        data = sd._audit_record_to_dict(_fixed_record())
        redacted = sd._redact_record(data, [])
        chain = sd._compute_chain_hash([redacted.data])
        assert (
            chain[0]
            == "200f866033f6dccdf3325358042d630b0166a71a0c685b8d0a7c4263eeb133d2"
        )

    def test_compute_chain_hash_disclosed_anchor_pinned(self) -> None:
        """Disclosing 'anchor' routes the raw dataclass into the chain-hash
        json.dumps — the byte-changing reachability. Pinned to current bytes."""
        data = sd._audit_record_to_dict(_fixed_record())
        redacted = sd._redact_record(data, ["anchor"])
        chain = sd._compute_chain_hash([redacted.data])
        assert (
            chain[0]
            == "8a28f0f6196e6a81a3d4482113ce1ba381ec01703baec34d74933bfdac66bd48"
        )

    def test_witness_export_round_trip_intra_sdk_lockstep(self) -> None:
        """The export-side and verify-side sign-payload canonicalisations MUST
        stay byte-identical to each other (intra-SDK invariant) regardless of the
        cross-SDK decision: if one switched encoder and the other did not, every
        signature would fail. Functional round-trip proves they agree."""
        private_key, public_key = generate_keypair()
        export = export_for_witness(
            audit_records=[_fixed_record()],
            disclosed_fields=[],
            signing_key=private_key,
        )
        result = verify_witness_export(export, authority_public_key=public_key)
        assert result.signature_valid is True
        assert result.chain_integrity_valid is True
        assert result.valid is True


# ---------------------------------------------------------------------------
# 3. Cross-SDK-blocked — envelope to_canonical_json (HMAC sign/verify pre-image)
# ---------------------------------------------------------------------------


class TestEnvelopeCanonicalJsonCrossSDKBlockedBytes:
    def test_to_canonical_json_metadata_datetime_pinned_default_str(self) -> None:
        """to_canonical_json includes the free-form metadata dict; a datetime there
        renders SPACE-separated under default=str. canonical_scalars would render
        'T'-separated -> a divergent HMAC pre-image that also invalidates every
        on-disk signed envelope. Pinned to current bytes; re-pin only in lockstep
        with kailash-rs."""
        env = ConstraintEnvelope(
            financial=FinancialConstraint(budget_limit=100.0, currency="USD"),
            metadata={"audit_ts": datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC)},
        )
        canonical = env.to_canonical_json()
        # The cross-SDK-blocked divergence locus: space-separated (default=str),
        # NOT 'T'-separated (canonical_scalars).
        assert '"audit_ts":"2026-01-15 11:00:00+00:00"' in canonical
        assert '"audit_ts":"2026-01-15T11:00:00+00:00"' not in canonical
        # Full byte-image pin (current default=str image).
        assert canonical == (
            '{"envelope_hash":"c37f1e6e0618987446be6937792d32173c579d87577c76bac9'
            '71862730c9395f","financial":{"api_cost_budget_usd":null,"budget_limit'
            '":100.0,"budget_tracking":false,"cost_per_call":null,"currency":"USD"'
            ',"max_cost_per_action":null,"max_cost_per_session":null,"max_spend_usd'
            '":null,"reasoning_required":false,"requires_approval_above_usd":null},'
            '"metadata":{"audit_ts":"2026-01-15 11:00:00+00:00"}}'
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
