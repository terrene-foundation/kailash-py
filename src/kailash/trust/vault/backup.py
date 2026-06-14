# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 vault key-binding surface — handle-based backup + restore (W2-I1).

This module is the public binding between the SLIP-0039 wrapper
(:mod:`kailash.trust.vault.shamir`), the commitment/KCV control
(:mod:`kailash.trust.vault.commitment`), the audit-envelope builders
(:mod:`kailash.trust.vault.anchors`), and the named-tier dispatcher
(:mod:`kailash.trust.vault.dispatch`). It composes them into the two
operator-facing operations the vault binding exposes (issue #1312, mint
ISS-37 / EATP-12 §4.1):

* :func:`back_up_vault_key` — resolve a KEK handle internally, shard it under
  a vetted ritual, register the commitment + KCV, dispatch the OUTCOME anchor
  to the ``recovery`` tier (AU-02b: no shard release until the receipt is in
  hand), and return a :class:`~kailash.trust.vault.types.BackupReceipt` (never
  the secret).
* :func:`restore_vault_key` — gate clearance + handle-type + commitment
  authentication, reconstruct the secret, re-establish the KEK opaquely,
  dispatch the restore anchor, and return a
  :class:`~kailash.trust.vault.types.RestoreReceipt` (an opaque handle ref,
  never the secret).

The handle-based input surface (N12-IN-01) means callers pass a
:class:`~kailash.trust.vault.types.VaultKeyHandle`, NOT raw KEK bytes. The KEK
is resolved INTERNALLY by an injected
:class:`~kailash.trust.vault.input_gates.VaultKeyResolver` (the trusted-module
boundary, §3.4 / #630) and is consumed-and-``del``-ed in a ``finally`` block
(N12-IN-05) — it appears in no return value, receipt field, audit payload, or
log line. A raw-bytes escape hatch exists for migration tooling but is DISABLED
by default (N12-IN-03): the public ``back_up_vault_key`` has no raw-bytes
parameter; a deployment that genuinely needs it routes through the gated
:func:`back_up_raw_vault_key` which raises ``escape-hatch-disabled`` unless the
deployment passes an explicit build flag.

Resolver boundary (the key judgment). The shipped key manager has NO KEK-bytes
resolution / encryption hierarchy (the §3.4 net-new gap, #630). The
:class:`VaultKeyResolver` Protocol is the seam a deployment fills with its real
vault key store; a test injects a deterministic in-test resolver returning
known bytes (NOT a Tier-2 mock — it is the deployment-supplied trusted resolver
exercised through the real binding code path).

Signature evolution (closes #606). The pre-#606 stub signature
``back_up_vault_key(vault_key: bytes, ritual)`` is replaced by the conformant
handle-based form sanctioned by the N12-IN-03 note. Raw KEK bytes no longer
cross the public API by default.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

from kailash.delegate.audit import content_signing_bytes
from kailash.delegate.types import DelegateIdentity
from kailash.trust.vault.anchors import (
    build_backup_anchor,
    build_denial_anchor,
    build_restore_anchor,
)
from kailash.trust.vault.commitment import (
    DEFAULT_KEK_COMMITMENT_ALG,
    kek_identity_commitment,
    key_check_value,
    verify_commitment,
)
from kailash.trust.vault.dispatch import (
    AuditDispatcher,
    AuditTier,
    require_receipt_or_abort,
)
from kailash.trust.vault.errors import (
    RESTORE_GATE_ORDER,
    N12FT01Code,
    VaultBindingError,
    first_failing,
)
from kailash.trust.vault.input_gates import (
    BACKUP_CAPABILITY,
    RESTORE_CAPABILITY,
    ResolvedKek,
    VaultKeyResolver,
    master_secret_bits,
    require_clearance,
    require_escape_hatch_enabled,
    require_holders_supplied,
    require_kek_class,
    require_ritual_floor,
    require_secret_length,
)
from kailash.trust.vault.shamir import ShamirRitual, generate, reconstruct
from kailash.trust.vault.types import (
    BackupReceipt,
    ClearanceContext,
    RestoreReceipt,
    VaultKeyHandle,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AnchorSigner",
    "back_up_vault_key",
    "restore_vault_key",
    "back_up_raw_vault_key",
]

#: The pinned default SLIP-0039 iteration exponent recorded in
#: ``slip39_params.iteration_exponent`` (N12-CRY-PIN(b)). A deployment MAY
#: override via the public param; the binding pins the default at 1.
DEFAULT_ITERATION_EXPONENT: int = 1

#: The anchor event type for every vault binding anchor — a KEK
#: backup/restore/denial IS an external side effect on the trust plane
#: (mirrors :attr:`AuditDispatcher._VAULT_EVENT_TYPE`).
_EVENT_TYPE: str = "external_side_effect"


#: A signer callable: receives the ``content_signing_bytes`` pre-image and
#: returns the 128-hex Ed25519 signature. The deployment / runtime owns the
#: signing key; the binding never sees it (it only sees the produced
#: signature). Mirrors the Tier-2 wiring pattern in the D1 dispatch test.
AnchorSigner = Callable[[bytes], str]


def _sign_and_dispatch(
    *,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    event_payload: dict[str, Any],
    tier: AuditTier,
):
    """Sign the anchor pre-image and dispatch it; return the receipt or RAISE.

    The signed pre-image is ``content_signing_bytes(event_type, event_payload,
    signer.delegate_id)`` — the cross-SDK byte contract the dispatcher's engine
    re-derives and verifies. A dispatch FAILURE propagates (no receipt) per
    N12-AU-02b; the caller routes the result through
    :func:`~kailash.trust.vault.dispatch.require_receipt_or_abort` so no key /
    shard is released without a durable anchor.
    """
    pre_image = content_signing_bytes(
        _EVENT_TYPE, event_payload, signer_identity.delegate_id
    )
    signature = signer(pre_image)
    return require_receipt_or_abort(
        dispatcher.dispatch(
            _EVENT_TYPE,
            event_payload,
            signer_identity,
            signature,
            tier.value,
        )
    )


def _emit_backup_denial(
    *,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    principal: str,
    missing_capability_or_scope: str,
    target_handle_ref: str,
) -> None:
    """Dispatch a ``vault_key_backup_denied`` anchor to the SAFETY tier.

    Denials MUST NOT be dropped (N12-AU-01); the denial anchor carries EXACTLY
    ``{subtype, principal, missing_capability_or_scope, target_handle_ref,
    timestamp, time_attested}`` — vault_id / generation / commitments / KCV /
    ritual are EXPLICITLY OMITTED (the backup was denied before key
    resolution, so it has no such values). Best-effort: a denial-dispatch
    failure is logged but never masks the original denial (the caller already
    holds the typed denial error).
    """
    try:
        payload = build_denial_anchor(
            subtype="vault_key_backup_denied",
            principal=principal,
            missing_capability_or_scope=missing_capability_or_scope,
            target_handle_ref=target_handle_ref,
            timestamp="unverified",
            time_attested=False,
        )
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.SAFETY,
        )
    except Exception as exc:  # noqa: BLE001 - denial dispatch is best-effort
        logger.error(
            "vault.backup.denial_dispatch_failed",
            extra={
                "subtype": "vault_key_backup_denied",
                "principal": principal,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )


def back_up_vault_key(
    key_handle: VaultKeyHandle,
    ritual: ShamirRitual,
    clearance: ClearanceContext,
    holders: Sequence[str],
    *,
    resolver: VaultKeyResolver,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    alg_id: str,
    kek_commitment_alg: str = DEFAULT_KEK_COMMITMENT_ALG,
    passphrase: bytes = b"",
    iteration_exponent: int = DEFAULT_ITERATION_EXPONENT,
    side_channel_hardened: bool = False,
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    principal: Optional[str] = None,
) -> BackupReceipt:
    """Split a KEK (resolved from ``key_handle``) into Shamir shards (N12-IN-01).

    Handle-based primary surface: the KEK is resolved INTERNALLY via
    ``resolver`` (the trusted-module boundary) — raw KEK bytes do NOT cross
    this API (N12-IN-01). NOTE the signature carries NO entropy/seed parameter:
    entropy is sourced internally from the wrapper's CSPRNG (N12-CRY-PIN(e),
    enforced structurally here).

    Gate order (fail-closed):

    1. clearance presence — ``clearance.has_capability("vault:backup")`` else
       ``missing-clearance`` (a denial anchor is dispatched to the SAFETY tier);
    2. ritual floor (N12-TH-01) — ``2<=k<=n<=9`` else ``invalid-ritual``;
    3. holders supplied (basic) else ``unregistered-holder``;
    4. resolve KEK via ``resolver`` → ``key_class==KEK`` else ``not-a-kek``
       (N12-IN-02) BEFORE sharding.

    Then: ``shamir.generate`` → commitment + KCV (C1) → build the
    ``vault_key_backup`` anchor (D2) with ``slip39_params`` incl.
    ``master_secret_bits`` → sign ``content_signing_bytes`` → dispatch to the
    ``recovery`` tier and ``require_receipt_or_abort`` (AU-02b: NO shard release
    / NO receipt until the DispatchReceipt is in hand) → ``del`` the secret in a
    ``finally`` block (N12-IN-05) → return the
    :class:`~kailash.trust.vault.types.BackupReceipt` (carries ``key_id``
    (N12-IN-04), commitment, KCV, k, n, holders — NEVER the secret).

    Args:
        key_handle: The opaque KEK handle (N12-IN-01); resolved internally.
        ritual: The ``(k, n)`` ritual; MUST satisfy the vault floor.
        clearance: The bound authorization context; MUST carry ``vault:backup``.
        holders: The ordered holder-id distribution (n entries).
        resolver: The injected trusted-module resolver (deployment vault store).
        dispatcher: The named-tier audit dispatcher (D1).
        signer: A callable producing the 128-hex Ed25519 signature over the
            anchor pre-image (the deployment owns the signing key).
        signer_identity: The signing delegate's identity (flows into the
            pre-image + receipt).
        alg_id: The deployment SLIP-0039 algorithm id (rides
            ``event_payload.alg_id``).
        kek_commitment_alg: The EATP-08 §3.3 registry token for the commitment
            hash (default ``"eatp-v1"`` → SHA-256).
        passphrase: Optional SLIP-0039 passphrase (NEVER logged / receipted).
        iteration_exponent: The pinned ``slip39_params.iteration_exponent``.
        side_channel_hardened: N12-CRY-SC flag (default False).
        timestamp: RFC3339-Z attested timestamp (required when
            ``time_attested=True``); ignored when ``time_attested=False``.
        time_attested: Whether ``timestamp`` is trust-anchored (N12-AU-04a).
        principal: The acting principal recorded on the anchor; defaults to
            ``clearance.principal``.

    Returns:
        A :class:`~kailash.trust.vault.types.BackupReceipt`.

    Raises:
        VaultBindingError: any gate fails (``missing-clearance`` /
            ``invalid-ritual`` / ``unregistered-holder`` / ``not-a-kek``), or
            the audit dispatch fails (no receipt → abort, AU-02b).
    """
    target_ref = f"{key_handle.vault_id}:{key_handle.key_id}"
    acting_principal = principal if principal is not None else clearance.principal

    # Gate 1 — clearance. On failure dispatch a denial to the safety tier
    # BEFORE raising (denials MUST NOT be dropped, N12-AU-01).
    try:
        require_clearance(clearance, BACKUP_CAPABILITY)
    except VaultBindingError:
        _emit_backup_denial(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            principal=acting_principal,
            missing_capability_or_scope=BACKUP_CAPABILITY,
            target_handle_ref=target_ref,
        )
        raise

    # Gate 2 — ritual floor (N12-TH-01), BEFORE key resolution.
    require_ritual_floor(ritual)

    # Gate 3 — holders supplied (basic), BEFORE key resolution.
    holder_ids = require_holders_supplied(holders)

    logger.info(
        "vault.backup.start",
        extra={
            "vault_id": key_handle.vault_id,
            "key_id": key_handle.key_id,
            "k": ritual.threshold,
            "n": ritual.total_shards,
            "principal": acting_principal,
        },
    )

    # Resolve the KEK inside the trusted module. The resolved bytes are
    # consumed below and ``del``-ed in the finally (N12-IN-05).
    resolved = resolver.resolve_kek(key_handle)
    if not isinstance(resolved, ResolvedKek):
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            "resolver.resolve_kek MUST return a ResolvedKek; got "
            f"{type(resolved).__name__}",
            details={"returned_type": type(resolved).__name__},
        )
    try:
        # Gate 4 — KEK-class type enforcement (N12-IN-02), BEFORE sharding.
        require_kek_class(resolved)

        secret = resolved.master_secret
        ms_bits = master_secret_bits(secret)

        # Shard under the vetted ritual (CSPRNG-internal — no caller entropy).
        shards = generate(secret, ritual, passphrase=passphrase)
        # The shard mnemonics never leave the trusted module; only their count
        # and the commitment/KCV cross the boundary. del the shards eagerly.
        shard_count = len(shards)
        del shards

        # Commitment + KCV (C1) bind the resolved generation + secret.
        commitment = kek_identity_commitment(
            vault_id=key_handle.vault_id,
            kek_generation=resolved.kek_generation,
            master_secret=secret,
            passphrase_provenance=resolved.passphrase_provenance,
            alg=kek_commitment_alg,
        )
        kcv = key_check_value(
            vault_id=key_handle.vault_id,
            kek_generation=resolved.kek_generation,
            master_secret=secret,
            alg=kek_commitment_alg,
        )

        # Build the OUTCOME anchor (D2). shard_commitments are NOT computed by
        # I1 (the per-shard ciphertext-hash set is a later shard's concern; the
        # builder requires the field, so I1 supplies the empty ordered array —
        # the within-deployment foreign-shard array is populated by the C2a
        # registry shard). The cross-SDK / cross-generation defense is the
        # KEK-identity commitment, which I1 DOES register.
        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        payload = build_backup_anchor(
            alg_id=alg_id,
            k=ritual.threshold,
            n=ritual.total_shards,
            holders=holder_ids,
            shard_count=shard_count,
            vault_id=key_handle.vault_id,
            kek_generation=resolved.kek_generation,
            kek_identity_commitment=commitment,
            kek_commitment_alg=kek_commitment_alg,
            kcv=kcv,
            shard_commitments=[],
            slip39_params={
                "extendable": True,
                "iteration_exponent": iteration_exponent,
                "group_threshold": 1,
                "master_secret_bits": ms_bits,
            },
            principal=acting_principal,
            timestamp=ts,
            time_attested=time_attested,
            side_channel_hardened=side_channel_hardened,
        )

        # AU-02b: sign + dispatch to the recovery tier; the receipt is the
        # HARD precondition for returning the BackupReceipt. A dispatch failure
        # RAISES here (no receipt) and the BackupReceipt is never produced.
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.RECOVERY,
        )

        receipt = BackupReceipt(
            vault_id=key_handle.vault_id,
            kek_generation=resolved.kek_generation,
            kek_commitment_alg=kek_commitment_alg,
            kek_identity_commitment=commitment,
            kcv=kcv,
            k=ritual.threshold,
            n=ritual.total_shards,
            holders=tuple(holder_ids),
            side_channel_hardened=side_channel_hardened,
        )
        logger.info(
            "vault.backup.ok",
            extra={
                "vault_id": key_handle.vault_id,
                "key_id": resolved.key_id,
                "kek_generation": resolved.kek_generation,
                "shard_count": shard_count,
            },
        )
        return receipt
    finally:
        # N12-IN-05: consume-and-del. Drop the local reference AND zeroize the
        # resolver's reference so the KEK bytes do not linger past this call.
        try:
            del secret
        except NameError:
            pass
        resolved.zeroize()


def restore_vault_key(
    shards: Sequence[Sequence[str]],
    target_handle: VaultKeyHandle,
    clearance: ClearanceContext,
    *,
    resolver: VaultKeyResolver,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    expected_commitment: str,
    alg_id: str,
    kek_commitment_alg: str = DEFAULT_KEK_COMMITMENT_ALG,
    passphrase: bytes = b"",
    holders: Sequence[str] = (),
    shard_commitments: Sequence[str] = (),
    re_established_handle_ref: Optional[str] = None,
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    principal: Optional[str] = None,
) -> RestoreReceipt:
    """Reconstruct a KEK from ``shards`` and re-establish it opaquely (N12-IN-01).

    Handle-based: ``target_handle`` is resolved internally to obtain the target
    KEK's class + generation + passphrase provenance (the resolver is the
    trusted-module boundary). Raw KEK bytes are NOT returned (N12-IN-05) — only
    an opaque :class:`~kailash.trust.vault.types.RestoreReceipt` ref.

    Gates I1 OWNS (driven through the canonical FT-02 first-failing order so
    two SDKs return the same first code):

    * ``clearance`` → ``clearance.has_capability("vault:restore")`` else
      ``missing-clearance``;
    * ``handle-type`` → resolve ``target_handle``; ``key_class==KEK`` else
      ``not-a-kek``;
    * ``commitment-auth`` → reconstruct the secret, then ``verify_commitment``
      (C1, constant-time) against ``expected_commitment`` for the target →
      ``kek-commitment-mismatch`` on failure.

    Gates NOT owned by I1 (``shard-count``, ``parameter``, ``mixed-identifier``,
    ``foreign-shard`` (C2a), ``ordinal-generation`` (C3)) are wired by Wave-3
    shards via the SAME ``check`` function. I1's ``check`` returns ``None`` for
    the structurally-safe unwired gates ONLY where a stricter gate added later
    cannot make a Wave-2-accepted restore unsafe (see the inline per-gate
    comments naming the owning shard).

    After the gates pass: consume-and-``del`` the reconstructed secret in a
    ``finally`` block (N12-IN-05), build + dispatch a ``vault_key_restore``
    anchor (D2/D1, RECOVERY tier, AU-02b), and return the
    :class:`~kailash.trust.vault.types.RestoreReceipt` (opaque handle ref,
    never bytes). A clearance denial dispatches a ``vault_key_restore_denied``
    anchor to the SAFETY tier.

    Args:
        shards: The presented shard mnemonics (each a word-list).
        target_handle: The opaque target KEK handle; resolved internally.
        clearance: The bound authorization context; MUST carry ``vault:restore``.
        resolver: The injected trusted-module resolver.
        dispatcher: The named-tier audit dispatcher (D1).
        signer / signer_identity: The anchor signer + identity.
        expected_commitment: The registered KEK-identity commitment for the
            target (the caller/resolver supplies it this wave; the C2a registry
            replaces this in Wave 3).
        alg_id: The deployment SLIP-0039 algorithm id (rides
            ``event_payload.alg_id``).
        kek_commitment_alg: The commitment registry token (default ``eatp-v1``).
        passphrase: The SLIP-0039 passphrase used at backup time.
        holders: The current-generation holder distribution (recorded on the
            restore anchor per N12-AU-04; sourced from the establishing
            distribution anchor by the caller).
        timestamp / time_attested: N12-AU-04a two-state grammar.
        principal: The acting principal; defaults to ``clearance.principal``.

    Returns:
        A :class:`~kailash.trust.vault.types.RestoreReceipt`.

    Raises:
        VaultBindingError: any owned gate fails (``missing-clearance`` /
            ``not-a-kek`` / ``kek-commitment-mismatch``), or the audit dispatch
            fails (AU-02b).
    """
    target_ref = f"{target_handle.vault_id}:{target_handle.key_id}"
    acting_principal = principal if principal is not None else clearance.principal

    # --- gate 1 (clearance) — runs BEFORE resolution/reconstruction so a
    # denial dispatches without touching key material.
    try:
        require_clearance(clearance, RESTORE_CAPABILITY)
    except VaultBindingError:
        _emit_restore_denial(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            principal=acting_principal,
            missing_capability_or_scope=RESTORE_CAPABILITY,
            target_handle_ref=target_ref,
        )
        raise

    logger.info(
        "vault.restore.start",
        extra={
            "vault_id": target_handle.vault_id,
            "key_id": target_handle.key_id,
            "shard_count": len(shards),
            "principal": acting_principal,
        },
    )

    # Resolve the target handle (handle-type gate needs the class; commitment
    # auth needs the generation + passphrase provenance).
    resolved = resolver.resolve_kek(target_handle)
    if not isinstance(resolved, ResolvedKek):
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            "resolver.resolve_kek MUST return a ResolvedKek; got "
            f"{type(resolved).__name__}",
            details={"returned_type": type(resolved).__name__},
        )

    secret: bytes = b""
    try:
        # Reconstruct the candidate secret BEFORE running the commitment-auth
        # gate (commitment auth needs the reconstructed bytes). Reconstruction
        # itself does not re-establish a key; it only produces the candidate
        # the commitment gate authenticates. shamir.reconstruct may raise
        # wrapper errors (insufficient/mixed/corrupted) — those are gates the
        # Wave-3 shards own; here a wrapper raise propagates as the mapped
        # wrapper condition (resolved at the wrapper-exception layer, errors.py).
        secret = reconstruct(list(_as_word_lists(shards)), passphrase=passphrase)

        # Bind the reconstructed secret as a default arg (`_secret=secret`) so
        # the closure captures the value at def-time — explicit, and clean to
        # static analysis (no closure-over-mutable-local F821).
        def check(gate: str, _secret: bytes = secret) -> Optional[N12FT01Code]:
            """The FT-02 per-gate predicate. I1 owns 2 gates; the rest are seams."""
            if gate == "handle-type":
                # N12-IN-02: target MUST be KEK-class.
                if resolved.key_class.value != "kek":
                    return N12FT01Code.NOT_A_KEK
                return None
            if gate == "commitment-auth":
                # N12-CB-02 (C1): constant-time verify the reconstructed secret
                # against the registered commitment for the target. False →
                # kek-commitment-mismatch.
                ok = verify_commitment(
                    expected_commitment=expected_commitment,
                    vault_id=target_handle.vault_id,
                    kek_generation=resolved.kek_generation,
                    master_secret=_secret,
                    passphrase_provenance=resolved.passphrase_provenance,
                    alg=kek_commitment_alg,
                )
                return None if ok else N12FT01Code.KEK_COMMITMENT_MISMATCH
            # --- gates I1 does NOT own; each documents its owning shard ---
            # "clearance" already ran above (before resolution); returning None
            # here keeps the canonical order intact without re-checking.
            if gate == "clearance":
                return None
            # "shard-count" — insufficient/too-many. Owned by C3 (shard-count
            # gate). SAFE to return None in Wave-2: the shipped wrapper's
            # combine_mnemonics requires EXACTLY k shards and RAISES on
            # under/over-supply, so an out-of-bounds shard set fails at the
            # reconstruct() call above (loud wrapper error) — it never reaches
            # a silently-accepted restore. A stricter C3 gate only changes
            # WHICH typed code surfaces first, never makes a Wave-2-accepted
            # restore unsafe.
            if gate == "shard-count":
                return None
            # "parameter" — SLIP-0039 parameter-mismatch. Owned by C3. SAFE to
            # return None: parameter disagreement RAISES inside reconstruct()
            # (wrapper MnemonicError) above — fail-closed at the wrapper, never
            # a silent accept.
            if gate == "parameter":
                return None
            # "mixed-identifier" — mixed-shard-set. Owned by C3. SAFE: a mixed
            # identifier set RAISES inside reconstruct() (wrapper rejects mixed
            # identifiers) — fail-closed at the wrapper.
            if gate == "mixed-identifier":
                return None
            # "foreign-shard" — within-deployment ciphertext-hash check
            # (N12-CB-03). Owned by C2a (the shard_commitments registry I1 does
            # not populate). SAFE to return None in Wave-2 ONLY because the
            # cross-SDK / cross-generation defense — the KEK-identity
            # commitment — runs at the NEXT gate (commitment-auth) and rejects
            # any reconstructed secret whose commitment does not match the
            # target's registered commitment. A foreign shard set that somehow
            # reconstructs a DIFFERENT secret fails commitment-auth; a set that
            # reconstructs the SAME secret is by definition the genuine secret.
            # C2a tightens the typed code (unknown-shard before
            # kek-commitment-mismatch) but cannot make a Wave-2-accepted
            # restore unsafe — commitment-auth is the backstop.
            if gate == "foreign-shard":
                return None
            # "ordinal-generation" — stale/revoked generation (N12-SG-02/05).
            # Owned by C3 (the ordinal staleness gate sourcing the current
            # generation from the audited rotation chain). This gate is NOT
            # structurally safe to skip in general — a stale (superseded)
            # generation that PASSES commitment-auth (a legitimately-old backup)
            # would be re-established, silently rolling the vault back. But in
            # Wave-2 there is NO rotation chain to source the current generation
            # from (#630 — the generation registry is the C3 net-new gap), so
            # there is no current generation to compare against: every resolved
            # target is its own authoritative generation. Returning None here is
            # therefore correct for the Wave-2 surface (single-generation), and
            # C3 wires the real ordinal comparison the moment the rotation chain
            # exists. Documented as an actively-tracked integration seam (NOT a
            # silent stub): the workspace plan tracks C3's ordinal gate.
            if gate == "ordinal-generation":
                return None
            # Unknown gate name — fail-closed (the FT-02 order is closed; an
            # unrecognized gate is a programming error, never a silent pass).
            raise VaultBindingError(
                N12FT01Code.PARAMETER_MISMATCH,
                f"restore gate {gate!r} is not a recognized FT-02 gate "
                f"(closed order: {list(RESTORE_GATE_ORDER)})",
                details={"gate": gate},
            )

        first = first_failing(RESTORE_GATE_ORDER, check)
        if first is not None:
            # A gate failed → dispatch a restore denial to the safety tier and
            # raise the typed code. (A commitment mismatch / not-a-kek IS a
            # denial-class outcome under N12-AU-01 — the restore did not
            # proceed.)
            _emit_restore_denial(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                principal=acting_principal,
                missing_capability_or_scope=first.value,
                target_handle_ref=target_ref,
            )
            raise VaultBindingError(
                first,
                f"restore gate failed: {first.value} "
                f"(vault_id={target_handle.vault_id})",
                details={"gate_code": first.value, "vault_id": target_handle.vault_id},
            )

        # Gates passed. Re-establish the KEK opaquely. The shipped key manager
        # has no KEK re-establishment hierarchy (#630), so the trusted-module
        # re-establishment is the resolver's domain in a real deployment; here
        # the re-established handle is the (now-authenticated) target handle.
        # The reconstructed secret is consumed for authentication ONLY and is
        # del-ed in the finally — it is NEVER returned (N12-IN-05).
        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        # N12-AU-04 (§12.8): the restore anchor records the CURRENT-GENERATION
        # DISTRIBUTION (holders / shard_count / shard_commitments) copied from
        # the establishing distribution anchor for target_handle — NOT the
        # presenting k-shard subset. In Wave 2 the caller supplies the
        # distribution (holders + shard_commitments), exactly as it supplies
        # expected_commitment; Wave-3 C2a sources both from the registered
        # distribution anchor (N12-CB-03 reads the same record). shard_count is
        # the distribution n (len(shard_commitments)), never len(shards)=k. The
        # re-established handle is the opaque ref the deployment's re-establishment
        # path mints (the #630 hierarchy in Wave 3); the caller supplies it here,
        # falling back to the target ref for an in-place restore.
        payload = build_restore_anchor(
            alg_id=alg_id,
            re_established_handle_ref=(re_established_handle_ref or target_ref),
            vault_id=target_handle.vault_id,
            kek_generation=resolved.kek_generation,
            generation_checked=resolved.kek_generation,
            kek_identity_commitment=expected_commitment,
            kek_commitment_alg=kek_commitment_alg,
            holders=list(holders),
            shard_count=len(shard_commitments),
            shard_commitments=list(shard_commitments),
            principal=acting_principal,
            timestamp=ts,
            time_attested=time_attested,
        )
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.RECOVERY,
        )

        receipt = RestoreReceipt(
            restored_handle=target_handle,
            kek_generation=resolved.kek_generation,
            audit_anchor_ref=target_ref,
            forced_stale=False,
            metadata={"kek_commitment_alg": kek_commitment_alg},
        )
        logger.info(
            "vault.restore.ok",
            extra={
                "vault_id": target_handle.vault_id,
                "key_id": target_handle.key_id,
                "kek_generation": resolved.kek_generation,
            },
        )
        return receipt
    finally:
        # N12-IN-05: consume-and-del the reconstructed secret + the resolved
        # target material in a finally so every exit path (success, gate-fail,
        # dispatch-fail) drops the plaintext.
        del secret
        resolved.zeroize()


def _emit_restore_denial(
    *,
    dispatcher: AuditDispatcher,
    signer: AnchorSigner,
    signer_identity: DelegateIdentity,
    principal: str,
    missing_capability_or_scope: str,
    target_handle_ref: str,
) -> None:
    """Dispatch a ``vault_key_restore_denied`` anchor to the SAFETY tier.

    Denials MUST NOT be dropped (N12-AU-01); best-effort so a denial-dispatch
    failure never masks the original denial.
    """
    try:
        payload = build_denial_anchor(
            subtype="vault_key_restore_denied",
            principal=principal,
            missing_capability_or_scope=missing_capability_or_scope,
            target_handle_ref=target_handle_ref,
            timestamp="unverified",
            time_attested=False,
        )
        _sign_and_dispatch(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            event_payload=payload,
            tier=AuditTier.SAFETY,
        )
    except Exception as exc:  # noqa: BLE001 - denial dispatch is best-effort
        logger.error(
            "vault.restore.denial_dispatch_failed",
            extra={
                "subtype": "vault_key_restore_denied",
                "principal": principal,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )


def back_up_raw_vault_key(
    raw_secret: bytes,
    ritual: ShamirRitual,
    clearance: ClearanceContext,
    holders: Sequence[str],
    *,
    escape_hatch_enabled: bool = False,
    **_unused: Any,
) -> BackupReceipt:
    """Raw-bytes escape-hatch backup — DISABLED by default (N12-IN-03).

    The single most dangerous surface in the spec: it reintroduces raw KEK
    bytes in caller memory and bypasses the handle's generation/identity
    binding. It is therefore DISABLED by default — ``escape_hatch_enabled``
    defaults to ``False`` and a raw-bytes invocation raises
    ``escape-hatch-disabled``. The default build MUST NOT expose the raw-bytes
    path; an implementation whose default exposes it is non-conforming.

    I1 ships the default-OFF gate (the load-bearing structural defense) PLUS
    the secret-length pre-check (N12-CRY-PIN(d)). The ENABLED path's full
    behavior — the mandatory governance-approver HELD action + dual-emit of
    ``vault_key_restore_raw`` to recovery+safety, and the commitment binding —
    is a later shard (Complete/X1); enabling the flag here still raises
    ``escape-hatch-disabled`` until that shard lands, because the enabled path
    is not yet implemented and MUST fail-closed rather than ship a partial
    high-risk surface (no silent security hole).

    Args:
        raw_secret: The raw KEK bytes (escape-hatch only).
        ritual / clearance / holders: as :func:`back_up_vault_key`.
        escape_hatch_enabled: The explicit build/deploy flag (default False).

    Raises:
        VaultBindingError: ``escape-hatch-disabled`` (default OFF), or
            ``invalid-secret-length`` when the flag is set but the secret is
            not a pinned SLIP-0039 length.
    """
    # N12-IN-03 — the default-OFF gate. With the flag absent, the raw-bytes
    # path is rejected BEFORE any other work.
    require_escape_hatch_enabled(escape_hatch_enabled=escape_hatch_enabled)

    # Flag is set: still validate the secret length (N12-CRY-PIN(d)) BEFORE the
    # wrapper, then fail-closed — the enabled path's HELD + dual-emit
    # requirements are not implemented in I1, so we MUST NOT proceed to a
    # partial high-risk backup (no silent security hole).
    require_secret_length(raw_secret)
    raise VaultBindingError(
        N12FT01Code.ESCAPE_HATCH_DISABLED,
        "raw-bytes escape hatch is enabled by flag but the full enabled path "
        "(governance-approver HELD action + vault_key_restore_raw dual-emit to "
        "recovery+safety, N12-IN-03/N12-CL-03) is not yet implemented (a later "
        "shard, Complete/X1). Failing closed rather than shipping a partial "
        "high-risk surface.",
        details={"escape_hatch_enabled": escape_hatch_enabled},
    )


def _as_word_lists(shards: Sequence[Sequence[str]]):
    """Coerce a shard sequence into ``list[list[str]]`` for the wrapper.

    The wrapper's :func:`~kailash.trust.vault.shamir.reconstruct` validates
    deeply; this only normalizes the outer/inner sequence types so a tuple of
    tuples (a common caller shape) reaches the wrapper as lists.
    """
    return [list(s) for s in shards]
