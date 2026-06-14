# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 rotation trigger (§5 / R1 / Wave 5).

This module binds the **shipped** ``shamir.rotate_holders`` wrapper to the
EATP-12 authority + audit surface. It does NOT redefine the wrapper's
reconstruction-then-regeneration behavior — it COMPOSES it (N12-RT-01). Two
public surfaces:

* :func:`rotate_vault_holders` — **amicable** holder rotation (N12-RT-01/02/03,
  Mode-A-only per N12-RT-04). A holder departs amicably; the vault re-shards
  the SAME master secret under a new ritual. The ``kek_generation`` is
  **unchanged** (only the shard distribution changes, §5.1). Writes a
  ``vault_holder_rotation`` anchor carrying ``for_cause=False``.

* :func:`revoke_holder_for_cause` — **for-cause** revocation (N12-SH-04 /
  N12-RT-06). A holder is revoked for cause (suspected compromise). At
  Conformant level a departed holder still holds a cryptographically valid
  **current-generation** shard of the unchanged master secret, and a holder
  rotation does NOT advance the generation — so neither an identifier check nor
  attribution can cryptographically distinguish the retained shard from a
  legitimate one (N12-SH-04, F-AUTHZ-5/F-CRYPTO-8). The honest defense is
  **generation-supersession**: the binding escalates the revocation to a
  generation-advancing KEK-rotation (§5.2) that advances ``kek_generation`` to
  ``g+1`` so the departed holder's retained ``g`` shards become **stale**
  (refused by the §6 stale-generation guard, N12-SG-02). It emits a SINGLE
  ``vault_kek_rotation`` anchor carrying ``for_cause=True`` AND the new
  ``g+1`` re-shard distribution, so the ``for_cause`` flag lands on the anchor
  that actually advances the generation (fix [4]) and N12-CB-03's foreign-shard
  check has a ``g+1`` source immediately (no two-anchor split).

**The current generation is sourced from the audited chain, not a mutable
counter (N12-RT-06).** :func:`revoke_holder_for_cause` derives the prior
generation via :func:`~kailash.trust.vault.stale_guard.current_generation_from_chain`
— the SAME source the C3 stale-guard reads — then writes the ``g+1`` rotation
anchor that becomes the new chain high-water. This is what makes C3's
ordinal-generation gate LIVE: R1 WRITES the ``vault_kek_rotation`` anchors C3
READS (RT-06).

**Composition, not reimplementation (N12-RT-01):** both surfaces call the
shipped :func:`~kailash.trust.vault.shamir.rotate_holders` to recombine the
``old_shards`` and re-shard under ``new_ritual``. The for-cause k-floor check
calls the shipped :func:`~kailash.trust.vault.holder_registry.check_revocation_k_floor`
(N12-SH-03, B2) — it does NOT reimplement a parallel k-floor check.

**Rotation does NOT trigger D6.** N12-RT-05 scopes the post-recovery posture
downgrade to ``restore_vault_key`` (a KEK-materializing *recovery*); an
authorized administrative re-shard is not a recovery and does not start a
cooling-off window. (The internal reconstruct the wrapper performs is the
re-shard mechanism, not a recovery materialization.)

**Rotation-denial audit gap (documented, cross-SDK reconciliation item).** The
§4.5 closed denial-subtype set (N12-AU-03 / D2 "no new enum strings") defines
only ``vault_key_backup_denied`` and ``vault_key_restore_denied`` — there is NO
``vault_*_rotation_denied`` subtype. A rotation gate-failure therefore RAISES
the typed :class:`~kailash.trust.vault.errors.VaultBindingError` and emits a
structured WARN log (observable), but does NOT dispatch a denial anchor —
inventing a non-spec subtype would violate the closed-subtype discriminator the
V6 golden-fixture pre-image is defined over. Whether the spec intends a
rotation-denial subtype is reconciled at the cross-SDK gate (XSDK-3) against
kailash-rs (#1316).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Sequence

from kailash.delegate.types import DelegateIdentity
from kailash.trust.posture.postures import PostureStore
from kailash.trust.vault.anchors import (
    build_holder_rotation_anchor,
    build_kek_rotation_anchor,
)
from kailash.trust.vault.backup import (
    DEFAULT_ITERATION_EXPONENT,
    AnchorSigner,
    _shard_commitment,
    _sign_and_dispatch,
)
from kailash.trust.vault.clearance import ROTATE_CAPABILITY, evaluate_clearance
from kailash.trust.vault.commitment import (
    DEFAULT_KEK_COMMITMENT_ALG,
    kek_identity_commitment,
)
from kailash.trust.vault.dispatch import AuditDispatcher, AuditTier
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.holder_registry import (
    HolderRegistry,
    check_revocation_k_floor,
    default_holder_registry,
    require_registered_holders,
)
from kailash.trust.vault.input_gates import (
    ResolvedKek,
    VaultKeyResolver,
    master_secret_bits,
    require_clearance,
    require_kek_class,
    require_ritual_floor,
)
from kailash.trust.vault.registry import CommitmentRegistry, default_commitment_registry
from kailash.trust.vault.shamir import ShamirRitual, rotate_holders
from kailash.trust.vault.stale_guard import current_generation_from_chain
from kailash.trust.vault.types import ClearanceContext, RotationReceipt, VaultKeyHandle

logger = logging.getLogger(__name__)

__all__ = [
    "rotate_vault_holders",
    "revoke_holder_for_cause",
]


def _resolved_or_raise(
    resolver: VaultKeyResolver, key_handle: VaultKeyHandle
) -> ResolvedKek:
    """Resolve the KEK inside the trusted module; fail-closed on a non-ResolvedKek.

    Mirrors ``back_up_vault_key``'s resolver guard: a resolver returning
    anything but a :class:`ResolvedKek` is treated as ``not-a-kek`` (unknown →
    deny), so a misconfigured resolver never silently proceeds.
    """
    resolved = resolver.resolve_kek(key_handle)
    if not isinstance(resolved, ResolvedKek):
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            "resolver.resolve_kek MUST return a ResolvedKek; got "
            f"{type(resolved).__name__}",
            details={"returned_type": type(resolved).__name__},
        )
    return resolved


def rotate_vault_holders(
    key_handle: VaultKeyHandle,
    old_shards: Sequence[Sequence[str]],
    old_ritual: ShamirRitual,
    new_ritual: ShamirRitual,
    clearance: ClearanceContext,
    new_holders: Sequence[str],
    departing_holder: str,
    *,
    resolver: VaultKeyResolver,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    alg_id: str,
    holder_registry: Optional[HolderRegistry] = None,
    posture_store: Optional[PostureStore] = None,
    passphrase: bytes = b"",
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    trust_anchored_now: Optional[datetime] = None,
    approver_configured: bool = False,
    principal: Optional[str] = None,
) -> RotationReceipt:
    """Amicable holder rotation (N12-RT-01/02/03/04) — re-shard, generation UNCHANGED.

    Composes the shipped :func:`~kailash.trust.vault.shamir.rotate_holders`
    (NO reimplementation, N12-RT-01) to recombine ``old_shards`` and regenerate
    ``new_ritual.total_shards`` shards under the new ``(k, n)``. The
    ``kek_generation`` does NOT advance (the master secret is unchanged; only
    the shard distribution changes — §5.1 / N12-RT-03). Writes a
    ``vault_holder_rotation`` anchor with ``for_cause=False`` to the ``recovery``
    tier (mediated, fail-closed per N12-AU-02b).

    Gate order (fail-closed; a gate failure RAISES typed + WARN-logs, no denial
    anchor — see module docstring):

    1. clearance presence (CL-01) — ``vault:rotate`` else ``missing-clearance``;
    2. ritual floor (N12-TH-01) — ``new_ritual`` satisfies ``2<=k<=n<=9``;
    3. new holders registry-registered (N12-SH-01) else ``unregistered-holder``;
    4. resolve KEK → ``key_class==KEK`` else ``not-a-kek`` (N12-IN-02);
    5. full clearance (CL-02a tenant→domain→token + CL-04 cooling-off) against
       the resolved vault tenant/domain — ``vault:rotate`` is a cooling-off
       suspended capability, so a principal inside the 7-day post-recovery
       window cannot rotate.

    Then: ``rotate_holders`` → new ``shard_commitments`` → ``vault_holder_rotation``
    anchor → sign + dispatch (AU-02b receipt-or-abort) → ``RotationReceipt``.
    NO new commitment is registered: the commitment binds the unchanged
    ``(vault_id, generation, secret, provenance)`` so the already-registered
    commitment still verifies.

    Mode-A only (N12-RT-04): ``new_ritual`` is a single-group ``(k, n)`` ritual;
    this binding MUST NOT claim Mode-B (multi-group) conformance — the shipped
    wrapper is single-group (``group_threshold=1``).

    Args:
        key_handle: The opaque KEK handle (resolved internally for tenant/domain
            + current generation; the master secret is NOT used for the amicable
            anchor — the commitment is unchanged).
        old_shards: EXACTLY ``old_ritual.threshold`` shards from the current
            ritual (holder-supplied consent + reconstruction input). The shipped
            ``shamir.reconstruct`` requires exactly ``threshold`` mnemonics, not
            ``n`` — supplying more raises ``MnemonicError``.
        old_ritual: The current ``(k, n)`` ritual (recorded as the anchor's
            ``old`` params).
        new_ritual: The post-rotation ``(k, n)`` ritual; MUST satisfy the floor.
        clearance: The bound authorization context; MUST carry ``vault:rotate``.
        new_holders: The ordered post-rotation holder-id distribution.
        departing_holder: The amicably-departing holder id (recorded on the
            anchor).
        resolver: The injected trusted-module resolver.
        dispatcher: The named-tier audit dispatcher (D1).
        signer / signer_identity: The anchor signer + signing identity.
        alg_id: The deployment SLIP-0039 algorithm id (rides ``event_payload``).
        holder_registry: The deployment holder registry the new distribution is
            checked against (process default when omitted).
        posture_store: The PostureStore the CL-04 cooling-off read consults.
        passphrase: The SLIP-0039 passphrase for ``old_shards`` (re-emitted shards
            use the same passphrase per the wrapper default; NEVER logged).
        timestamp / time_attested: The trust-anchored-timestamp grammar
            (N12-AU-04a); ``"unverified"`` sentinel when not attested.
        trust_anchored_now: The trust-anchored clock the CL-04 window is
            evaluated against (NEVER a locally-mutable wall clock).
        approver_configured: The X1 CL-03 seam (until CL-03 lands a suspended op
            rejects fail-closed regardless).
        principal: The acting principal; defaults to ``clearance.principal``.

    Returns:
        A :class:`~kailash.trust.vault.types.RotationReceipt` (``for_cause=False``,
        ``kek_generation == prior_kek_generation``).

    Raises:
        VaultBindingError: any gate fails (``missing-clearance`` /
            ``invalid-ritual`` / ``unregistered-holder`` / ``not-a-kek``), or the
            audit dispatch fails (no receipt → abort, AU-02b).
    """
    acting_principal = principal if principal is not None else clearance.principal

    # Gate 1 — clearance presence (cheap token check, no resolution needed).
    try:
        require_clearance(clearance, ROTATE_CAPABILITY)
    except VaultBindingError:
        logger.warning(
            "vault.rotate.denied",
            extra={
                "phase": "clearance-presence",
                "principal": acting_principal,
                "required_capability": ROTATE_CAPABILITY,
                "vault_id": key_handle.vault_id,
            },
        )
        raise

    # Gate 2 — ritual floor on the NEW ritual (N12-TH-01), BEFORE resolution.
    require_ritual_floor(new_ritual)

    # Gate 3 — the new holder distribution MUST be registry-registered (N12-SH-01).
    active_holder_registry = (
        holder_registry if holder_registry is not None else default_holder_registry()
    )
    holder_ids = require_registered_holders(new_holders, active_holder_registry)

    # Gate 4 — resolve KEK inside the trusted module (for tenant/domain + gen).
    resolved = _resolved_or_raise(resolver, key_handle)
    try:
        require_kek_class(resolved)

        # Gate 5 — full clearance (CL-02a tenant→domain→token + CL-04 cooling-off)
        # against the RESOLVED vault tenant/domain, BEFORE any re-shard.
        try:
            evaluate_clearance(
                clearance,
                resolved,
                ROTATE_CAPABILITY,
                posture_store=posture_store,
                now=trust_anchored_now,
                approver_configured=approver_configured,
            )
        except VaultBindingError:
            logger.warning(
                "vault.rotate.denied",
                extra={
                    "phase": "scope-or-cooling-off",
                    "principal": acting_principal,
                    "required_capability": ROTATE_CAPABILITY,
                    "vault_id": key_handle.vault_id,
                },
            )
            raise

        logger.info(
            "vault.rotate.holder.start",
            extra={
                "vault_id": key_handle.vault_id,
                "departing_holder": departing_holder,
                "old_k": old_ritual.threshold,
                "old_n": old_ritual.total_shards,
                "new_k": new_ritual.threshold,
                "new_n": new_ritual.total_shards,
                "principal": acting_principal,
            },
        )

        # Compose the shipped wrapper — recombine old_shards + re-shard under the
        # new ritual (N12-RT-01; NO reimplementation). The new shards never leave
        # the trusted module; only their per-shard ciphertext COMMITMENTS
        # (N12-CB-03) cross the boundary (one-way, no secret).
        new_shards = rotate_holders(
            [list(s) for s in old_shards], new_ritual, passphrase=passphrase
        )
        try:
            shard_commitments = [_shard_commitment(s) for s in new_shards]
        finally:
            del new_shards

        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        payload = build_holder_rotation_anchor(
            alg_id=alg_id,
            old_k=old_ritual.threshold,
            old_n=old_ritual.total_shards,
            new_k=new_ritual.threshold,
            new_n=new_ritual.total_shards,
            departing_holder=departing_holder,
            holders=holder_ids,
            vault_id=key_handle.vault_id,
            kek_generation=resolved.kek_generation,  # UNCHANGED (N12-RT-03)
            shard_commitments=shard_commitments,
            for_cause=False,  # amicable (N12-RT-02; for-cause escalates to KEK rotation)
            principal=acting_principal,
            timestamp=ts,
            time_attested=time_attested,
        )

        # AU-02b: sign + dispatch to recovery; the receipt is the HARD precondition
        # for returning. A dispatch failure RAISES (no receipt → abort).
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.RECOVERY,
        )

        receipt = RotationReceipt(
            vault_id=key_handle.vault_id,
            prior_kek_generation=resolved.kek_generation,
            kek_generation=resolved.kek_generation,  # unchanged
            for_cause=False,
            k=new_ritual.threshold,
            n=new_ritual.total_shards,
            holders=tuple(holder_ids),
            shard_commitments=tuple(shard_commitments),
            kek_identity_commitment=None,  # commitment unchanged — none registered
            kek_commitment_alg=None,
        )
        logger.info(
            "vault.rotate.holder.ok",
            extra={
                "vault_id": key_handle.vault_id,
                "kek_generation": resolved.kek_generation,
                "new_shard_count": len(shard_commitments),
            },
        )
        return receipt
    finally:
        resolved.zeroize()


def revoke_holder_for_cause(
    key_handle: VaultKeyHandle,
    old_shards: Sequence[Sequence[str]],
    current_ritual: ShamirRitual,
    new_ritual: ShamirRitual,
    clearance: ClearanceContext,
    current_holders: Sequence[str],
    revoked_holders: Sequence[str],
    new_holders: Sequence[str],
    *,
    resolver: VaultKeyResolver,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    alg_id: str,
    registry: Optional[CommitmentRegistry] = None,
    holder_registry: Optional[HolderRegistry] = None,
    posture_store: Optional[PostureStore] = None,
    kek_commitment_alg: str = DEFAULT_KEK_COMMITMENT_ALG,
    passphrase: bytes = b"",
    iteration_exponent: int = DEFAULT_ITERATION_EXPONENT,
    side_channel_hardened: bool = False,
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    trust_anchored_now: Optional[datetime] = None,
    approver_configured: bool = False,
    principal: Optional[str] = None,
) -> RotationReceipt:
    """For-cause revocation → generation-advancing KEK-rotation (N12-SH-04 / N12-RT-06).

    A holder revoked **for cause** holds a cryptographically valid
    current-generation shard that no identifier check can distinguish from a
    legitimate one (N12-SH-04). The honest defense is **generation-supersession**:
    this surface escalates the revocation to a KEK-rotation (§5.2) that advances
    ``kek_generation`` from ``g`` to ``g+1`` so the departed holder's retained
    ``g`` shards become **stale** (refused by the §6 guard, N12-SG-02). It emits
    a SINGLE ``vault_kek_rotation`` anchor carrying ``for_cause=True`` AND the
    new ``g+1`` re-shard distribution (the new ``{k,n}``, ``holders``,
    ``shard_commitments``, the new ``kek_identity_commitment`` + alg), so the
    ``for_cause`` flag lands on the anchor that advances the generation (fix [4])
    and N12-CB-03's foreign-shard check has a ``g+1`` source immediately.

    Gate order (fail-closed; a gate failure RAISES typed + WARN-logs, no denial
    anchor — see module docstring):

    1. clearance presence (CL-01) — ``vault:rotate`` else ``missing-clearance``;
    2. ritual floor (N12-TH-01) on ``new_ritual``;
    3. **k-floor (N12-SH-03)** — :func:`check_revocation_k_floor` REFUSES the
       revocation if revoking ``revoked_holders`` would leave fewer than
       ``current_ritual.threshold`` un-revoked holders (the non-revoked holders
       MUST be able to supply ``old_shards`` for reconstruction). Composes the
       B2 guard; does NOT reimplement it;
    4. new holders registry-registered (N12-SH-01);
    5. resolve KEK → ``key_class==KEK`` (N12-IN-02);
    6. full clearance (CL-02a + CL-04) against the resolved vault tenant/domain.

    Then: derive ``prior_gen`` from the audited rotation chain
    (:func:`current_generation_from_chain` — the SAME source C3 reads, N12-RT-06),
    set ``new_gen = prior_gen + 1``, compose ``rotate_holders`` to re-shard,
    compute the ``new_gen`` commitment over the resolved secret, build the
    ``vault_kek_rotation`` anchor, sign + dispatch (AU-02b), then REGISTER the
    ``new_gen`` commitment (AFTER dispatch — the registry mirrors the audited
    chain, never holds a commitment with no audited rotation).

    Mode-A only (N12-RT-04): single-group full re-shard; MUST NOT claim Mode-B.

    Args:
        key_handle: The opaque KEK handle (resolved for the master secret + the
            new-generation commitment + tenant/domain).
        old_shards: EXACTLY ``current_ritual.threshold`` shards from the
            **non-revoked** holders (the reconstruction input for the re-shard).
            The shipped ``shamir.reconstruct`` requires exactly ``threshold``
            mnemonics, not ``n`` — supplying more raises ``MnemonicError``.
        current_ritual: The pre-revocation ``(k, n)`` ritual (the k-floor uses
            its threshold).
        new_ritual: The post-revocation ``(k, n)`` ritual; MUST satisfy the floor.
        clearance: The bound authorization context; MUST carry ``vault:rotate``.
        current_holders: The pre-revocation holder-id set (k-floor input).
        revoked_holders: The holder ids being revoked for cause (k-floor input).
        new_holders: The ordered post-revocation holder-id distribution.
        resolver: The injected trusted-module resolver (source of the master
            secret bound into the new-generation commitment).
        dispatcher: The named-tier audit dispatcher (D1) — also the chain the
            prior generation is derived from.
        signer / signer_identity: The anchor signer + signing identity.
        alg_id: The deployment SLIP-0039 algorithm id.
        registry: The per-(vault_id, gen) commitment registry the new-generation
            commitment is registered into (process default when omitted).
        holder_registry: The deployment holder registry the new distribution is
            checked against.
        posture_store: The PostureStore the CL-04 cooling-off read consults.
        kek_commitment_alg: The EATP-08 §3.3 registry token for the new-generation
            commitment hash (default ``"eatp-v1"`` → SHA-256).
        passphrase: The SLIP-0039 passphrase for ``old_shards`` (NEVER logged).
        iteration_exponent: The pinned ``slip39_params.iteration_exponent``.
        side_channel_hardened: N12-CRY-SC flag (default False).
        timestamp / time_attested: The trust-anchored-timestamp grammar.
        trust_anchored_now: The trust-anchored CL-04 clock.
        approver_configured: The X1 CL-03 seam.
        principal: The acting principal; defaults to ``clearance.principal``.

    Returns:
        A :class:`~kailash.trust.vault.types.RotationReceipt` (``for_cause=True``,
        ``kek_generation == prior_kek_generation + 1``, carrying the new-generation
        commitment).

    Raises:
        VaultBindingError: any gate fails (``missing-clearance`` /
            ``invalid-ritual`` / ``revoked-holder`` (k-floor) /
            ``unregistered-holder`` / ``not-a-kek``), or the audit dispatch fails
            (no receipt → abort, AU-02b).
    """
    acting_principal = principal if principal is not None else clearance.principal

    # Gate 1 — clearance presence.
    try:
        require_clearance(clearance, ROTATE_CAPABILITY)
    except VaultBindingError:
        logger.warning(
            "vault.rotate.denied",
            extra={
                "phase": "clearance-presence",
                "principal": acting_principal,
                "required_capability": ROTATE_CAPABILITY,
                "vault_id": key_handle.vault_id,
                "for_cause": True,
            },
        )
        raise

    # Gate 2 — ritual floor on the NEW ritual.
    require_ritual_floor(new_ritual)

    # Gate 3 — k-floor (N12-SH-03, B2 — NO reimplementation). The non-revoked
    # holders MUST be able to reconstruct (>= k) so the re-shard's old_shards
    # input is satisfiable; if revoking would drop the un-revoked set below the
    # current threshold the revocation is REFUSED ("rotation-required" — surfaced
    # to the operator) rather than leaving the vault unrecoverable.
    check_revocation_k_floor(current_ritual.threshold, current_holders, revoked_holders)

    # Gate 4 — the new holder distribution MUST be registry-registered.
    active_holder_registry = (
        holder_registry if holder_registry is not None else default_holder_registry()
    )
    holder_ids = require_registered_holders(new_holders, active_holder_registry)

    # Gate 5 — resolve KEK inside the trusted module (master secret for the
    # new-generation commitment + tenant/domain for clearance).
    resolved = _resolved_or_raise(resolver, key_handle)
    secret: Optional[bytes] = None
    try:
        require_kek_class(resolved)

        # Gate 6 — full clearance (CL-02a tenant→domain→token + CL-04 cooling-off).
        try:
            evaluate_clearance(
                clearance,
                resolved,
                ROTATE_CAPABILITY,
                posture_store=posture_store,
                now=trust_anchored_now,
                approver_configured=approver_configured,
            )
        except VaultBindingError:
            logger.warning(
                "vault.rotate.denied",
                extra={
                    "phase": "scope-or-cooling-off",
                    "principal": acting_principal,
                    "required_capability": ROTATE_CAPABILITY,
                    "vault_id": key_handle.vault_id,
                    "for_cause": True,
                },
            )
            raise

        # Derive the prior generation from the AUDITED chain (N12-RT-06 — NOT a
        # mutable counter). The new generation is the monotonic next; this anchor
        # becomes the chain high-water the C3 stale-guard reads.
        prior_gen = current_generation_from_chain(
            dispatcher,
            vault_id=key_handle.vault_id,
            captured_generation=resolved.kek_generation,
        )
        new_gen = prior_gen + 1

        logger.info(
            "vault.rotate.for_cause.start",
            extra={
                "vault_id": key_handle.vault_id,
                "prior_kek_generation": prior_gen,
                "new_kek_generation": new_gen,
                "revoked_count": len(set(revoked_holders) & set(current_holders)),
                "new_k": new_ritual.threshold,
                "new_n": new_ritual.total_shards,
                "principal": acting_principal,
            },
        )

        secret = resolved.master_secret
        ms_bits = master_secret_bits(secret)

        # Compose the shipped wrapper — recombine the non-revoked holders'
        # old_shards + re-shard under the new ritual (N12-RT-01; NO reimpl).
        #
        # Trust-boundary invariant (documented): the commitment below binds the
        # RESOLVER's secret while ``rotate_holders`` re-shards the secret
        # reconstructed from ``old_shards``. For a well-formed vault these are the
        # SAME KEK (the resolver is the trusted-module source of the current KEK;
        # ``old_shards`` are the holders' copies of that same KEK), exactly as
        # ``back_up_vault_key`` trusts the resolver for both the commitment AND
        # the split. A caller supplying ``old_shards`` of a DIFFERENT secret
        # produces a g+1 distribution whose new shards reconstruct a secret that
        # fails the registered commitment at restore (``kek-commitment-mismatch``)
        # — a self-inflicted unrecoverable generation by an authorized
        # vault:rotate holder, NOT a security bypass (bounded; surfaced here).
        new_shards = rotate_holders(
            [list(s) for s in old_shards], new_ritual, passphrase=passphrase
        )
        try:
            shard_count = len(new_shards)
            shard_commitments = [_shard_commitment(s) for s in new_shards]
        finally:
            del new_shards

        # The new-generation KEK-identity commitment binds the UNCHANGED master
        # secret to the ADVANCED generation (N12-CB-01 / N12-SG-01(b)): a relabelled
        # g shard recomputes the g-commitment (verifies against the g registry
        # entry) but is refused as STALE by the §6 guard (g < g+1) — generation-
        # supersession, the honest for-cause defense (N12-SH-04).
        new_commitment = kek_identity_commitment(
            vault_id=key_handle.vault_id,
            kek_generation=new_gen,
            master_secret=secret,
            passphrase_provenance=resolved.passphrase_provenance,
            alg=kek_commitment_alg,
        )

        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        payload = build_kek_rotation_anchor(
            alg_id=alg_id,
            prior_kek_generation=prior_gen,
            kek_generation=new_gen,
            vault_id=key_handle.vault_id,
            k=new_ritual.threshold,
            n=new_ritual.total_shards,
            holders=holder_ids,
            shard_count=shard_count,
            shard_commitments=shard_commitments,
            kek_identity_commitment=new_commitment,
            kek_commitment_alg=kek_commitment_alg,
            slip39_params={
                "extendable": True,
                "iteration_exponent": iteration_exponent,
                "group_threshold": 1,
                "master_secret_bits": ms_bits,
            },
            for_cause=True,  # N12-SH-04: the flag rides the generation-advancing anchor
            principal=acting_principal,
            timestamp=ts,
            time_attested=time_attested,
            side_channel_hardened=side_channel_hardened,
        )

        # AU-02b: sign + dispatch to recovery; receipt is the HARD precondition.
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.RECOVERY,
        )

        # Register the new-generation commitment ONLY AFTER the anchor is durably
        # dispatched (the registry mirrors the audited chain — a dispatch failure
        # RAISES above and this line never executes, so the registry never holds
        # a commitment with no audited rotation, AU-02b).
        active_registry = (
            registry if registry is not None else default_commitment_registry()
        )
        active_registry.register(
            vault_id=key_handle.vault_id,
            kek_generation=new_gen,
            kek_commitment_alg=kek_commitment_alg,
            commitment=new_commitment,
            key_id=resolved.key_id,
        )

        receipt = RotationReceipt(
            vault_id=key_handle.vault_id,
            prior_kek_generation=prior_gen,
            kek_generation=new_gen,
            for_cause=True,
            k=new_ritual.threshold,
            n=new_ritual.total_shards,
            holders=tuple(holder_ids),
            shard_commitments=tuple(shard_commitments),
            kek_identity_commitment=new_commitment,
            kek_commitment_alg=kek_commitment_alg,
        )
        logger.info(
            "vault.rotate.for_cause.ok",
            extra={
                "vault_id": key_handle.vault_id,
                "prior_kek_generation": prior_gen,
                "kek_generation": new_gen,
                "new_shard_count": shard_count,
            },
        )
        return receipt
    finally:
        # N12-IN-05: consume-and-del. Drop the local secret reference AND zeroize
        # the resolver's reference so the KEK bytes do not linger past this call.
        secret = None
        del secret
        resolved.zeroize()
