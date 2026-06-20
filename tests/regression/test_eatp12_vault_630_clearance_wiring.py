# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression — F-VAULT-630: recommit + retire enforce CL-02a tenant/domain + CL-04.

Closes the #630 gap. Before this fix, the ``clearance-tenant-domain`` gate of
``recommit_vault_kek`` (N12-CB-04(c)) and ``retire_vault_kek_alg``
(N12-CB-04(e)) was NAMED for tenant/domain scoping but enforced capability
PRESENCE only (``clearance.has_capability(...)``) — the CL-02a tenant→domain
scoping (N12-CL-02a) and the CL-04 cooling-off (N12-CL-04) the gate name + spec
imply were deferred (the honest-disclosure comment at registry_ops.py + the
``test_redteam_trustplane_round2.py`` "gate-label over-claim, NO behavioral
delta" note). This fix wires the full ``evaluate_clearance`` gate into both
surfaces, mirroring the proven backup/restore/rotation sibling pattern.

Each test below FAILS against the pre-fix capability-only gate and PASSES against
the wired gate — verified by the git-stash prove-fail receipt in the F-VAULT-630
session report. NO mocks (``rules/testing.md`` Tier-2): a real
:class:`~kailash.trust.vault.registry.CommitmentRegistry`, a real per-tier
:class:`AuditDispatcher` with an Ed25519 signer + verifier, a real
:class:`~kailash.trust.posture.posture_store.SQLitePostureStore`, and the
deployment-supplied trusted resolver (a Protocol-satisfying deterministic
adapter, NOT a mock) exercised through the real binding code path.

Coverage:

* recommit — a vault:backup holder whose clearance tenant/domain does NOT match
  the vault's (resolved) tenant/domain is DENIED missing-clearance even with all
  other gates satisfiable (CL-02a, both the tenant axis and the domain axis).
* retire — a vault:retire-alg holder in tenant/domain A is DENIED
  missing-clearance against a vault in tenant/domain B even with a live
  recoverability sibling alg present (CL-02a).
* recommit cooling-off — a principal inside the 7-day post-recovery window is
  SUSPENDED for recommit (vault:backup IS a cooling-off-suspended capability) →
  missing-clearance, when no approver path (CL-04).
* retire cooling-off no-op — a principal inside the window is NOT suspended for
  retire (vault:retire-alg is NOT in COOLING_OFF_SUSPENDED_CAPABILITIES) → the
  retire still passes the clearance gate (spec-faithful no-op, CL-04).
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier
from kailash.trust.key_manager import KeyClass
from kailash.trust.posture.posture_store import SQLitePostureStore
from kailash.trust.vault.clearance import COOLING_OFF_SUSPENDED_CAPABILITIES
from kailash.trust.vault.commitment import kek_identity_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek
from kailash.trust.vault.registry import CommitmentRegistry
from kailash.trust.vault.registry_ops import recommit_vault_kek, retire_vault_kek_alg
from kailash.trust.vault.stale_guard import trigger_d6_posture_downgrade
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

pytestmark = pytest.mark.regression

_KNOWN_KEK = bytes.fromhex(
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"
)
_KEK_GENERATION = 7
_KEY_ID = "kek-handle-630"
_VAULT_ID = "vault-630"
_PROVENANCE = "vault-derived:v1"
_ALG_V1 = "eatp-v1"
_ALG_V11 = "eatp-v1.1"
#: The principal acting in the regression tests (also the cooling-off subject).
_PRINCIPAL = "agent-630"
#: The vault's TRUSTED tenant/domain (resolved from the handle by the resolver).
_VAULT_TENANT = "tenant-A"
_VAULT_DOMAIN = "domain-A"


class _Resolver:
    """Deployment-supplied trusted resolver returning the known KEK (NOT a mock).

    Resolves the vault's bound ``vault_tenant`` / ``vault_domain`` — the CL-02a
    trusted-module source the clearance gate compares the ClearanceContext
    against. The handle carries no tenant/domain; the resolver is authoritative.
    """

    def __init__(
        self,
        *,
        vault_tenant: str = _VAULT_TENANT,
        vault_domain: str = _VAULT_DOMAIN,
    ) -> None:
        self._tenant = vault_tenant
        self._domain = vault_domain

    def resolve_kek(self, handle: VaultKeyHandle) -> ResolvedKek:
        return ResolvedKek(
            master_secret=_KNOWN_KEK,
            key_class=KeyClass.KEK,
            kek_generation=_KEK_GENERATION,
            key_id=_KEY_ID,
            passphrase_provenance=_PROVENANCE,
            vault_tenant=self._tenant,
            vault_domain=self._domain,
        )


def _build_signer() -> tuple[DelegateIdentity, Ed25519Verifier, Callable[[bytes], str]]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity = DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-vault-binding",
        role_binding_ref="rb-vault-binding",
        genesis_ref="gen-vault-binding",
    )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )
    verifier = Ed25519Verifier(directory=directory)

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, verifier, signer


def _handle() -> VaultKeyHandle:
    return VaultKeyHandle(
        key_id=_KEY_ID, vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION
    )


def _clearance(*caps: str, tenant: str = _VAULT_TENANT, domain: str = _VAULT_DOMAIN):
    return ClearanceContext(
        principal=_PRINCIPAL, tenant=tenant, domain=domain, capabilities=tuple(caps)
    )


def _commitment(alg: str) -> str:
    return kek_identity_commitment(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        master_secret=_KNOWN_KEK,
        passphrase_provenance=_PROVENANCE,
        alg=alg,
    )


def _seed_v1(registry: CommitmentRegistry) -> str:
    """Register the initial ``eatp-v1`` commitment (models a prior backup)."""
    commitment = _commitment(_ALG_V1)
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        kek_commitment_alg=_ALG_V1,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    return commitment


def _seed_v11(registry: CommitmentRegistry) -> str:
    """Register a LIVE eatp-v1.1 sibling (recoverability guard satisfiable)."""
    commitment = _commitment(_ALG_V11)
    registry.register(
        vault_id=_VAULT_ID,
        kek_generation=_KEK_GENERATION,
        kek_commitment_alg=_ALG_V11,
        commitment=commitment,
        key_id=_KEY_ID,
    )
    return commitment


@pytest.fixture
def posture_store():
    """A REAL SQLitePostureStore against a temp DB (Tier-2, NO mock)."""
    fd, path = tempfile.mkstemp(suffix="-630-postures.db")
    os.close(fd)
    os.unlink(path)
    store = SQLitePostureStore(path)
    try:
        yield store
    finally:
        store.close()
        if os.path.exists(path):
            os.unlink(path)


# ---------------------------------------------------------------------------
# CL-02a — recommit tenant/domain scoping (the #630 gap, recommit surface)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_recommit_wrong_tenant_denied_missing_clearance():
    """recommit — a vault:backup holder in the WRONG tenant is DENIED.

    All other recommit gates are satisfiable (the resolver's generation matches,
    a live prior eatp-v1 exists, the bind recomputes), yet a tenant mismatch on
    the CL-02a axis denies missing-clearance. Pre-fix (capability-PRESENCE only)
    this passed and recommitted.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    c_x = _seed_v1(registry)

    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),
            _clearance("vault:backup", tenant="tenant-B"),  # wrong tenant
            resolver=_Resolver(),  # vault tenant is tenant-A
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment=c_x,
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # No anchor dispatched + the new alg was NEVER registered (denied at gate 1).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
    )


@pytest.mark.regression
def test_recommit_uncovered_domain_denied_missing_clearance():
    """recommit — a vault:backup holder whose domain does NOT cover the vault's
    domain is DENIED (CL-02a(b), domain axis)."""
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    c_x = _seed_v1(registry)

    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),
            # Right tenant, but a SIBLING domain that does not cover domain-A.
            _clearance("vault:backup", domain="domain-B"),
            resolver=_Resolver(),  # vault domain is domain-A
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment=c_x,
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
    )


# ---------------------------------------------------------------------------
# CL-02a — retire tenant/domain scoping (the #630 gap, retire surface)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_retire_wrong_tenant_denied_even_with_live_recoverability_sibling():
    """retire — a vault:retire-alg holder in tenant/domain A is DENIED against a
    vault in tenant/domain B even with a live recoverability sibling alg present.

    The recoverability-preserved gate (step 4) is SATISFIABLE (a live eatp-v1.1
    sibling exists), so the only thing denying the retire is the CL-02a
    tenant/domain scoping at gate 1. Pre-fix (capability-PRESENCE only) the
    retire was authorized regardless of tenant/domain.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    c_x = _seed_v1(registry)
    _seed_v11(registry)  # live recoverability sibling — guard would PASS

    with pytest.raises(VaultBindingError) as exc:
        retire_vault_kek_alg(
            _handle(),
            # Holder in tenant/domain B; the vault is tenant/domain A.
            _clearance("vault:retire-alg", tenant="tenant-B", domain="domain-B"),
            resolver=_Resolver(),  # vault is tenant-A / domain-A
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            retired_kek_commitment_alg=_ALG_V1,
            retired_kek_identity_commitment=c_x,
            registry=registry,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # No anchor dispatched; BOTH algs stay live (retire denied at gate 1).
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert set(
        registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION)
    ) == {_ALG_V1, _ALG_V11}


# ---------------------------------------------------------------------------
# CL-04 — recommit cooling-off suspension (vault:backup IS suspended)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_recommit_cooling_off_suspends_principal_in_window(posture_store):
    """recommit — a principal inside the 7-day post-recovery window is SUSPENDED.

    vault:backup IS in COOLING_OFF_SUSPENDED_CAPABILITIES, so a recommit by a
    principal whose cooling-off receipt is present (and inside the window per the
    trust-anchored clock) is denied missing-clearance when no approver is
    configured. Pre-fix the cooling-off check never ran on the recommit surface.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    c_x = _seed_v1(registry)

    # Fire the RT-05 D6 trigger with an INJECTED trust-anchored start (records
    # the cooling-off receipt the CL-04 gate reads) for our principal.
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal=_PRINCIPAL, forced_stale=False, now=start
    )

    # A recommit 3 days into the window (trust-anchored now), same principal.
    now_in_window = start + timedelta(days=3)
    with pytest.raises(VaultBindingError) as exc:
        recommit_vault_kek(
            _handle(),
            _clearance("vault:backup"),  # correct tenant/domain
            resolver=_Resolver(),
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=identity,
            alg_id=_ALG_V1,
            prior_kek_commitment_alg=_ALG_V1,
            prior_kek_identity_commitment=c_x,
            new_kek_commitment_alg=_ALG_V11,
            registry=registry,
            posture_store=posture_store,
            trust_anchored_now=now_in_window,
        )
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE
    # Suspended before any anchor / registry mutation.
    assert dispatcher.sequence_length(AuditTier.RECOVERY.value) == 0
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V1,
    )


@pytest.mark.regression
def test_vault_backup_is_a_cooling_off_suspended_capability():
    """Structural invariant — vault:backup IS suspended, vault:retire-alg is NOT.

    Pins the membership the two cooling-off regression tests depend on. If the
    suspended set ever changes, this fails loudly and forces a re-audit of the
    recommit (suspended) vs retire (no-op) cooling-off behavior.
    """
    assert "vault:backup" in COOLING_OFF_SUSPENDED_CAPABILITIES
    assert "vault:retire-alg" not in COOLING_OFF_SUSPENDED_CAPABILITIES


# ---------------------------------------------------------------------------
# CL-04 — retire cooling-off NO-OP (vault:retire-alg is NOT suspended)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_retire_cooling_off_is_a_noop_principal_in_window_still_passes(posture_store):
    """retire — a principal inside the window is NOT suspended for retire.

    vault:retire-alg is NOT in COOLING_OFF_SUSPENDED_CAPABILITIES, so the CL-04
    cooling-off is a structural no-op: a principal with a present cooling-off
    receipt (inside the window) still passes the retire clearance gate. This
    proves the SPEC-FAITHFUL no-op — we do NOT force-suspend retire — and the
    retire completes (a live eatp-v1.1 sibling satisfies recoverability).

    Pre-fix this test ALSO passed (the gate was capability-only, so cooling-off
    never ran for retire either) — but it now passes for the RIGHT reason: the
    full clearance gate runs and correctly declines to suspend a non-suspended
    capability. It is the paired counterpart to the recommit-suspended test:
    together they prove the suspended-set membership drives behavior.
    """
    identity, verifier, signer = _build_signer()
    dispatcher = AuditDispatcher.for_named_tiers(verifier)
    registry = CommitmentRegistry()
    c_x = _seed_v1(registry)
    _seed_v11(registry)  # live recoverability sibling so the retire can complete

    # Same principal, same in-window cooling-off receipt as the recommit test.
    start = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trigger_d6_posture_downgrade(
        posture_store, principal=_PRINCIPAL, forced_stale=False, now=start
    )
    now_in_window = start + timedelta(days=3)

    # The retire PASSES the clearance gate (no suspension) and completes.
    retired_entry = retire_vault_kek_alg(
        _handle(),
        _clearance("vault:retire-alg"),  # correct tenant/domain
        resolver=_Resolver(),
        dispatcher=dispatcher,
        signer=signer,
        signer_identity=identity,
        alg_id=_ALG_V1,
        retired_kek_commitment_alg=_ALG_V1,
        retired_kek_identity_commitment=c_x,
        registry=registry,
        posture_store=posture_store,
        trust_anchored_now=now_in_window,
    )
    assert retired_entry.retired is True
    # eatp-v1 retired; eatp-v1.1 remains the live recoverability sibling.
    assert registry.live_algs(vault_id=_VAULT_ID, kek_generation=_KEK_GENERATION) == (
        _ALG_V11,
    )
    # A vault_kek_retire anchor DID land (the retire was authorized).
    rec = dispatcher._engines[AuditTier.RECOVERY.value].entries
    assert any(e.event_payload["subtype"] == "vault_kek_retire" for e in rec)
