# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 commitment-registry write operations — recommit + retire (W3-C2b).

This module owns the two registry-MUTATING operations the vault binding adds on
top of the C2a additive commitment registry
(:mod:`kailash.trust.vault.registry`):

* :func:`recommit_vault_kek` — **N12-CB-04(c)** hash-sunset migration. ADDITIVELY
  registers a new-algorithm commitment ``C_Y`` for ``(vault_id, kek_generation)``
  WITHOUT deleting the prior-algorithm commitment ``C_X``; both stay live until
  an explicit retire. Binds ``C_Y`` to the SAME reconstructed secret and the same
  ``(vault_id, kek_generation)`` as the prior, MUST NOT alter ``kek_generation``
  or ``vault_id``, and dispatches a ``vault_kek_recommit`` OUTCOME anchor (D2,
  ``recovery`` tier, AU-02b fail-closed) recording the from-to pair.

* :func:`retire_vault_kek_alg` — **N12-CB-04(e)** weak-algorithm sunset. Marks a
  specific ``(kek_commitment_alg -> kek_identity_commitment)`` registry entry
  ``retired=True`` (producing a NEW frozen :class:`CommitmentEntry` — registry
  entries are additive/immutable). Requires the distinct ``vault:retire-alg``
  capability (NOT ordinary ``vault:restore`` / ``vault:backup``), scoped by the
  full §4.2 clearance gate (CL-02a tenant/domain against the RESOLVED vault
  tenant/domain — the handle carries none, so the resolver is the trusted-module
  source); enforces the **recoverability guard** (a live, non-retired strong-alg
  commitment ``C_Y`` for the same ``(vault_id, kek_generation)`` MUST already
  exist so retirement never strands the corpus); and dispatches a
  ``vault_kek_retire`` OUTCOME anchor (D2, ``recovery`` tier, AU-02b).

Both operations drive their checks through the canonical first-failing gate
orders (:data:`~kailash.trust.vault.errors.RECOMMIT_GATE_ORDER` /
:data:`~kailash.trust.vault.errors.RETIRE_GATE_ORDER`) via
:func:`~kailash.trust.vault.errors.first_failing` (N12-FT-03), so two conformant
SDKs return the same first typed error for the same malformed write.

**AU-02b ordering (fail-closed).** The OUTCOME anchor is signed + dispatched
BEFORE the registry mutation commits. A dispatch failure RAISES (no receipt) and
the registry is never mutated — the registry mirrors the audited recovery-tier
anchor chain exactly as :func:`~kailash.trust.vault.backup.back_up_vault_key`
does (register only after the anchor lands).

The reconstructed secret is supplied by the same injected
:class:`~kailash.trust.vault.input_gates.VaultKeyResolver` boundary the
backup/restore surface uses; it is consumed for the recommit binding-mismatch
recompute AND to source the trusted vault tenant/domain the retire CL-02a gate
scopes against (the handle carries no tenant/domain), then ``zeroize()``-d in a
``finally`` (N12-IN-05). No plaintext crosses any return value, anchor payload,
or log line.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from kailash.delegate.types import DelegateIdentity
from kailash.trust.posture.postures import PostureStore
from kailash.trust.vault.anchors import (
    build_kek_recommit_anchor,
    build_kek_retire_anchor,
)
from kailash.trust.vault.backup import AnchorSigner, _sign_and_dispatch
from kailash.trust.vault.clearance import evaluate_clearance
from kailash.trust.vault.commitment import verify_commitment
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import (
    RECOMMIT_GATE_ORDER,
    RETIRE_GATE_ORDER,
    N12FT01Code,
    VaultBindingError,
    first_failing,
)
from kailash.trust.vault.input_gates import (
    BACKUP_CAPABILITY,
    ResolvedKek,
    VaultKeyResolver,
    require_clearance,
)
from kailash.trust.vault.registry import (
    CommitmentEntry,
    CommitmentRegistry,
    default_commitment_registry,
)
from kailash.trust.vault.types import ClearanceContext, VaultKeyHandle

logger = logging.getLogger(__name__)

__all__ = [
    "RETIRE_ALG_CAPABILITY",
    "recommit_vault_kek",
    "retire_vault_kek_alg",
]

#: The distinct high-consequence capability token a retirement requires
#: (N12-CB-04(e)(2)) — NEVER the ordinary ``vault:restore`` / ``vault:backup``
#: capability. A retire on an ordinary capability is rejected with
#: ``missing-clearance``.
RETIRE_ALG_CAPABILITY: str = "vault:retire-alg"


def recommit_vault_kek(
    key_handle: VaultKeyHandle,
    clearance: ClearanceContext,
    *,
    resolver: VaultKeyResolver,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    alg_id: str,
    prior_kek_commitment_alg: str,
    prior_kek_identity_commitment: str,
    new_kek_commitment_alg: str,
    registry: Optional[CommitmentRegistry] = None,
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    principal: Optional[str] = None,
    posture_store: Optional[PostureStore] = None,
    trust_anchored_now: Optional[datetime] = None,
    approver_configured: bool = False,
) -> CommitmentEntry:
    """ADDITIVELY recommit a KEK commitment under a new algorithm (N12-CB-04(c)).

    Hash-sunset migration: registers a new-algorithm commitment ``C_Y`` for
    ``(key_handle.vault_id, key_handle.kek_generation)`` WITHOUT deleting the
    prior-algorithm commitment ``C_X``; both stay live until an explicit retire.
    The new commitment is recomputed (C1) over the SAME reconstructed secret +
    same ``(vault_id, kek_generation)`` as the prior and bound under
    ``new_kek_commitment_alg``.

    FT-03 gate order (``RECOMMIT_GATE_ORDER``, fail-closed first-failing):

    1. ``clearance-tenant-domain`` — the FULL §4.2 clearance gate
       (:func:`~kailash.trust.vault.clearance.evaluate_clearance`) for the
       recommit capability ``vault:backup``: the binding-OWNED CL-02a
       tenant→domain→token fail-closed scoping against the RESOLVED vault
       tenant/domain (the substrate gate is domain-blind) PLUS the N12-CL-04
       cooling-off suspension — ``vault:backup`` is a cooling-off-suspended
       capability, so a principal inside the 7-day post-recovery window cannot
       recommit without a verified governance-approver. Any failure →
       ``missing-clearance``. A cheap presence-only check
       (:func:`~kailash.trust.vault.input_gates.require_clearance`) runs BEFORE
       resolution so a token-less caller is denied without materializing the
       secret (same ``missing-clearance`` code).
    2. ``generation-vault-unchanged`` — the recommit MUST NOT alter
       ``kek_generation`` or ``vault_id`` (it operates on the resolved handle's
       own generation/vault) else ``recommit-generation-altered``;
    3. ``prior-commitment-exists`` — a LIVE (non-retired) registry entry MUST
       exist for ``(vault_id, gen)`` under ``prior_kek_commitment_alg`` whose
       commitment equals ``prior_kek_identity_commitment`` else
       ``unknown-prior-commitment``;
    4. ``new-commitment-binds-secret`` — the recomputed ``C_Y`` over the
       reconstructed secret under ``new_kek_commitment_alg`` MUST bind the SAME
       secret + same ``(vault_id, kek_generation)`` else
       ``recommit-binding-mismatch``.

    AU-02b: the ``vault_kek_recommit`` anchor is dispatched to the ``recovery``
    tier (the receipt is the HARD precondition) BEFORE the new entry is
    registered. A dispatch failure RAISES and the registry is never mutated.

    Args:
        key_handle: The target KEK handle; resolved internally for the
            generation + secret. Its ``vault_id`` / ``kek_generation`` are the
            ones the recommit binds to (and MUST NOT alter).
        clearance: The bound authorization context; MUST carry ``vault:backup``.
        resolver: The injected trusted-module resolver (consume-and-``del``).
        dispatcher: The named-tier audit dispatcher (D1).
        signer / signer_identity: The anchor signer + identity.
        alg_id: The deployment SLIP-0039 algorithm id (rides
            ``event_payload.alg_id``).
        prior_kek_commitment_alg / prior_kek_identity_commitment: The from-side
            of the migration; MUST name a live registry entry.
        new_kek_commitment_alg: The to-side commitment-registry token; ``C_Y``
            is computed under this algorithm.
        registry: The per-(vault_id, gen) registry to extend; the process
            default when omitted.
        timestamp / time_attested: N12-AU-04a two-state grammar.
        principal: The acting principal; defaults to ``clearance.principal``.
        posture_store: The PostureStore the CL-04 cooling-off read consults
            (``None`` → no-receipt conservative default: not suspended).
        trust_anchored_now: The trust-anchored clock the CL-04 window is
            evaluated against (NEVER a locally-mutable wall clock).
        approver_configured: The X1 CL-03 seam — recorded on a cooling-off
            denial for audit; a configured-but-unexercised approver does NOT by
            itself lift the suspension.

    Returns:
        The newly-registered live :class:`CommitmentEntry` for
        ``new_kek_commitment_alg`` (``retired=False``).

    Raises:
        VaultBindingError: any gate fails (``missing-clearance`` /
            ``recommit-generation-altered`` / ``unknown-prior-commitment`` /
            ``recommit-binding-mismatch``), or the audit dispatch fails (AU-02b).
    """
    acting_principal = principal if principal is not None else clearance.principal
    active_registry = (
        registry if registry is not None else default_commitment_registry()
    )
    vault_id = key_handle.vault_id
    kek_generation = key_handle.kek_generation

    logger.info(
        "vault.recommit.start",
        extra={
            "vault_id": vault_id,
            "kek_generation": kek_generation,
            "prior_kek_commitment_alg": prior_kek_commitment_alg,
            "new_kek_commitment_alg": new_kek_commitment_alg,
            "principal": acting_principal,
        },
    )

    # Gate 1 (cheap presence-only) — vault:backup token check BEFORE resolution
    # (mirror the backup/rotation gate-1-cheap): a token-less caller is denied
    # without materializing the KEK secret. Same missing-clearance code as the
    # full gate below, so the first-failing determinism is preserved.
    require_clearance(clearance, BACKUP_CAPABILITY)

    # Resolve the KEK inside the trusted module; consumed for the binding check
    # and the CL-02a tenant/domain read, then del-ed in the finally (N12-IN-05).
    resolved = resolver.resolve_kek(key_handle)
    if not isinstance(resolved, ResolvedKek):
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            "resolver.resolve_kek MUST return a ResolvedKek; got "
            f"{type(resolved).__name__}",
            details={"returned_type": type(resolved).__name__},
        )

    try:
        new_commitment_box: list[str] = []

        def check(gate: str) -> Optional[N12FT01Code]:
            """The FT-03 recommit per-gate predicate (steps 1-4)."""
            if gate == "clearance-tenant-domain":
                # (1) The FULL §4.2 clearance gate for the recommit capability
                # vault:backup: binding-OWNED CL-02a tenant→domain→token
                # fail-closed scoping against the RESOLVED vault tenant/domain
                # (the substrate gate is domain-blind) + N12-CL-04 cooling-off
                # suspension (vault:backup IS a suspended capability, so a
                # principal inside the 7-day post-recovery window is suspended).
                # A vault:backup granted in tenant/domain A fails against this
                # vault in tenant/domain B. evaluate_clearance raises on failure;
                # translate to the typed code for first_failing (preserves the
                # missing-clearance first-failing determinism, N12-FT-03).
                try:
                    evaluate_clearance(
                        clearance,
                        resolved,
                        BACKUP_CAPABILITY,
                        posture_store=posture_store,
                        now=trust_anchored_now,
                        approver_configured=approver_configured,
                    )
                except VaultBindingError as exc:
                    return exc.code
                return None
            if gate == "generation-vault-unchanged":
                # (2) The recommit MUST NOT alter kek_generation / vault_id. We
                # operate on the resolved handle's OWN generation; a divergence
                # between the handle's captured generation and the resolver's
                # resolved generation is an altered-generation attempt.
                if resolved.kek_generation != kek_generation:
                    return N12FT01Code.RECOMMIT_GENERATION_ALTERED
                return None
            if gate == "prior-commitment-exists":
                # (3) A LIVE entry MUST exist under prior_kek_commitment_alg whose
                # commitment equals prior_kek_identity_commitment.
                lookup = active_registry.lookup(
                    vault_id=vault_id,
                    kek_generation=kek_generation,
                    kek_commitment_alg=prior_kek_commitment_alg,
                )
                prior_entry = lookup.entry
                if (
                    prior_entry is None
                    or prior_entry.retired
                    or prior_entry.commitment != prior_kek_identity_commitment
                ):
                    return N12FT01Code.UNKNOWN_PRIOR_COMMITMENT
                return None
            if gate == "new-commitment-binds-secret":
                # (4) Compute C_Y under new_kek_commitment_alg over the resolved
                # secret + same (vault_id, kek_generation) and constant-time
                # verify it binds that secret. Reuses C1's verify_commitment
                # (hmac.compare_digest) against a freshly-computed C_Y so the
                # bind check is a real recompute, never a trusted caller value.
                from kailash.trust.vault.commitment import kek_identity_commitment

                c_y = kek_identity_commitment(
                    vault_id=vault_id,
                    kek_generation=kek_generation,
                    master_secret=resolved.master_secret,
                    passphrase_provenance=resolved.passphrase_provenance,
                    alg=new_kek_commitment_alg,
                )
                ok = verify_commitment(
                    expected_commitment=c_y,
                    vault_id=vault_id,
                    kek_generation=kek_generation,
                    master_secret=resolved.master_secret,
                    passphrase_provenance=resolved.passphrase_provenance,
                    alg=new_kek_commitment_alg,
                )
                if not ok:
                    return N12FT01Code.RECOMMIT_BINDING_MISMATCH
                new_commitment_box.append(c_y)
                return None
            raise VaultBindingError(
                N12FT01Code.PARAMETER_MISMATCH,
                f"recommit gate {gate!r} is not a recognized FT-03 gate "
                f"(closed order: {list(RECOMMIT_GATE_ORDER)})",
                details={"gate": gate},
            )

        first = first_failing(RECOMMIT_GATE_ORDER, check)
        if first is not None:
            logger.warning(
                "vault.recommit.gate_failed",
                extra={
                    "vault_id": vault_id,
                    "kek_generation": kek_generation,
                    "gate_code": first.value,
                },
            )
            raise VaultBindingError(
                first,
                f"recommit gate failed: {first.value} (vault_id={vault_id})",
                details={"gate_code": first.value, "vault_id": vault_id},
            )

        new_commitment = new_commitment_box[0]

        # The new entry inherits the prior live entry's key_id (N12-IN-04: the
        # recommit binds the SAME key, so the same key_id; key_id is NOT in the
        # §12.2 commitment pre-image — it is bound at THIS registry layer).
        prior_entry = active_registry.lookup(
            vault_id=vault_id,
            kek_generation=kek_generation,
            kek_commitment_alg=prior_kek_commitment_alg,
        ).entry
        # prior_entry is guaranteed live + non-None here (gate 3 passed).
        new_key_id = prior_entry.key_id  # type: ignore[union-attr]

        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        payload = build_kek_recommit_anchor(
            alg_id=alg_id,
            vault_id=vault_id,
            kek_generation=kek_generation,
            prior_kek_commitment_alg=prior_kek_commitment_alg,
            prior_kek_identity_commitment=prior_kek_identity_commitment,
            new_kek_commitment_alg=new_kek_commitment_alg,
            new_kek_identity_commitment=new_commitment,
            principal=acting_principal,
            timestamp=ts,
            time_attested=time_attested,
        )

        # AU-02b: dispatch the OUTCOME anchor to the recovery tier BEFORE the
        # registry mutation. A dispatch failure RAISES here (no receipt) and the
        # new entry is never registered — the registry mirrors the audited chain.
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.RECOVERY,
        )

        # ADDITIVE register: adds the new-alg sibling entry WITHOUT deleting the
        # prior (CommitmentRegistry.register is additive — a new alg under the
        # same (vault_id, gen) is a sibling). Both C_X and C_Y are now live.
        new_entry = active_registry.register(
            vault_id=vault_id,
            kek_generation=kek_generation,
            kek_commitment_alg=new_kek_commitment_alg,
            commitment=new_commitment,
            key_id=new_key_id,
        )
        logger.info(
            "vault.recommit.ok",
            extra={
                "vault_id": vault_id,
                "kek_generation": kek_generation,
                "new_kek_commitment_alg": new_kek_commitment_alg,
                "live_algs": list(
                    active_registry.live_algs(
                        vault_id=vault_id, kek_generation=kek_generation
                    )
                ),
            },
        )
        return new_entry
    finally:
        # N12-IN-05: consume-and-del the resolved KEK material on every exit.
        resolved.zeroize()


def retire_vault_kek_alg(
    key_handle: VaultKeyHandle,
    clearance: ClearanceContext,
    *,
    resolver: VaultKeyResolver,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    alg_id: str,
    retired_kek_commitment_alg: str,
    retired_kek_identity_commitment: str,
    registry: Optional[CommitmentRegistry] = None,
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    principal: Optional[str] = None,
    posture_store: Optional[PostureStore] = None,
    trust_anchored_now: Optional[datetime] = None,
    approver_configured: bool = False,
) -> CommitmentEntry:
    """Retire a specific commitment-registry entry as non-verifiable (N12-CB-04(e)).

    Marks the ``(retired_kek_commitment_alg -> retired_kek_identity_commitment)``
    entry for ``(key_handle.vault_id, key_handle.kek_generation)`` ``retired=True``
    by REPLACING it with a new frozen :class:`CommitmentEntry` (registry entries
    are additive/immutable — the retire produces a new entry, never mutates in
    place). The restore commitment-auth gate reads ``entry.retired`` and maps a
    retired entry to ``retired-commitment-alg`` (distinct from
    ``kek-commitment-mismatch`` / ``commitment-alg-mismatch``).

    FT-03 gate order (``RETIRE_GATE_ORDER``, fail-closed first-failing):

    1. ``clearance-tenant-domain`` — the FULL §4.2 clearance gate
       (:func:`~kailash.trust.vault.clearance.evaluate_clearance`) for the
       DISTINCT high-consequence ``vault:retire-alg`` capability (NOT
       ``vault:restore`` / ``vault:backup``): the binding-OWNED CL-02a
       tenant→domain→token fail-closed scoping against the RESOLVED vault
       tenant/domain (the handle carries no tenant/domain — the resolver is the
       only trusted-module source). N12-CL-04 cooling-off is a structural no-op
       here: ``vault:retire-alg`` is NOT in
       :data:`~kailash.trust.vault.clearance.COOLING_OFF_SUSPENDED_CAPABILITIES`,
       so a retire is never suspended by the post-recovery window (spec-faithful;
       retire is not a materializing-restore-class op). Any failure →
       ``missing-clearance``. A cheap presence-only check
       (:func:`~kailash.trust.vault.input_gates.require_clearance`) runs BEFORE
       resolution so a token-less caller is denied without materializing the
       secret (same ``missing-clearance`` code).
    2. ``generation-vault-unchanged`` — the retire MUST NOT alter
       ``kek_generation`` or ``vault_id`` else ``recommit-generation-altered``;
    3. ``retired-entry-exists`` — a LIVE (non-retired) registry entry MUST exist
       under ``retired_kek_commitment_alg`` whose commitment equals
       ``retired_kek_identity_commitment`` else ``unknown-prior-commitment``;
    4. ``recoverability-preserved`` — a LIVE non-retired commitment ``C_Y`` for
       the SAME ``(vault_id, kek_generation)`` under a DIFFERENT algorithm MUST
       already exist (the corpus is recoverable after the retire) else a
       ``missing-clearance``-class refusal (N12-CB-04(e)(4) — retirement MUST
       NOT strand the corpus).

    AU-02b: the ``vault_kek_retire`` anchor is dispatched to the ``recovery``
    tier BEFORE the registry entry is replaced. A dispatch failure RAISES and
    the entry stays live. The resolve + gate machinery + AU-02b dispatch +
    registry mutation are wrapped in a ``try`` / ``finally`` that ``zeroize()``-s
    the resolved KEK on EVERY exit (N12-IN-05), preserving the anchor-before-
    mutation ordering.

    Args:
        key_handle: The target KEK handle (vault_id + generation). Retire
            resolves it via ``resolver`` to source the trusted vault
            tenant/domain for the CL-02a clearance scoping — the handle itself
            carries no tenant/domain (``VaultKeyHandle`` has only key_id /
            vault_id / kek_generation), so the resolver is the ONLY trusted-
            module source. The materialized secret is consumed only to read the
            trusted tenant/domain and ``zeroize()``-d in the ``finally``; it
            never crosses a return value, anchor payload, or log line (N12-IN-05).
        clearance: MUST carry ``vault:retire-alg`` (N12-CB-04(e)(2)).
        resolver: The injected trusted-module resolver — the trusted source of
            the vault's tenant/domain for the CL-02a scoping (consume-and-
            ``zeroize``).
        dispatcher: The named-tier audit dispatcher (D1).
        signer / signer_identity: The anchor signer + identity.
        alg_id: The deployment SLIP-0039 algorithm id (rides
            ``event_payload.alg_id``).
        retired_kek_commitment_alg / retired_kek_identity_commitment: The entry
            to retire; MUST name a live registry entry.
        registry: The per-(vault_id, gen) registry; the process default when
            omitted.
        timestamp / time_attested: N12-AU-04a two-state grammar.
        principal: The acting principal; defaults to ``clearance.principal``.
        posture_store: The PostureStore the CL-04 cooling-off read consults
            (``None`` → no-receipt conservative default). CL-04 is a structural
            no-op for ``vault:retire-alg`` (not a suspended capability) — this
            is threaded for signature symmetry with recommit + future-proofing.
        trust_anchored_now: The trust-anchored clock for the CL-04 window
            (NEVER a locally-mutable wall clock).
        approver_configured: The X1 CL-03 seam (recorded on a denial for audit).

    Returns:
        The new retired :class:`CommitmentEntry` (``retired=True``).

    Raises:
        VaultBindingError: any gate fails (``missing-clearance`` /
            ``recommit-generation-altered`` / ``unknown-prior-commitment`` /
            recoverability refusal), or the audit dispatch fails (AU-02b).
    """
    acting_principal = principal if principal is not None else clearance.principal
    active_registry = (
        registry if registry is not None else default_commitment_registry()
    )
    vault_id = key_handle.vault_id
    kek_generation = key_handle.kek_generation

    logger.info(
        "vault.retire.start",
        extra={
            "vault_id": vault_id,
            "kek_generation": kek_generation,
            "retired_kek_commitment_alg": retired_kek_commitment_alg,
            "principal": acting_principal,
        },
    )

    # Gate 1 (cheap presence-only) — vault:retire-alg token check BEFORE
    # resolution: a token-less caller is denied without materializing the KEK
    # secret. Same missing-clearance code as the full gate below, so the
    # first-failing determinism is preserved.
    require_clearance(clearance, RETIRE_ALG_CAPABILITY)

    # Resolve the KEK inside the trusted module — the ONLY trusted-module source
    # of the vault's tenant/domain for the CL-02a scoping (the handle carries
    # none). The secret is materialized solely to read the trusted tenant/domain
    # and zeroize()-d in the finally on EVERY exit (N12-IN-05); it never crosses
    # a return value, anchor payload, or log line.
    resolved = resolver.resolve_kek(key_handle)
    if not isinstance(resolved, ResolvedKek):
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            "resolver.resolve_kek MUST return a ResolvedKek; got "
            f"{type(resolved).__name__}",
            details={"returned_type": type(resolved).__name__},
        )

    try:

        def check(gate: str) -> Optional[N12FT01Code]:
            """The FT-03 retire per-gate predicate (steps 1-4)."""
            if gate == "clearance-tenant-domain":
                # (1) The FULL §4.2 clearance gate for the DISTINCT
                # vault:retire-alg capability (N12-CB-04(e)(2)) — NOT the
                # ordinary vault:restore / vault:backup capability. Runs the
                # binding-OWNED CL-02a tenant→domain→token fail-closed scoping
                # against the RESOLVED vault tenant/domain (the resolver is the
                # only trusted-module source; the handle carries no
                # tenant/domain). A vault:retire-alg holder in tenant/domain A
                # is denied against this vault in tenant/domain B even with a
                # live recoverability sibling alg present.
                #
                # CL-04 cooling-off is a STRUCTURAL no-op here: vault:retire-alg
                # is NOT in COOLING_OFF_SUSPENDED_CAPABILITIES (it is not a
                # materializing-restore-class op), so is_in_cooling_off is never
                # consulted for it — a principal inside the 7-day post-recovery
                # window is NOT suspended for a retire. This is spec-faithful;
                # we do NOT force-suspend retire.
                #
                # evaluate_clearance raises on failure; translate to the typed
                # code for first_failing (preserves the missing-clearance
                # first-failing determinism, N12-FT-03).
                try:
                    evaluate_clearance(
                        clearance,
                        resolved,
                        RETIRE_ALG_CAPABILITY,
                        posture_store=posture_store,
                        now=trust_anchored_now,
                        approver_configured=approver_configured,
                    )
                except VaultBindingError as exc:
                    return exc.code
                return None
            if gate == "generation-vault-unchanged":
                # (2) Retire MUST NOT alter generation/vault. The handle carries
                # the captured generation; a negative generation would have been
                # rejected at VaultKeyHandle construction, so this gate is
                # structurally a no-op on a well-formed handle, BUT it stays in
                # the order so the first-failing sequence matches the recommit
                # path + the spec FT-03 ordering. (A later C3 ordinal-generation
                # surface may strengthen it.)
                if kek_generation != key_handle.kek_generation:  # pragma: no cover
                    return N12FT01Code.RECOMMIT_GENERATION_ALTERED
                return None
            if gate == "retired-entry-exists":
                # (3) A LIVE entry MUST exist under retired_kek_commitment_alg
                # whose commitment equals retired_kek_identity_commitment.
                lookup = active_registry.lookup(
                    vault_id=vault_id,
                    kek_generation=kek_generation,
                    kek_commitment_alg=retired_kek_commitment_alg,
                )
                target_entry = lookup.entry
                if (
                    target_entry is None
                    or target_entry.retired
                    or target_entry.commitment != retired_kek_identity_commitment
                ):
                    return N12FT01Code.UNKNOWN_PRIOR_COMMITMENT
                return None
            if gate == "recoverability-preserved":
                # (4) Recoverability guard (N12-CB-04(e)(4)): a LIVE non-retired
                # commitment C_Y for the SAME (vault_id, gen) under a DIFFERENT
                # alg MUST already exist, so the retire does NOT strand the
                # corpus. The live_algs() growth metric is the source of truth:
                # after removing the alg about to be retired, at least one OTHER
                # live alg MUST remain. Refused with a missing-clearance-class
                # VaultBindingError (the spec's "missing-clearance-class rejection,
                # never stranding recoverability"). UNCHANGED by #630.
                live = set(
                    active_registry.live_algs(
                        vault_id=vault_id, kek_generation=kek_generation
                    )
                )
                live.discard(retired_kek_commitment_alg)
                if not live:
                    return N12FT01Code.MISSING_CLEARANCE
                return None
            raise VaultBindingError(
                N12FT01Code.PARAMETER_MISMATCH,
                f"retire gate {gate!r} is not a recognized FT-03 gate "
                f"(closed order: {list(RETIRE_GATE_ORDER)})",
                details={"gate": gate},
            )

        first = first_failing(RETIRE_GATE_ORDER, check)
        if first is not None:
            logger.warning(
                "vault.retire.gate_failed",
                extra={
                    "vault_id": vault_id,
                    "kek_generation": kek_generation,
                    "gate_code": first.value,
                },
            )
            raise VaultBindingError(
                first,
                f"retire gate failed: {first.value} (vault_id={vault_id})",
                details={"gate_code": first.value, "vault_id": vault_id},
            )

        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        payload = build_kek_retire_anchor(
            alg_id=alg_id,
            vault_id=vault_id,
            kek_generation=kek_generation,
            retired_kek_commitment_alg=retired_kek_commitment_alg,
            retired_kek_identity_commitment=retired_kek_identity_commitment,
            principal=acting_principal,
            timestamp=ts,
            time_attested=time_attested,
        )

        # AU-02b: dispatch the OUTCOME anchor to the recovery tier BEFORE
        # replacing the registry entry. A dispatch failure RAISES (no receipt)
        # and the entry stays live — the registry mirrors the audited recovery-
        # tier chain. The resolve/zeroize try/finally WRAPS this dispatch +
        # mutation so the anchor-before-mutation ordering is preserved and the
        # secret is always zeroized on every exit (N12-IN-05).
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.RECOVERY,
        )

        # Replace the entry with a new frozen retired one (entries are immutable
        # — the retire produces a NEW CommitmentEntry, never mutates in place).
        # The commitment + key_id carry through verbatim; only `retired` flips.
        retired_entry = _mark_entry_retired(
            active_registry,
            vault_id=vault_id,
            kek_generation=kek_generation,
            kek_commitment_alg=retired_kek_commitment_alg,
        )
        logger.info(
            "vault.retire.ok",
            extra={
                "vault_id": vault_id,
                "kek_generation": kek_generation,
                "retired_kek_commitment_alg": retired_kek_commitment_alg,
                "live_algs": list(
                    active_registry.live_algs(
                        vault_id=vault_id, kek_generation=kek_generation
                    )
                ),
            },
        )
        return retired_entry
    finally:
        # N12-IN-05: consume-and-zeroize the resolved KEK material on every exit.
        resolved.zeroize()


def _mark_entry_retired(
    registry: CommitmentRegistry,
    *,
    vault_id: str,
    kek_generation: int,
    kek_commitment_alg: str,
) -> CommitmentEntry:
    """Replace ``(vault_id, gen, alg)``'s entry with a ``retired=True`` clone.

    Registry entries are additive/immutable frozen DTOs — the retire produces a
    NEW :class:`CommitmentEntry` carrying the same ``commitment`` + ``key_id``
    with ``retired=True`` and installs it in the per-(vault_id, gen) algorithm
    map, replacing the live entry under the same algorithm key. The caller has
    already verified (gate 3) that a live entry exists, so the slot is present.

    This is the single write into the C2a registry's private store the retire
    path performs; it is fail-closed (a missing slot is structurally impossible
    after gate 3 but raises rather than silently no-op).
    """
    slot = registry._store.get((vault_id, kek_generation))
    if slot is None or kek_commitment_alg not in slot:  # pragma: no cover
        raise VaultBindingError(
            N12FT01Code.UNKNOWN_PRIOR_COMMITMENT,
            "retire reached the registry write with no live entry for "
            f"(vault_id={vault_id!r}, kek_generation={kek_generation}) under "
            f"alg {kek_commitment_alg!r}; fail-closed (gate 3 should have caught "
            "this)",
            details={
                "vault_id": vault_id,
                "kek_generation": kek_generation,
                "kek_commitment_alg": kek_commitment_alg,
            },
        )
    live = slot[kek_commitment_alg]
    retired_entry = CommitmentEntry(
        commitment=live.commitment,
        key_id=live.key_id,
        retired=True,
    )
    slot[kek_commitment_alg] = retired_entry
    return retired_entry
