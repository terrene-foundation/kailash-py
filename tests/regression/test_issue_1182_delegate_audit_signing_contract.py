# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for #1182 — delegate audit-chain sign/verify contract.

Root cause (#1182): ``AuditChainEngine.emit_event``'s signature contract
was structurally unsatisfiable. The runtime sign-site
(``DelegateRuntime._emit_phase_audit``) signed the PAYLOAD ALONE, while the
engine verify-site verified the signature against ``AuditChainEntry``'s
FULL pre-signature dict (``to_signing_dict()`` → sequence + previous_hash +
event_type + event_payload + signer_delegate_id + signed_at). The engine
assigns ``sequence`` / ``previous_hash`` / ``signed_at`` AFTER it receives
the signature, so the caller could NEVER produce a matching signature —
``AuditChainSignatureError`` raised at sequence=0 under any real (non-Null)
verifier. ``NullVerifier`` masked it (it rejects everything regardless).

The fix (Design (a)): a single shared content pre-image —
``content_signing_bytes(event_type, event_payload, signer_delegate_id)`` —
is signed by the caller AND verified by the engine. The signature attests
delegate AUTHORSHIP of the event CONTENT; it deliberately EXCLUDES the
engine-assigned fields (the caller cannot know them at signing time).
Ordering tamper-evidence (reorder / insert / delete) stays with the
hash-chain: each entry's ``previous_hash`` is the SHA-256 of the prior
entry's full canonical dict (which includes sequence + previous_hash +
the prior signature), so mutating a committed entry breaks the recomputed
linkage of every successor. Signature attests authorship; hash-chain
attests ordering — orthogonal, both load-bearing.

These tests use REAL Ed25519 cryptography end-to-end — NO mocking, NO
NullVerifier — per the #1182 acceptance criteria + ``rules/testing.md``
§ "Behavioral Regression Tests Over Source-Grep" and § Tier-2/Tier-3
no-mocking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.audit import (
    AuditChainEngine,
    AuditChainSignatureError,
    DelegateEventType,
    content_signing_bytes,
)
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchSurface,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope
from kailash.delegate.runtime import DelegateRuntime, Posture
from kailash.delegate.trust import TenantScope, TenantScopedCascade
from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    PrincipalDirectory,
    Role,
    RoleLifecycleState,
    RoleScope,
)
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain
from kailash.trust.envelope import ConstraintEnvelope, FinancialConstraint

# ---------------------------------------------------------------------------
# Real-crypto helpers (NO mocks, NO NullVerifier)
# ---------------------------------------------------------------------------


def _make_keypair() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _pub_bytes(priv: Ed25519PrivateKey) -> bytes:
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _make_signer(priv: Ed25519PrivateKey):
    """Real Ed25519 signer over whatever canonical bytes it is handed."""

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return signer


def _build_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-1182",
        role_binding_ref="rb-1182",
        genesis_ref="g-1182",
    )


def _build_chain(agent_id: str) -> TrustLineageChain:
    return TrustLineageChain(
        genesis=GenesisRecord(
            id="g-1182",
            agent_id=agent_id,
            authority_id="auth-1182",
            authority_type=AuthorityType.SYSTEM,
            created_at=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
            signature="00" * 64,
        )
    )


def _build_envelope() -> DelegateConstraintEnvelope:
    block = GenesisRecord(
        id="g-env-1182",
        agent_id="agent-env-1182",
        authority_id="auth-env-1182",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    genesis = DelegateGenesisRecord(
        block=block, spec_version="1", capabilities=("read",)
    )
    return DelegateConstraintEnvelope.from_genesis(
        ConstraintEnvelope(financial=FinancialConstraint(budget_limit=1000.0)),
        genesis,
    )


def _build_role() -> Role:
    return Role(
        role_id=uuid.uuid4(),
        display_name="1182-role",
        scope=RoleScope(
            domain="finance",
            capabilities=CapabilitySet(capabilities=("noop.read",)),
        ),
        lifecycle=RoleLifecycleState.ACTIVE,
    )


class _NoOpConnector(Connector):
    """Real Protocol-satisfying no-op connector (NOT a mock).

    Returns a deterministic result with one audit-visible event so the
    full ACTING-phase dispatch + audit-emit path runs under real crypto.
    """

    connector_id = "noop-1182"
    connector_kind = "noop"
    requires_capabilities = frozenset({"noop.read"})

    def __init__(self, *, tenant_id_observed: str) -> None:
        self.tenant_id_observed = tenant_id_observed
        self.invocations: list[dict] = []

    async def invoke(self, input_payload, *, identity, envelope):
        self.invocations.append({"id": input_payload.get("id", "n/a")})
        return ConnectorInvocationResult(
            payload={"ok": True},
            audit_events=(DelegateEventType.EXTERNAL_SIDE_EFFECT,),
            tenant_id_observed=self.tenant_id_observed,
            external_side_effect=True,
        )


class _Signature:
    name = "noop-1182-sig"
    input_schema = {"id": str}
    output_schema = {"ok": bool}


def _build_real_runtime(*, tenant_id: str = "tenant-1182"):
    """Wire a full DelegateRuntime with a REAL Ed25519Verifier (no Null)."""
    from kailash.delegate.verifier import Ed25519Verifier

    priv = _make_keypair()
    identity = _build_identity()
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: _pub_bytes(priv)},
    )
    chain = _build_chain(agent_id=str(identity.delegate_id))
    audit_engine = AuditChainEngine(
        chain=chain, verifier=Ed25519Verifier(directory=directory)
    )
    cascade = TenantScopedCascade(
        tenant=TenantScope.for_tenant(tenant_id),
        verifier=Ed25519Verifier(directory=directory),
    )
    signer = _make_signer(priv)
    # Seed the root grantee with a real grant_proof (cascade verifies it).
    grant_proof = signer(
        canonical_json_dumps(
            {"delegate_id": str(identity.delegate_id), "tenant": tenant_id}
        ).encode("utf-8")
    )
    cascade.register_root_grantee(identity, grant_proof=grant_proof)
    # R2 composition gate (Invariant 4) requires the SAME envelope + role
    # object in the DispatchSurface AND the DelegateRuntime — build once.
    envelope = _build_envelope()
    role = _build_role()
    surface = DispatchSurface(
        connector=_NoOpConnector(tenant_id_observed=tenant_id),
        signature=_Signature(),
        envelope=envelope,
        identity=identity,
        audit_engine=audit_engine,
        trust_cascade=cascade,
        role=role,
        signer=signer,
    )
    runtime = DelegateRuntime(
        dispatch_surface=surface,
        audit_engine=audit_engine,
        cascade=cascade,
        envelope=envelope,
        identity=identity,
        signer=signer,
        posture=Posture.L5_DELEGATED,
    )
    return runtime, audit_engine, identity, priv


# ---------------------------------------------------------------------------
# Test 1 — sign/verify byte-equality at the contract level
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_issue_1182_sign_site_and_verify_site_share_identical_bytes() -> None:
    """The bytes the runtime signs == the bytes emit_event verifies.

    Before #1182 the runtime signed ``canonical_json_dumps(payload)`` while
    the engine verified against ``entry.to_signing_bytes()`` (full dict with
    engine-assigned fields). They could never be equal at sequence>0 OR even
    at sequence=0 (the runtime omitted sequence/previous_hash/signed_at
    entirely). The fix routes BOTH through ``content_signing_bytes``.
    """
    from kailash.delegate.audit import AuditChainEntry

    did = uuid.uuid4()
    event_type = DelegateEventType.EXTERNAL_SIDE_EFFECT.value
    payload = {"run_id": str(uuid.uuid4()), "phase": "acting"}

    # Sign-site bytes (what the runtime/dispatch produce via the helper).
    sign_site_bytes = content_signing_bytes(event_type, payload, did)

    # Verify-site bytes: build the entry the engine would build (with
    # arbitrary engine-assigned fields) and ask for its content-signing
    # bytes — they MUST equal the sign-site bytes regardless of sequence /
    # previous_hash / signed_at.
    entry = AuditChainEntry(
        sequence=7,
        previous_hash="ab" * 32,
        event_type=event_type,
        event_payload=payload,
        signer_delegate_id=did,
        signed_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        signature="00" * 64,
    )
    verify_site_bytes = entry.to_content_signing_bytes()

    assert sign_site_bytes == verify_site_bytes
    # And the content pre-image must NOT contain the engine-assigned fields.
    assert b"previous_hash" not in sign_site_bytes
    assert b"sequence" not in sign_site_bytes
    assert b"signed_at" not in sign_site_bytes
    # It MUST bind event_type + payload + signer (authorship attestation).
    assert b"event_type" in sign_site_bytes
    assert b"event_payload" in sign_site_bytes
    assert b"signer_delegate_id" in sign_site_bytes


# ---------------------------------------------------------------------------
# Test 2 — the issue repro: emit_event with a runtime-path signature SUCCEEDS
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_issue_1182_emit_event_accepts_runtime_path_signature() -> None:
    """A signature over the content pre-image verifies under Ed25519Verifier.

    This is the #1182 repro, corrected to sign what the runtime now signs:
    the content pre-image. Pre-fix, NO caller could produce a matching
    signature; emit_event raised AuditChainSignatureError at sequence=0.
    """
    from kailash.delegate.verifier import Ed25519Verifier

    priv = _make_keypair()
    did = uuid.uuid4()
    ident = DelegateIdentity(
        delegate_id=did,
        sovereign_ref="s",
        role_binding_ref="r",
        genesis_ref="g",
        principal_kind="delegate",
    )
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={did: _pub_bytes(priv)},
    )
    engine = AuditChainEngine(
        chain=_build_chain(agent_id=str(did)),
        verifier=Ed25519Verifier(directory),
    )
    payload = {"phase": "ingest", "delegate_id": str(did)}
    signature = priv.sign(
        content_signing_bytes(
            DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload, did
        )
    ).hex()

    # Pre-fix: this raised AuditChainSignatureError at sequence=0.
    entry = engine.emit_event(
        DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload, ident, signature
    )
    assert entry.sequence == 0
    assert len(engine.entries) == 1

    # A second event advances the sequence + links the hash-chain.
    payload2 = {"phase": "act"}
    sig2 = priv.sign(
        content_signing_bytes(
            DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload2, did
        )
    ).hex()
    entry2 = engine.emit_event(
        DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload2, ident, sig2
    )
    assert entry2.sequence == 1
    assert entry2.previous_hash != ""  # hash-chain linked


# ---------------------------------------------------------------------------
# Test 3 — end-to-end: DelegateRuntime.execute() completes under real crypto
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1182_delegate_runtime_execute_completes_under_ed25519() -> None:
    """Full TAOD execute() reaches COMPLETED under a REAL Ed25519Verifier.

    Pre-fix this landed FAILED at phase='thinking' with
    AuditChainSignatureError (the first audit emit's signature could not be
    verified). No mocking, no NullVerifier — real keypair + real connector.
    """
    runtime, audit_engine, _identity, _priv = _build_real_runtime()

    result = await runtime.execute({"id": "issue-1182-e2e"})

    assert result.taod_state.phase == "completed", (
        f"execute() did not complete (phase={result.taod_state.phase!r}); "
        f"#1182 sign/verify contract still broken"
    )
    assert result.dispatch_result is not None
    # Every audit entry verified + landed (4 TAOD transitions + 1 dispatch).
    assert len(audit_engine.entries) >= 4
    # head_hash is set => the chain materialized.
    assert audit_engine.head_hash() is not None


# ---------------------------------------------------------------------------
# Test 4 — tamper-evidence: mutating a committed entry breaks the hash-chain
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_issue_1182_hash_chain_detects_entry_tampering() -> None:
    """The fix preserves ordering tamper-evidence via the hash-chain.

    The signature no longer covers sequence/previous_hash, so we MUST prove
    that reorder/insert/delete/mutation is still detectable INDEPENDENTLY —
    through the previous_hash linkage. Mutating a committed entry's payload,
    sequence, or previous_hash makes the recomputed predecessor-hash of the
    NEXT entry diverge from the stored previous_hash.
    """
    from kailash.delegate.audit import AuditChainEntry

    priv = _make_keypair()
    did = uuid.uuid4()
    ident = DelegateIdentity(
        delegate_id=did,
        sovereign_ref="s",
        role_binding_ref="r",
        genesis_ref="g",
    )
    from kailash.delegate.verifier import Ed25519Verifier

    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={did: _pub_bytes(priv)},
    )
    engine = AuditChainEngine(
        chain=_build_chain(agent_id=str(did)),
        verifier=Ed25519Verifier(directory),
    )

    def _emit(payload):
        sig = priv.sign(
            content_signing_bytes(
                DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload, did
            )
        ).hex()
        return engine.emit_event(
            DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload, ident, sig
        )

    e0 = _emit({"phase": "ingest"})
    e1 = _emit({"phase": "act"})
    e2 = _emit({"phase": "done"})

    # The committed chain is internally consistent: each entry's
    # previous_hash equals SHA-256 of the prior entry's full canonical dict.
    import hashlib

    def _entry_hash(entry: AuditChainEntry) -> str:
        return hashlib.sha256(
            canonical_json_dumps(entry.to_canonical_dict()).encode("utf-8")
        ).hexdigest()

    assert e0.previous_hash == ""  # genesis
    assert e1.previous_hash == _entry_hash(e0)
    assert e2.previous_hash == _entry_hash(e1)

    # TAMPER: forge a replacement for e0 with a mutated payload but reuse
    # its (sequence, previous_hash, signature). The signature still
    # "verifies" the CONTENT in isolation only if re-signed — but the point
    # is the HASH-CHAIN: e1.previous_hash was computed over the ORIGINAL e0.
    tampered_e0 = AuditChainEntry(
        sequence=e0.sequence,
        previous_hash=e0.previous_hash,
        event_type=e0.event_type,
        event_payload={"phase": "INGEST-TAMPERED"},  # mutated content
        signer_delegate_id=e0.signer_delegate_id,
        signed_at=e0.signed_at,
        signature=e0.signature,
    )
    # The successor's stored previous_hash no longer matches the recomputed
    # hash of the tampered predecessor — ordering tamper detected.
    assert e1.previous_hash != _entry_hash(tampered_e0)

    # Sequence tampering is equally detectable: a re-sequenced entry hashes
    # differently, breaking every downstream previous_hash linkage.
    resequenced_e1 = AuditChainEntry(
        sequence=99,  # mutated ordering
        previous_hash=e1.previous_hash,
        event_type=e1.event_type,
        event_payload=e1.event_payload,
        signer_delegate_id=e1.signer_delegate_id,
        signed_at=e1.signed_at,
        signature=e1.signature,
    )
    assert e2.previous_hash != _entry_hash(resequenced_e1)


# ---------------------------------------------------------------------------
# Test 5 — a payload-only signature (the pre-#1182 sign-site) is REJECTED
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_issue_1182_payload_only_signature_is_rejected() -> None:
    """Signing the bare payload (the pre-fix runtime behaviour) MUST fail.

    Guards against a regression that re-introduces the payload-only sign
    pre-image: the engine verifies the content pre-image (which includes
    event_type + signer_delegate_id), so a signature over the bare payload
    does not verify.
    """
    from kailash.delegate.verifier import Ed25519Verifier

    priv = _make_keypair()
    did = uuid.uuid4()
    ident = DelegateIdentity(
        delegate_id=did,
        sovereign_ref="s",
        role_binding_ref="r",
        genesis_ref="g",
    )
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={did: _pub_bytes(priv)},
    )
    engine = AuditChainEngine(
        chain=_build_chain(agent_id=str(did)),
        verifier=Ed25519Verifier(directory),
    )
    payload = {"phase": "ingest"}
    # Pre-#1182 sign-site: signature over the bare payload alone.
    bad_sig = priv.sign(canonical_json_dumps(payload).encode("utf-8")).hex()

    with pytest.raises(AuditChainSignatureError, match="content_signing_bytes"):
        engine.emit_event(
            DelegateEventType.EXTERNAL_SIDE_EFFECT.value, payload, ident, bad_sig
        )
    assert engine.entries == ()
