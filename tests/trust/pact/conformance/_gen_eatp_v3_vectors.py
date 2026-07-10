# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""One-shot generator for the EATP v3 additive-element (#1592) conformance vectors.

Constructs each fixture through the REAL production implementation
(``BilateralDelegation`` / ``ClearanceAttestation`` / ``verify_chain`` /
``RevocationEvent`` / ``ConfidentialityLevel``) and writes the byte-pinned vector
JSON into ``vectors/`` (``eatp3_*.json`` prefix). Re-run to regenerate after an
intentional canonical change, then re-pin ``PACT_VECTORS.sha256`` in the same
commit (``cross-sdk-inspection.md`` Rule 4c). NOT collected by pytest.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from kailash.trust import ConfidentialityLevel, TrustPosture
from kailash.trust.pact.attestation import (
    new_clearance_attestation,
    posture_can_reidentify,
)
from kailash.trust.pact.audit import SCHEMA_VERSION_V3
from kailash.trust.pact.bilateral import (
    GuaranteeTier,
    PartyAnchor,
    SignerKind,
    new_bilateral_delegation,
)
from kailash.trust.pact.verify_chain import (
    COMPOSITION_MODE,
    ChainLink,
    ChainVerdict,
    verify_chain,
)
from kailash.trust.revocation import RevocationEvent, RevocationMode, RevocationType

VECTORS = Path(__file__).parent / "vectors"

# Deterministic anchor references + timestamps for stable byte-pins.
_ANCHOR_A = "sha256:" + "a" * 64
_ANCHOR_B = "sha256:" + "b" * 64
_WITNESS = "sha256:" + "c" * 64
_ALL_POSTURES = [
    TrustPosture.PSEUDO,
    TrustPosture.TOOL,
    TrustPosture.SUPERVISED,
    TrustPosture.DELEGATING,
    TrustPosture.AUTONOMOUS,
]


def _write(filename: str, vector: dict[str, Any]) -> None:
    path = VECTORS / filename
    path.write_text(
        json.dumps(vector, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {filename}")


def _bilateral_vector(filename: str, description: str, delegation: Any) -> None:
    vector = {
        "description": description,
        "pact_type": "BilateralDelegation",
        "conformance_requirement": "EATP-v3-bilateral",
        "schema_version": SCHEMA_VERSION_V3,
        "input": delegation.to_dict(),
        "expected_canonical_json": delegation.canonical_json(),
        "expected_content_hash": delegation.content_hash(),
        "expected_atomic_valid": delegation.is_atomically_valid(),
        "expected_guarantee_tier": delegation.guarantee_tier().value,
        "expected_supports_non_repudiation": delegation.supports_non_repudiation(),
    }
    _write(filename, vector)


def main() -> None:
    # -- BilateralDelegation: valid, conformant, party-signed (atomic validity) --
    valid = new_bilateral_delegation(
        delegation_id="del-1592-001",
        root="Eng",
        delegator=PartyAnchor("Eng-CTO", _ANCHOR_A, SignerKind.PARTY),
        delegate=PartyAnchor("Eng-CTO-Backend-Lead", _ANCHOR_B, SignerKind.PARTY),
        ts="2026-01-15T10:00:00+00:00",
        payload={"scope": "deploy", "subject_ref": "kb-42"},
    )
    _bilateral_vector(
        "eatp3_bilateral_valid.json",
        "BilateralDelegation with BOTH parties' anchors present + party-signed: "
        "atomically valid, CONFORMANT guarantee tier, supports non-repudiation "
        "(#1592).",
        valid,
    )

    # -- BilateralDelegation: missing delegate anchor -> NOT atomically valid --
    missing = new_bilateral_delegation(
        delegation_id="del-1592-002",
        root="Eng",
        delegator=PartyAnchor("Eng-CTO", _ANCHOR_A, SignerKind.PARTY),
        delegate=PartyAnchor("Eng-CTO-Backend-Lead", "", SignerKind.PARTY),
        ts="2026-01-15T10:01:00+00:00",
        payload={"scope": "deploy"},
    )
    _bilateral_vector(
        "eatp3_bilateral_missing_anchor.json",
        "BilateralDelegation missing the delegate's anchor: NOT atomically valid "
        "(one party's anchor never half-authorizes), degraded to "
        "RECORDED_BY_INTERMEDIARY, no non-repudiation (#1592).",
        missing,
    )

    # -- BilateralDelegation: dispatcher-signed -> provenance only, NEVER non-rep --
    dispatcher = new_bilateral_delegation(
        delegation_id="del-1592-003",
        root="Eng",
        delegator=PartyAnchor("Eng-CTO", _ANCHOR_A, SignerKind.DISPATCHER),
        delegate=PartyAnchor("Eng-CTO-Backend-Lead", _ANCHOR_B, SignerKind.PARTY),
        ts="2026-01-15T10:02:00+00:00",
        payload={"scope": "deploy"},
    )
    _bilateral_vector(
        "eatp3_bilateral_dispatcher_provenance.json",
        "BilateralDelegation whose delegator anchor is DISPATCHER-signed: "
        "provenance-only, RECORDED_BY_INTERMEDIARY tier, MUST NOT support "
        "non-repudiation (dispatcher signature is provenance-only) (#1592).",
        dispatcher,
    )

    # -- BilateralDelegation: conformant + witness -> COMPLETE_WITNESSED --
    witnessed = new_bilateral_delegation(
        delegation_id="del-1592-004",
        root="Eng",
        delegator=PartyAnchor("Eng-CTO", _ANCHOR_A, SignerKind.PARTY),
        delegate=PartyAnchor("Eng-CTO-Backend-Lead", _ANCHOR_B, SignerKind.PARTY),
        ts="2026-01-15T10:03:00+00:00",
        witness_ref=_WITNESS,
        payload={"scope": "deploy"},
    )
    _bilateral_vector(
        "eatp3_bilateral_witnessed.json",
        "BilateralDelegation conformant PLUS an independent witness anchor: "
        "COMPLETE_WITNESSED (the strongest guarantee tier) (#1592).",
        witnessed,
    )

    # -- Guarantee-tier taxonomy distinction (the three tiers, wire values) --
    _write(
        "eatp3_guarantee_tier_distinction.json",
        {
            "description": "The three EATP v3 guarantee tiers, their wire values, "
            "and which BilateralDelegation shape yields each. Ordered weakest -> "
            "strongest (#1592).",
            "pact_type": "GuaranteeTier",
            "conformance_requirement": "EATP-v3-guarantee-tier",
            "expected_tiers_ordered": [
                GuaranteeTier.RECORDED_BY_INTERMEDIARY.value,
                GuaranteeTier.CONFORMANT.value,
                GuaranteeTier.COMPLETE_WITNESSED.value,
            ],
            "expected_shape_to_tier": {
                "dispatcher_or_missing_anchor": missing.guarantee_tier().value,
                "both_party_signed_present": valid.guarantee_tier().value,
                "conformant_plus_witness": witnessed.guarantee_tier().value,
            },
            "expected_dispatcher_is_recorded_by_intermediary": (
                dispatcher.guarantee_tier().value
            ),
        },
    )

    # -- ClearanceAttestation: posture-gated re-identification --
    att = new_clearance_attestation(
        attestation_id="att-1592-001",
        subject_ref="subject-pseudonym-0001",
        required_clearance=ConfidentialityLevel.SECRET,
        ts="2026-01-15T10:04:00+00:00",
        attested_by_role_address="Eng-CTO",
        payload={"purpose": "fraud_investigation"},
    )
    _write(
        "eatp3_clearance_posture_gate.json",
        {
            "description": "ClearanceAttestation requiring SECRET clearance to "
            "re-identify a pseudonymous subject. Posture-gated: only postures "
            "whose POSTURE_CEILING reaches SECRET (DELEGATING, AUTONOMOUS) may "
            "re-identify (#1592).",
            "pact_type": "ClearanceAttestation",
            "conformance_requirement": "EATP-v3-clearance-attestation",
            "schema_version": SCHEMA_VERSION_V3,
            "input": att.to_dict(),
            "expected_canonical_json": att.canonical_json(),
            "expected_content_hash": att.content_hash(),
            "expected_required_clearance": att.required_clearance.value,
            "expected_reidentify_by_posture": {
                posture.value: posture_can_reidentify(posture, att.required_clearance)
                for posture in _ALL_POSTURES
            },
        },
    )

    # -- ClearanceAttestation ordinal + inverted-pair wire-token pin --
    ordered = sorted(ConfidentialityLevel)  # uses the shared C0..C4 __lt__ ordinal
    _write(
        "eatp3_clearance_ordinal_inverted_pair.json",
        {
            "description": "The ConfidentialityLevel C0..C4 ordinal reused by "
            "ClearanceAttestation. Pins the inverted-pair wire tokens: "
            "'restricted' is C1 and 'confidential' is C2 (restricted < "
            "confidential), NOT the intuitive reverse (#1592).",
            "pact_type": "ConfidentialityLevelOrdinal",
            "conformance_requirement": "EATP-v3-clearance-ordinal",
            "expected_ordinal": {
                level.value: rank for rank, level in enumerate(ordered)
            },
            "expected_wire_tokens_ordered": [level.value for level in ordered],
            "expected_restricted_rank": ordered.index(ConfidentialityLevel.RESTRICTED),
            "expected_confidential_rank": ordered.index(
                ConfidentialityLevel.CONFIDENTIAL
            ),
            "expected_restricted_lt_confidential": (
                ConfidentialityLevel.RESTRICTED < ConfidentialityLevel.CONFIDENTIAL
            ),
        },
    )

    # -- VERIFY_CHAIN: deny-overrides (a deny link denies the whole chain) --
    deny_links = [
        ChainLink("link-a", ChainVerdict.ALLOW, "delegator anchor verified"),
        ChainLink("link-b", ChainVerdict.DENY, "delegate clearance insufficient"),
        ChainLink("link-c", ChainVerdict.ALLOW, "temporal window ok"),
    ]
    deny_result = verify_chain(deny_links)
    _write(
        "eatp3_verify_chain_deny_overrides.json",
        {
            "description": "VERIFY_CHAIN deny-overrides: a chain with one DENY "
            "link (between two ALLOW links) denies the WHOLE chain; the first "
            "denying link is cited and evaluation short-circuits there (#1592).",
            "pact_type": "VerifyChain",
            "conformance_requirement": "EATP-v3-verify-chain",
            "composition_mode": COMPOSITION_MODE,
            "input": {"links": [link.to_dict() for link in deny_links]},
            "expected_result": deny_result.to_dict(),
            "expected_allowed": deny_result.allowed,
            "expected_denied_by": deny_result.denied_by,
            "expected_evaluated": deny_result.evaluated,
        },
    )

    # -- VERIFY_CHAIN: all links allow -> allowed --
    allow_links = [
        ChainLink("link-a", ChainVerdict.ALLOW, "delegator anchor verified"),
        ChainLink("link-b", ChainVerdict.ALLOW, "delegate clearance ok"),
        ChainLink("link-c", ChainVerdict.ALLOW, "temporal window ok"),
    ]
    allow_result = verify_chain(allow_links)
    _write(
        "eatp3_verify_chain_all_allow.json",
        {
            "description": "VERIFY_CHAIN with every link ALLOW: the composed "
            "verdict is allowed; deny-overrides never fires (#1592).",
            "pact_type": "VerifyChain",
            "conformance_requirement": "EATP-v3-verify-chain",
            "composition_mode": COMPOSITION_MODE,
            "input": {"links": [link.to_dict() for link in allow_links]},
            "expected_result": allow_result.to_dict(),
            "expected_allowed": allow_result.allowed,
            "expected_denied_by": allow_result.denied_by,
            "expected_evaluated": allow_result.evaluated,
        },
    )

    # -- Revocation GRACEFUL mode (grace-window drain) --
    graceful = RevocationEvent(
        event_id="rev-1592-graceful",
        revocation_type=RevocationType.AGENT_REVOKED,
        target_id="agent-graceful",
        revoked_by="admin",
        reason="scheduled key rotation with drain window",
        timestamp=_dt.datetime(2026, 1, 15, 10, 5, 0, tzinfo=_dt.timezone.utc),
        mode=RevocationMode.GRACEFUL,
        effective_at=_dt.datetime(2026, 1, 15, 11, 0, 0, tzinfo=_dt.timezone.utc),
    )
    _write(
        "eatp3_revocation_graceful.json",
        {
            "description": "GRACEFUL revocation: revoked, but an effective_at "
            "grace deadline lets in-flight work drain before the revocation "
            "takes HARD effect. is_effective is False inside the window, True "
            "once the deadline passes. Irreversible (#1592).",
            "pact_type": "RevocationEvent",
            "conformance_requirement": "EATP-v3-revocation-mode",
            "input": graceful.to_dict(),
            "expected_mode": graceful.mode.value,
            "expected_effective_at": graceful.effective_at.isoformat(),
            "expected_reversible": False,
            "expected_is_effective_before_deadline": False,
            "expected_is_effective_after_deadline": True,
        },
    )

    # -- Revocation SUSPEND mode (reversible hold) --
    suspend = RevocationEvent(
        event_id="rev-1592-suspend",
        revocation_type=RevocationType.AGENT_REVOKED,
        target_id="agent-suspend",
        revoked_by="admin",
        reason="temporary hold pending review",
        timestamp=_dt.datetime(2026, 1, 15, 10, 6, 0, tzinfo=_dt.timezone.utc),
        mode=RevocationMode.SUSPEND,
    )
    _write(
        "eatp3_revocation_suspend.json",
        {
            "description": "SUSPEND revocation: a REVERSIBLE hold. The target is "
            "inactive while suspended and MAY be reinstated (SUSPENDED -> ACTIVE). "
            "A terminal IMMEDIATE/GRACEFUL revocation can NEVER be reinstated "
            "(trust state never relaxes) (#1592).",
            "pact_type": "RevocationEvent",
            "conformance_requirement": "EATP-v3-revocation-mode",
            "input": suspend.to_dict(),
            "expected_mode": suspend.mode.value,
            "expected_effective_at": None,
            "expected_reversible": True,
        },
    )


if __name__ == "__main__":
    main()
