# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration test for ``AuditChainEngine`` ↔ ``TrustLineageChain``.

S4 #1035 — Tier-2 wiring test per ``facade-manager-detection.md`` MUST
Rule 1 ("Every Manager-Shape Class Has a Tier 2 Test"):
``AuditChainEngine`` is an ``*Engine`` shape that owns long-lived chain
state and emits side-effects (substrate ``AuditAnchor`` writes onto the
wrapped ``TrustLineageChain.audit_anchors`` list).

**Tier classification:** the substrate ``TrustLineageChain`` is a real
``@dataclass`` (not a ``typing.Protocol`` satisfier), so the
"Protocol-Satisfying Deterministic Adapter" exception in
``rules/testing.md`` does NOT apply. The test exercises the load-bearing
wiring contract (engine emits events → substrate chain holds them, head
hash chains correctly, integrity replay reproduces the SHA-256 linkage)
against the REAL substrate — no mocks, no patches. Real-Postgres
backed durability is deferred to S6 runtime (per S4 shard plan: the
audit chain primitive lives above durability; the substrate's pluggable
audit-anchor store binds to Postgres at S6).

This test pairs with the S2.5 ``test_genesis_chain_roundtrip.py`` pattern
— same shape: import path + facade-call shape + canonical-bytes contract
end-to-end through the real substrate.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest

from kailash.delegate.audit import AuditChainEngine, DelegateEventType
from kailash.delegate.types import DelegateIdentity
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import (
    ActionResult,
    AuthorityType,
    GenesisRecord,
    TrustLineageChain,
)


def _build_chain(agent_id: str) -> TrustLineageChain:
    return TrustLineageChain(
        genesis=GenesisRecord(
            id=f"g-{agent_id}",
            agent_id=agent_id,
            authority_id=f"auth-{agent_id}",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        )
    )


def _build_identity(genesis_ref: str = "g-tier2-wiring") -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-tier2",
        role_binding_ref="rb-tier2",
        genesis_ref=genesis_ref,
    )


@pytest.mark.integration
def test_engine_writes_substrate_audit_anchor_per_event() -> None:
    """Emitting N events MUST land N ``AuditAnchor`` rows on the substrate.

    The facade-manager-detection.md MUST Rule 1 contract: a wiring test
    that observes the substrate STATE CHANGE through the same surface a
    user would. This asserts the engine doesn't drift into a parallel
    in-memory list — every event lands on the real
    ``TrustLineageChain.audit_anchors`` the substrate persists.
    """
    chain = _build_chain("agent-tier2-wiring")
    engine = AuditChainEngine(chain=chain)
    signer = _build_identity(genesis_ref="g-agent-tier2-wiring")

    # Substrate starts with zero anchors (genesis only).
    assert len(chain.audit_anchors) == 0

    # Emit 5 audit-visible events.
    for i in range(5):
        engine.emit_event(
            event_type=DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER,
            payload={"step": i, "label": f"transition-{i}"},
            signer_identity=signer,
            signature=("%032x" % i).rjust(128, "f"),
        )

    # External state assertion: substrate observed every event.
    assert len(chain.audit_anchors) == 5
    # Each substrate anchor was tagged with the Delegate event type.
    for anchor in chain.audit_anchors:
        assert anchor.action == DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER
        assert anchor.agent_id == "agent-tier2-wiring"
        # Substrate result is SUCCESS (audit is post-fact; failed audit
        # writes are the substrate's failure-mode, not Delegate's).
        assert anchor.result == ActionResult.SUCCESS

    # Engine's own snapshot matches substrate cardinality.
    assert len(engine.entries) == 5


@pytest.mark.integration
def test_engine_chain_integrity_replay_reproduces_linkage() -> None:
    """Replaying the chain MUST reproduce every previous_hash byte-for-byte.

    The chain-link contract: entry N+1.previous_hash ==
    SHA-256(canonical_json(entry N)). This is the cryptographic backbone
    cross-SDK verifiers consume; the test re-derives every linkage and
    asserts byte-equality.
    """
    chain = _build_chain("agent-replay")
    engine = AuditChainEngine(chain=chain)
    signer = _build_identity(genesis_ref="g-agent-replay")

    # Emit a 4-event chain — S4.5 collapsed py's 8 string sentinels to
    # 5 rs-canonical variants; the lost py distinctions
    # (lifecycle_transition / posture_ratchet / cascade_emission) ride
    # in payload["subtype"] per the migration map in
    # ``DelegateEventType.__doc__``.
    events = [
        (
            DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER,
            {"subtype": "lifecycle_transition", "to": "instantiated"},
        ),
        (
            DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER,
            {"subtype": "posture_ratchet", "from": 1, "to": 2},
        ),
        (
            DelegateEventType.GRANT_CONSUMPTION,
            {"subtype": "cascade_emission", "child_id": "child-1"},
        ),
        (DelegateEventType.GRANT_CONSUMPTION, {"grant_id": "g-x"}),
    ]
    for i, (event_type, payload) in enumerate(events):
        engine.emit_event(
            event_type=event_type,
            payload=payload,
            signer_identity=signer,
            signature=("%02x" % (i + 10)) * 64,
        )

    entries = engine.entries
    assert len(entries) == 4

    # Replay: verify EVERY link byte-for-byte.
    assert entries[0].previous_hash == ""
    for i in range(1, len(entries)):
        prior = entries[i - 1]
        recomputed = hashlib.sha256(
            canonical_json_dumps(prior.to_canonical_dict()).encode("utf-8")
        ).hexdigest()
        assert entries[i].previous_hash == recomputed, (
            f"linkage drift at entry {i}: expected {recomputed!r}, "
            f"got {entries[i].previous_hash!r}"
        )

    # head_hash matches SHA-256 of the tail entry's canonical bytes.
    tail = entries[-1]
    expected_head = hashlib.sha256(
        canonical_json_dumps(tail.to_canonical_dict()).encode("utf-8")
    ).hexdigest()
    assert engine.head_hash() == expected_head


@pytest.mark.integration
def test_engine_emits_all_audit_visible_event_types_through_substrate() -> None:
    """Every audit-visible DelegateEventType variant rides the substrate.

    Per S4.5 the variant set collapsed from py's 8 string sentinels to
    rs-canonical 5 variants — 4 are audit-visible and 1
    (REASONING_SCRATCHPAD) is reasoning-private (C3 audit-visibility
    classifier). This test covers the 4 audit-visible variants only;
    REASONING_SCRATCHPAD rejection has a dedicated unit test.
    """
    chain = _build_chain("agent-type-coverage")
    engine = AuditChainEngine(chain=chain)
    signer = _build_identity(genesis_ref="g-agent-type-coverage")

    audit_visible_types = [
        DelegateEventType.EXTERNAL_SIDE_EFFECT,
        DelegateEventType.CONSTRAINT_DECISION,
        DelegateEventType.GRANT_CONSUMPTION,
        DelegateEventType.POSTURE_OR_SOVEREIGN_HANDOVER,
    ]

    for i, event_type in enumerate(audit_visible_types):
        entry = engine.emit_event(
            event_type=event_type,
            payload={"index": i},
            signer_identity=signer,
            signature=("%02x" % i) * 64,
        )
        assert entry.event_type == event_type
        assert entry.sequence == i

    # Substrate observed every audit-visible type. Per S4.5 the
    # ``str``-backed Enum sub-class's ``.value`` IS the wire form;
    # ``action`` carries the bare string sentinel both forms compare
    # against ("external_side_effect", etc.).
    actions_seen = {a.action for a in chain.audit_anchors}
    assert actions_seen == {t.value for t in audit_visible_types}


@pytest.mark.integration
def test_engine_substrate_anchor_payload_is_canonical_json() -> None:
    """Substrate ``AuditAnchor.trust_chain_hash`` holds canonical-JSON bytes.

    Cross-SDK verifiers consume the substrate anchor's trust_chain_hash
    field. The contract: it's the ``canonical_json_dumps`` of the
    typed entry's canonical dict — byte-stable across processes, byte-
    equal to what the rs verifier expects.
    """
    chain = _build_chain("agent-canon")
    engine = AuditChainEngine(chain=chain)
    signer = _build_identity(genesis_ref="g-agent-canon")

    # DISPATCH_INVOCATION in pre-S4.5 → EXTERNAL_SIDE_EFFECT + subtype.
    entry = engine.emit_event(
        event_type=DelegateEventType.EXTERNAL_SIDE_EFFECT,
        payload={
            "subtype": "dispatch_invocation",
            "connector": "test-connector",
            "op": "write",
        },
        signer_identity=signer,
        signature="9" * 128,
    )

    assert len(chain.audit_anchors) == 1
    anchor = chain.audit_anchors[0]
    # Round-1 finding C6 / analyst MED-4 outcome (b): the substrate
    # field is documented "Hash of trust chain at action time"
    # (kailash.trust.chain.AuditAnchor:526), so the substrate stores
    # the SHA-256 hex of the canonical-JSON, NOT the canonical-JSON
    # itself. The full canonical payload is still reproducible from
    # ``engine.entries[0].to_canonical_dict()`` for cross-SDK byte
    # parity contracts.
    canonical_payload = canonical_json_dumps(entry.to_canonical_dict())
    expected_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    assert anchor.trust_chain_hash == expected_hash
