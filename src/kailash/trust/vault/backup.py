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

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Callable, Optional, Sequence

from kailash.delegate.audit import content_signing_bytes
from kailash.delegate.types import DelegateIdentity
from kailash.trust.posture.postures import PostureStore
from kailash.trust.vault.anchors import (
    build_backup_anchor,
    build_denial_anchor,
    build_restore_anchor,
    build_restore_forced_stale_anchor,
)
from kailash.trust.vault.clearance import evaluate_clearance
from kailash.trust.vault.commitment import (
    DEFAULT_KEK_COMMITMENT_ALG,
    kek_identity_commitment,
    key_check_value,
    verify_commitment,
)
from kailash.trust.vault.complete import (
    APPROVE_CAPABILITY,
    WITNESS_CAPABILITY,
    CeremonyWitness,
    ConformanceLevel,
    GovernanceApproval,
    verify_ceremony_witness,
    verify_governance_approval,
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
    map_wrapper_exception,
)
from kailash.trust.vault.holder_registry import (
    HolderRegistry,
    default_holder_registry,
    require_registered_holders,
)
from kailash.trust.vault.input_gates import (
    BACKUP_CAPABILITY,
    RESTORE_CAPABILITY,
    ResolvedKek,
    VaultKeyResolver,
    master_secret_bits,
    require_clearance,
    require_escape_hatch_enabled,
    require_kek_class,
    require_printable_passphrase,
    require_ritual_floor,
    require_secret_length,
)
from kailash.trust.vault.registry import CommitmentRegistry, default_commitment_registry
from kailash.trust.vault.shamir import (
    ShamirRitual,
    generate,
    reconstruct,
    serialize_shard,
)
from kailash.trust.vault.stale_guard import (
    RESTORE_STALE_CAPABILITY,
    CompromisedGenerationDenylist,
    current_generation_from_chain,
    default_compromised_generation_denylist,
    trigger_d6_posture_downgrade,
)
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


def _shard_words_to_str(words: Sequence[str]) -> str:
    """Space-join a shard word-list into the SLIP-0039 mnemonic string form.

    Mirrors the wrapper's internal ``_join`` (single-space delimiter) so a parsed
    :class:`shamir_mnemonic.share.Share` sees the same mnemonic text the
    reconstruct path passes to ``combine_mnemonics``.
    """
    return " ".join(words)


def _parse_share(words: Sequence[str]):
    """Parse ONE shard word-list into a SLIP-0039 ``Share`` WITHOUT reconstructing.

    Returns the parsed ``Share`` (exposing ``.identifier`` + ``.member_threshold``
    SLIP-0039 metadata) or ``None`` on ANY exception (malformed shard, missing
    extra, import failure). Returning ``None`` lets the FT-02 shard-count /
    mixed-identifier gates defer to the reconstruct/checksum backstop rather than
    mislabel a corrupted shard — the pre-reconstruction count/identifier gates are
    additive determinism, never a new failure surface.
    """
    try:
        from shamir_mnemonic.share import Share  # type: ignore[import-not-found]

        return Share.from_mnemonic(_shard_words_to_str(words))
    except Exception:  # noqa: BLE001 - any parse failure → defer to backstop
        return None


def _shard_identifier(words: Sequence[str]) -> Optional[int]:
    """Return a shard's SLIP-0039 ``identifier`` (the per-backup id), or None.

    Two shards from the SAME backup share an identifier; distinct identifiers
    mean the shards came from two different SLIP-0039 backups (mixed set).
    """
    share = _parse_share(words)
    return None if share is None else share.identifier


def _shard_member_threshold(words: Sequence[str]) -> Optional[int]:
    """Return a shard's SLIP-0039 ``member_threshold`` (k), or None on parse error.

    SLIP-0039 encodes k (the within-group member threshold) in each shard's
    metadata, so the required quorum is derivable from a single presented shard
    WITHOUT reconstruction — the pre-reconstruction shard-count gate (FT-02 step 3)
    reads it to detect under/over-supply deterministically.
    """
    share = _parse_share(words)
    return None if share is None else share.member_threshold


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
    conformance_level: ConformanceLevel = ConformanceLevel.CONFORMANT,
    witness: Optional[CeremonyWitness] = None,
    witness_clearance: Optional[ClearanceContext] = None,
    requester_delegate_id: Optional[str] = None,
    verify_token: Optional[Callable[[bytes, str, str], bool]] = None,
    approver_principal: Optional[str] = None,
    approver_delegate_id: Optional[str] = None,
) -> BackupReceipt:
    """Split a KEK (resolved from ``key_handle``) into Shamir shards (N12-IN-01).

    Handle-based primary surface: the KEK is resolved INTERNALLY via
    ``resolver`` (the trusted-module boundary) — raw KEK bytes do NOT cross
    this API (N12-IN-01). NOTE the signature carries NO entropy/seed parameter:
    entropy is sourced internally from the wrapper's CSPRNG (N12-CRY-PIN(e),
    enforced structurally here).

    Gate order (fail-closed):

    1. clearance presence (CL-01) — ``clearance.has_capability("vault:backup")``
       else ``missing-clearance`` (a denial anchor is dispatched to the SAFETY
       tier). This is the cheap token presence-check that needs no resolution;
    2. ritual floor (N12-TH-01) — ``2<=k<=n<=9`` else ``invalid-ritual``;
    3. holders supplied AND registry-registered (N12-SH-01) else
       ``unregistered-holder`` — every holder id MUST be in the deployment
       holder registry BEFORE any sharding (F-AUTHZ-6);
    4. resolve KEK via ``resolver`` → ``key_class==KEK`` else ``not-a-kek``
       (N12-IN-02) BEFORE sharding;
    5. full clearance (CL-02a + CL-04) — tenant→domain→token fail-closed order
       AGAINST the resolved vault tenant/domain, plus the cooling-off
       suspension, BEFORE any sharding. A bound token in tenant/domain A fails
       ``missing-clearance`` against a vault in tenant/domain B; a principal
       inside the 7-day post-recovery window is suspended.

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
        registry: The per-(vault_id, gen) commitment registry to register into
            (N12-CB-04(c)); the process default when omitted.
        holder_registry: The deployment-controlled holder registry gate 3 checks
            every supplied holder id against (N12-SH-01); the process default
            (:func:`~kailash.trust.vault.holder_registry.default_holder_registry`)
            when omitted. The default singleton is EMPTY and FAIL-CLOSED — a
            deployment MUST register its holders before the first backup, else
            every holder is rejected ``unregistered-holder``.
        posture_store: The injected PostureStore the CL-04 cooling-off read
            consults (N12-CL-04). When omitted the cooling-off check cannot run
            (no-receipt conservative default — a backup by a principal with no
            prior materializing restore is not suspended).
        kek_commitment_alg: The EATP-08 §3.3 registry token for the commitment
            hash (default ``"eatp-v1"`` → SHA-256).
        passphrase: Optional SLIP-0039 passphrase (NEVER logged / receipted).
        iteration_exponent: The pinned ``slip39_params.iteration_exponent``.
        side_channel_hardened: N12-CRY-SC flag (default False).
        timestamp: RFC3339-Z attested timestamp (required when
            ``time_attested=True``); ignored when ``time_attested=False``.
        time_attested: Whether ``timestamp`` is trust-anchored (N12-AU-04a).
        trust_anchored_now: The trust-anchored clock the CL-04 cooling-off
            window is evaluated against (N12-CL-04) — the SAME source C3 used to
            record the start, NEVER a locally-mutable wall clock. When a
            cooling-off receipt exists but this is omitted, the suspension
            remains in force (fail-closed).
        approver_configured: Whether a governance-approver (CL-03) is configured
            for this deployment (audit-recorded; the cooling-off suspension is
            lifted only by a VERIFIED approval, never by this flag alone).
        principal: The acting principal recorded on the anchor; defaults to
            ``clearance.principal``.
        conformance_level: ``CONFORMANT`` (default) runs only the
            Conformant-mandatory gates and the pre-image is witness-free
            (byte-unchanged §12.4); ``COMPLETE`` requires an independent ceremony
            witness (N12-CL-05) bound into the signed ``event_payload``.
        witness: the Complete-level ceremony witness (N12-CL-05). When supplied
            it is verified fail-closed and embedded under
            ``event_payload["witness"]``; mandatory at ``COMPLETE``.
        witness_clearance: the witness's bound authorization context (carries
            ``vault:witness`` + the witness's tenant/domain); required when
            ``witness`` is supplied.
        requester_delegate_id: the acting principal's signing ``delegate_id`` —
            the distinctness axis the witness MUST differ on; required when
            ``witness`` is supplied.
        verify_token: ``(pre_image, signature_hex, delegate_id) -> bool`` — the
            deployment verifier (a real ``Ed25519Verifier`` in Tier-2) checking
            the witness's signature; required when ``witness`` is supplied.
        approver_principal / approver_delegate_id: the configured governance
            approver's identity (when one is configured for the deployment); the
            witness MUST be distinct from the approver on both axes (N12-CL-05).

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

    # Gate 2a — passphrase printability (N12-PP-01, §4.4.1): reject a
    # non-printable passphrase DETERMINISTICALLY (`invalid-passphrase`) BEFORE the
    # SLIP-0039 wrapper, rather than as a mapped library ValueError.
    require_printable_passphrase(passphrase)

    # Gate 2b — N12-CRY-SC truthfulness. side_channel_hardened=True is assertable
    # ONLY at Complete AND REQUIRES hardware-backed reconstruction (HSM/enclave)
    # so the secret never enters the non-constant-time userspace
    # combine_mnemonics. THIS binding ALWAYS reconstructs via userspace
    # combine_mnemonics (the SLIP-0039 reference wrapper is documented
    # not-constant-time), so True is never truthful here — recording it would be a
    # fake-classification (zero-tolerance Rule 2). Reject at the entry gate, before
    # resolution. §4.6 has no typed code for this, so a plain ValueError is the
    # correct entry-gate surface.
    if side_channel_hardened is True:
        raise ValueError(
            "side_channel_hardened=True is assertable only at Complete with "
            "hardware-backed reconstruction (HSM/enclave); this binding "
            "reconstructs via userspace combine_mnemonics and cannot truthfully "
            "assert it (N12-CRY-SC). Leave it False."
        )

    # Gate 3 — holders supplied AND registry-registered (N12-SH-01), BEFORE key
    # resolution. Deepens I1's basic presence check: every supplied holder id
    # MUST be a registered, deployment-approved holder, else unregistered-holder
    # on the FIRST unregistered id, BEFORE any sharding (F-AUTHZ-6 — caller-
    # arbitrary holder ids would turn backup-to-attacker-holders into a
    # sanctioned exfiltration channel; the registry closes it). The validated
    # ids are the registry ids recorded on the audit envelope (never contents).
    active_holder_registry = (
        holder_registry if holder_registry is not None else default_holder_registry()
    )
    holder_ids = require_registered_holders(holders, active_holder_registry)

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

        # Gate 5 — full clearance (CL-02a tenant/domain + CL-04 cooling-off),
        # BEFORE sharding. The token presence-check ran at gate 1; this deepens
        # it to the binding-OWNED tenant→domain→token fail-closed order against
        # the RESOLVED vault tenant/domain (the substrate gate is domain-blind),
        # plus the cooling-off suspension. A bound token in tenant/domain A is
        # denied against this vault in tenant/domain B; a principal inside the
        # 7-day post-recovery window is suspended. On failure dispatch a denial
        # to the safety tier BEFORE raising (denials MUST NOT be dropped).
        try:
            evaluate_clearance(
                clearance,
                resolved,
                BACKUP_CAPABILITY,
                posture_store=posture_store,
                now=trust_anchored_now,
                approver_configured=approver_configured,
            )
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

        # Complete-level ceremony witness (N12-CL-05 / X1). At COMPLETE the
        # backup/generation path MUST bind an independent witness into the
        # signed vault_key_backup event_payload (covered by
        # content_signing_bytes), so a missing/forged witness is
        # cryptographically detectable; at CONFORMANT no witness is bound and the
        # pre-image is byte-unchanged (§12.4 golden fixture). Verify BEFORE
        # sharding so a forged witness aborts before any shard is generated.
        witness_payload: Optional[dict[str, Any]] = None
        if conformance_level == ConformanceLevel.COMPLETE and witness is None:
            _emit_backup_denial(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                principal=acting_principal,
                missing_capability_or_scope=WITNESS_CAPABILITY,
                target_handle_ref=target_ref,
            )
            raise VaultBindingError(
                N12FT01Code.MISSING_CLEARANCE,
                "Complete-level backup requires an independent ceremony witness "
                "(N12-CL-05); none was supplied. Pass a CeremonyWitness + "
                "witness_clearance + verify_token, or run at CONFORMANT.",
                details={"required_capability": WITNESS_CAPABILITY},
            )
        if witness is not None:
            if (
                verify_token is None
                or witness_clearance is None
                or requester_delegate_id is None
            ):
                # Caller-contract violation (a witness was supplied without its
                # companion verification inputs) — distinct from a forged/missing
                # WITNESS, which DOES emit a vault_key_backup_denied. We
                # deliberately do NOT emit a denial here: a caller bug must not
                # pollute the safety-tier incident surface with non-attack noise.
                # Still fail-closed (raise before any shard is generated).
                logger.warning(
                    "vault.backup.witness_companion_args_missing",
                    extra={
                        "vault_id": key_handle.vault_id,
                        "has_verify_token": verify_token is not None,
                        "has_witness_clearance": witness_clearance is not None,
                        "has_requester_delegate_id": requester_delegate_id is not None,
                    },
                )
                raise VaultBindingError(
                    N12FT01Code.MISSING_CLEARANCE,
                    "a ceremony witness was supplied but verify_token / "
                    "witness_clearance / requester_delegate_id is missing "
                    "(N12-CL-05); fail-closed.",
                    details={"required_capability": WITNESS_CAPABILITY},
                )
            try:
                witness_payload = verify_ceremony_witness(
                    witness,
                    vault_id=key_handle.vault_id,
                    requester_principal=acting_principal,
                    requester_delegate_id=requester_delegate_id,
                    resolved=resolved,
                    operation="backup",
                    verify_token=verify_token,
                    witness_clearance=witness_clearance,
                    approver_principal=approver_principal,
                    approver_delegate_id=approver_delegate_id,
                )
            except VaultBindingError:
                _emit_backup_denial(
                    dispatcher=dispatcher,
                    signer=signer,
                    signer_identity=signer_identity,
                    principal=acting_principal,
                    missing_capability_or_scope=WITNESS_CAPABILITY,
                    target_handle_ref=target_ref,
                )
                raise

        secret = resolved.master_secret
        ms_bits = master_secret_bits(secret)

        # Shard under the vetted ritual (CSPRNG-internal — no caller entropy).
        shards = generate(secret, ritual, passphrase=passphrase)
        # The shard mnemonics never leave the trusted module; only their count,
        # their per-shard ciphertext COMMITMENTS (SHA-256 of the canonical
        # paper-print form, N12-CB-03), and the commitment/KCV cross the
        # boundary. Compute the shard_commitments BEFORE del-ing the shards so
        # the recovery-tier anchor carries the within-deployment foreign-shard
        # array restore (C2a) consults. The ciphertext hash is one-way and
        # carries no secret (N12-AU-01 contents-exclusion holds).
        shard_count = len(shards)
        shard_commitments = [_shard_commitment(s) for s in shards]
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

        # The per-(vault_id, gen) registry this backup registers into
        # (N12-CB-04(c)); injected for tests, the process singleton otherwise.
        active_registry = (
            registry if registry is not None else default_commitment_registry()
        )

        # Build the OUTCOME anchor (D2). The within-deployment foreign-shard
        # array (N12-CB-03) is the per-shard ciphertext-commitment set computed
        # above; the cross-SDK / cross-generation defense is the KEK-identity
        # commitment registered just below.
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
            shard_commitments=shard_commitments,
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
            witness=witness_payload,
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

        # Register the KEK-identity commitment ONLY AFTER the OUTCOME anchor is
        # durably dispatched (N12-CB-04(c) + N12-IN-04 key_id binding). Ordering
        # matters: a dispatch failure RAISES above and this line never executes,
        # so the registry never holds a commitment with no audited backup — the
        # registry mirrors the audited recovery-tier chain (AU-02b).
        active_registry.register(
            vault_id=key_handle.vault_id,
            kek_generation=resolved.kek_generation,
            kek_commitment_alg=kek_commitment_alg,
            commitment=commitment,
            key_id=resolved.key_id,
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
            # `secret` was never bound — an early raise above (resolve/gate
            # failure) exits before line 610. Nothing to delete; the resolver
            # zeroize below still runs unconditionally. (N12-IN-05.)
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
    alg_id: str,
    registry: Optional[CommitmentRegistry] = None,
    denylist: Optional[CompromisedGenerationDenylist] = None,
    posture_store: Optional[PostureStore] = None,
    force_stale: bool = False,
    expected_commitment: Optional[str] = None,
    expected_kcv: Optional[str] = None,
    kek_commitment_alg: str = DEFAULT_KEK_COMMITMENT_ALG,
    passphrase: bytes = b"",
    holders: Sequence[str] = (),
    shard_commitments: Sequence[str] = (),
    re_established_handle_ref: Optional[str] = None,
    timestamp: Optional[str] = None,
    time_attested: bool = False,
    trust_anchored_now: Optional[datetime] = None,
    approver_configured: bool = False,
    principal: Optional[str] = None,
    conformance_level: ConformanceLevel = ConformanceLevel.CONFORMANT,
    approval: Optional[GovernanceApproval] = None,
    approver_clearance: Optional[ClearanceContext] = None,
    requester_delegate_id: Optional[str] = None,
    verify_token: Optional[Callable[[bytes, str, str], bool]] = None,
) -> RestoreReceipt:
    """Reconstruct a KEK from ``shards`` and re-establish it opaquely (N12-IN-01).

    Handle-based: ``target_handle`` is resolved internally to obtain the target
    KEK's class + generation + key_id + passphrase provenance (the resolver is
    the trusted-module boundary). Raw KEK bytes are NOT returned (N12-IN-05) —
    only an opaque :class:`~kailash.trust.vault.types.RestoreReceipt` ref.

    Gate order (FT-02 §4.6, the canonical first-failing sequence). B1 deepens the
    clearance gate (step 1) from I1's presence-check to the full §4.2 control:
    CL-02a tenant→domain→token fail-closed scoping against the resolved vault
    tenant/domain (the substrate capability gate is domain-blind, so the binding
    OWNS the tenant/domain cascade) PLUS the CL-04 cooling-off suspension (a 2nd
    materializing op by a principal inside the 7-day post-recovery window is
    rejected ``missing-clearance``). A cheap token presence-check still runs
    BEFORE resolution (so an unauthorized caller is denied without touching key
    material); the full CL-02a/CL-04 evaluation runs at step 1 once the resolver
    has supplied the vault's tenant/domain, BEFORE any shard is combined. C2a
    wires the foreign-shard (step 6), commitment-auth (step 7), and key-identity
    sub-gate of step 7. Step 6 evaluates the PRESENTED shard ciphertext-hashes
    against the distribution anchor's ``shard_commitments`` and runs **BEFORE
    reconstruction** (it needs no secret); reconstruction happens between step 6
    and step 7; step 7 authenticates the reconstructed secret + key-identity. The
    remaining gates (shard-count / parameter / mixed-identifier) are backstopped
    by the wrapper raising and are mapped via :func:`map_wrapper_exception`;
    ordinal-generation (step 8) is C3's.

    **Registry consultation (C2a — replaces the Wave-2 caller-supplied interim).**
    When a ``registry`` is available (injected or the process default), restore
    SOURCES its anti-injection inputs from the registry + the recovery-tier
    distribution anchor rather than trusting caller args:

    * commitment-auth recomputes the commitment over ``resolved.kek_generation``
      under the backup's recorded ``kek_commitment_alg`` and compares to the
      registry entry — discriminating the three N12-CB-02 codes precisely
      (``commitment-alg-mismatch`` / ``retired-commitment-alg`` /
      ``kek-commitment-mismatch``);
    * key-identity (N12-CB-02(d)) compares ``target_handle``'s captured ``key_id``
      against the registered ``key_id`` → ``key-identity-mismatch``;
    * foreign-shard + the restore anchor's distribution (holders/shard_commitments)
      are sourced from the recovery-tier distribution anchor for
      ``(vault_id, kek_generation)``.

    ``expected_commitment`` / ``holders`` / ``shard_commitments`` remain as a
    BACKWARD-COMPAT fallback for callers/tests that supply the distribution
    explicitly (the Wave-2 interim); the registry/anchor source takes precedence
    when a registration exists. ``map_wrapper_exception`` is wired fail-closed: an
    UNRECOGNIZED wrapper exception (None return) DENIES the restore — never a
    silent proceed.

    Args:
        shards: The presented shard mnemonics (each a word-list).
        target_handle: The opaque target KEK handle; resolved internally.
        clearance: The bound authorization context; MUST carry ``vault:restore``.
        resolver: The injected trusted-module resolver.
        dispatcher: The named-tier audit dispatcher (D1).
        signer / signer_identity: The anchor signer + identity.
        alg_id: The deployment SLIP-0039 algorithm id (rides
            ``event_payload.alg_id``).
        registry: The per-(vault_id, gen) commitment registry to CONSULT
            (N12-CB-04(c)); the process default when omitted.
        denylist: The per-vault compromised-generation denylist consulted at
            step 8 (N12-SG-05); the process default when omitted. A denylisted
            captured generation → ``revoked-generation``, NOT overridable by
            ``force_stale``, EVEN when it equals current.
        posture_store: The injected PostureStore (N12-RT-05). EVERY successful
            KEK-materializing restore downgrades ``principal`` to SUPERVISED +
            records a 7-day cooling-off start via this store. Omitting it skips
            the D6 trigger with a loud WARN (a Conformant deployment MUST wire it).
        force_stale: N12-SG-03 override. Overrides ONLY the step-8 ordinal
            staleness gate (never steps 6/7, never the denylist). Requires the
            DISTINCT higher capability ``vault:restore-stale`` (else
            ``missing-clearance``). When set on a successful restore: sources the
            step-6 foreign-shard array from the CAPTURED (old-gen) distribution,
            emits a LOUD ``vault_key_restore_forced_stale`` anchor dual-emitted to
            BOTH recovery AND safety, and sets ``RestoreReceipt.forced_stale=True``.
        expected_commitment: Backward-compat fallback commitment (the Wave-2
            interim) — used only when the registry has no entry for the target.
        expected_kcv: Optional offline key-check-value (N12-CB-04(d) / V6) from
            the ``BackupReceipt``. When supplied, the commitment-auth gate
            recomputes the 16-hex KCV over the reconstructed secret + captured
            generation and constant-time compares it; a mismatch (a relabelled /
            tampered escrow blob) fails ``kcv-mismatch`` OFFLINE — no registry or
            live vault needed. ``None`` (default) skips the check (backward-compat).
        kek_commitment_alg: The backup's recorded commitment-registry token.
        passphrase: The SLIP-0039 passphrase used at backup time.
        holders / shard_commitments: Backward-compat fallback distribution —
            used only when no recovery-tier distribution anchor is found.
        re_established_handle_ref: The opaque re-established handle (caller-supplied
            until #630's re-establishment hierarchy mints it).
        timestamp / time_attested: N12-AU-04a two-state grammar.
        trust_anchored_now: The trust-anchored clock the CL-04 cooling-off window
            (FT-02 step 1) is evaluated against (N12-CL-04) — the SAME source C3
            used to record the start, NEVER a locally-mutable wall clock. When a
            cooling-off receipt exists but this is omitted, the suspension
            remains in force (fail-closed). A roll-forward does NOT lift an
            active suspension early.
        approver_configured: Whether a governance-approver (CL-03) is configured
            for this deployment (audit-recorded; the cooling-off suspension is
            lifted only by a VERIFIED approval, never by this flag alone).
        principal: The acting principal; defaults to ``clearance.principal``.
        conformance_level: ``CONFORMANT`` (default) embeds no approval and the
            restore pre-image is byte-unchanged; ``COMPLETE`` makes the
            governance-approver HELD action MANDATORY on the high-risk restore
            paths (forced-stale N12-SG-03 here; cooling-off N12-CL-04 is enforced
            by the clearance gate, which only lifts the suspension on a verified
            approval).
        approval: the Complete-level governance approval (N12-CL-03). When
            supplied it is verified fail-closed BEFORE the FT-02 gate sequence,
            lifts a CL-04 cooling-off suspension, and is embedded under
            ``event_payload["approval"]`` (covered by ``content_signing_bytes``).
        approver_clearance: the approver's bound authorization context (carries
            ``vault:approve`` + the approver's tenant/domain); required when
            ``approval`` is supplied.
        requester_delegate_id: the acting principal's signing ``delegate_id`` —
            the distinctness axis the approver MUST differ on; required when
            ``approval`` is supplied.
        verify_token: ``(pre_image, signature_hex, delegate_id) -> bool`` — the
            deployment verifier checking the approver's signature; required when
            ``approval`` is supplied.

    Returns:
        A :class:`~kailash.trust.vault.types.RestoreReceipt`.

    Raises:
        VaultBindingError: any gate fails (``missing-clearance`` / ``not-a-kek`` /
            ``unknown-shard`` / ``commitment-alg-mismatch`` /
            ``retired-commitment-alg`` / ``kek-commitment-mismatch`` /
            ``key-identity-mismatch`` / a mapped wrapper code), or the audit
            dispatch fails (AU-02b).
    """
    target_ref = f"{target_handle.vault_id}:{target_handle.key_id}"
    acting_principal = principal if principal is not None else clearance.principal
    active_registry = (
        registry if registry is not None else default_commitment_registry()
    )
    active_denylist = (
        denylist if denylist is not None else default_compromised_generation_denylist()
    )

    # Passphrase printability (N12-PP-01, §4.4.1): reject a non-printable
    # passphrase DETERMINISTICALLY (`invalid-passphrase`) BEFORE the SLIP-0039
    # wrapper's reconstruct, matching the backup-side entry gate.
    require_printable_passphrase(passphrase)

    # --- pre-resolution clearance — the force_stale higher-capability check
    # (N12-SG-03) is a DISTINCT axis the spec gates separately from the ordinary
    # token, so it runs here BEFORE resolution: a forced-stale restore requires
    # vault:restore-stale IN ADDITION to vault:restore; a caller holding only
    # vault:restore with force_stale=True is denied missing-clearance (F-AUTHZ-9).
    # The ORDINARY token + the CL-02a tenant/domain scoping + the CL-04
    # cooling-off suspension are evaluated TOGETHER at the canonical FT-02 step 1
    # (the "clearance" gate in `check` below) — AFTER resolution supplies the
    # vault tenant/domain, in the fail-closed order tenant→domain→token. That
    # step still runs BEFORE any shard is combined (reconstruction is lazy and
    # fires only at step 7), so deferring the ordinary-token report to step 1
    # honors CL-02a's order WITHOUT combining any shard for an unauthorized
    # caller. Resolution itself materializes nothing dangerous (the secret is
    # held in the trusted module and zeroized in the finally).
    if force_stale:
        try:
            require_clearance(clearance, RESTORE_STALE_CAPABILITY)
        except VaultBindingError:
            _emit_restore_denial(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                principal=acting_principal,
                missing_capability_or_scope=RESTORE_STALE_CAPABILITY,
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
    # auth needs the generation + key_id + passphrase provenance).
    resolved = resolver.resolve_kek(target_handle)
    if not isinstance(resolved, ResolvedKek):
        raise VaultBindingError(
            N12FT01Code.NOT_A_KEK,
            "resolver.resolve_kek MUST return a ResolvedKek; got "
            f"{type(resolved).__name__}",
            details={"returned_type": type(resolved).__name__},
        )

    # --- Source the distribution (N12-CB-03 / N12-AU-04). PREFER the recovery-tier
    # distribution anchor for (vault_id, captured gen); fall back to caller-supplied
    # holders/shard_commitments (the Wave-2 interim) when no anchor is found.
    # N12-IN-05: this span runs AFTER resolution but BEFORE the main try/finally,
    # and `_find_distribution_anchor` / the `dist_anchor.get(...)` extraction
    # dereference attacker-shaped recovery-tier state (dispatcher._engines /
    # entry.event_payload / list(get("holders"))) that can raise. Wrap it so the
    # resolved (live) KEK is zeroized on ANY raise — no denial/error exit leaks an
    # un-zeroized KEK (the same residency class the R1 HIGH-1 fix closed for the X1
    # block; resolved.zeroize() is idempotent so it composes with that block).
    dist_holders: list[str]
    dist_shard_commitments: list[str]
    try:
        dist_anchor = _find_distribution_anchor(
            dispatcher,
            vault_id=target_handle.vault_id,
            kek_generation=resolved.kek_generation,
        )
        if dist_anchor is not None:
            dist_holders = list(dist_anchor.get("holders", []))
            dist_shard_commitments = list(dist_anchor.get("shard_commitments", []))
        else:
            dist_holders = list(holders)
            dist_shard_commitments = list(shard_commitments)
    except BaseException:
        resolved.zeroize()
        raise

    # --- Complete-level governance approval (N12-CL-03 / X1). Verify the
    # approver's HELD action fail-closed HERE — after resolution (the approval
    # pre-image binds resolved.kek_generation + the operation) and BEFORE the
    # FT-02 gate sequence — so a verified approval can (a) lift a CL-04
    # cooling-off suspension at the clearance gate, AND (b) embed into the signed
    # restore anchor (covered by content_signing_bytes). `operation` binds the
    # pre-image to THIS path so an approval cannot be replayed for a different
    # operation/requester (N12-CL-03(c)). A forged/missing approval on a
    # mandatory high-risk path is rejected missing-clearance, dual-recorded as a
    # vault_key_restore_denied denial, BEFORE the KEK is materialized.
    operation = "restore-forced-stale" if force_stale else "restore"
    approval_payload: Optional[dict[str, Any]] = None
    approval_verified = False
    if approval is not None:
        if (
            verify_token is None
            or approver_clearance is None
            or requester_delegate_id is None
        ):
            # Caller-contract violation (an approval was supplied without its
            # companion verification inputs) — distinct from a forged/missing
            # APPROVAL, which DOES emit a vault_key_restore_denied. We
            # deliberately do NOT emit a denial here: a caller bug must not
            # pollute the safety-tier incident surface with non-attack noise.
            # Still fail-closed (raise before any shard is combined).
            logger.warning(
                "vault.restore.approval_companion_args_missing",
                extra={
                    "vault_id": target_handle.vault_id,
                    "has_verify_token": verify_token is not None,
                    "has_approver_clearance": approver_clearance is not None,
                    "has_requester_delegate_id": requester_delegate_id is not None,
                },
            )
            # N12-IN-05: the X1 approval gate runs AFTER resolution but BEFORE the
            # main try/finally, so zeroize the resolved KEK on this exit path (the
            # finally below does not cover the pre-try X1 raises).
            resolved.zeroize()
            raise VaultBindingError(
                N12FT01Code.MISSING_CLEARANCE,
                "a governance approval was supplied but verify_token / "
                "approver_clearance / requester_delegate_id is missing "
                "(N12-CL-03); fail-closed.",
                details={"required_capability": APPROVE_CAPABILITY},
            )
        try:
            approval_payload = verify_governance_approval(
                approval,
                vault_id=target_handle.vault_id,
                requester_principal=acting_principal,
                requester_delegate_id=requester_delegate_id,
                approver_clearance=approver_clearance,
                resolved=resolved,
                operation=operation,
                verify_token=verify_token,
            )
            approval_verified = True
        except VaultBindingError:
            _emit_restore_denial(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                principal=acting_principal,
                missing_capability_or_scope=APPROVE_CAPABILITY,
                target_handle_ref=target_ref,
            )
            # N12-IN-05: zeroize the resolved KEK on this pre-try denial path.
            resolved.zeroize()
            raise

    # Mandatory at COMPLETE for the forced-stale high-risk path (N12-SG-03 +
    # CL-03): a forced-stale restore overrides the staleness gate, so the spec
    # requires the independent governance-approver HELD action. (Cooling-off
    # CL-04 mandatory-ness is enforced INSIDE the clearance gate below — an
    # unverified approval keeps the suspension in force.) Reject BEFORE any shard
    # is combined.
    if (
        conformance_level == ConformanceLevel.COMPLETE
        and force_stale
        and not approval_verified
    ):
        _emit_restore_denial(
            dispatcher=dispatcher,
            signer=signer,
            signer_identity=signer_identity,
            principal=acting_principal,
            missing_capability_or_scope=APPROVE_CAPABILITY,
            target_handle_ref=target_ref,
        )
        # N12-IN-05: zeroize the resolved KEK on this pre-try mandatory-denial path.
        resolved.zeroize()
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "forced-stale restore at Complete level requires a verified "
            "governance-approver HELD action (N12-CL-03 / N12-SG-03); none was "
            "supplied/verified. Pass a GovernanceApproval + approver_clearance + "
            "verify_token, or run at CONFORMANT.",
            details={"required_capability": APPROVE_CAPABILITY},
        )

    secret: bytes = b""
    # `_reconstructed` is a one-element box so the lazy reconstruct (between
    # step 6 and step 7) is visible to the finally for consume-and-del.
    _reconstructed: list[bytes] = []

    def _reconstruct_guarded() -> bytes:
        """Reconstruct between step 6 and step 7, fail-closed on the wrapper.

        On a wrapper raise, map it via :func:`map_wrapper_exception`: a non-None
        code → typed VaultBindingError (insufficient/corrupted/parameter); a None
        (UNRECOGNIZED wrapper exception) → DENY with an internal typed error,
        NEVER proceed and NEVER treat as success (EATP §4.6 fail-closed).
        """
        try:
            value = reconstruct(list(_as_word_lists(shards)), passphrase=passphrase)
        except VaultBindingError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped below; never swallowed
            code = map_wrapper_exception(exc)
            if code is not None:
                raise VaultBindingError(
                    code,
                    f"restore reconstruction failed: {code.value} "
                    f"(vault_id={target_handle.vault_id})",
                    details={"code": code.value, "error": str(exc)},
                ) from exc
            # None → unrecognized wrapper exception. Fail-closed: deny.
            raise VaultBindingError(
                N12FT01Code.CORRUPTED_SHARD,
                "restore reconstruction raised an unrecognized wrapper "
                f"exception ({type(exc).__name__}); denying fail-closed "
                "(the wrapper text is not the only signal; no key without a "
                "recognized, authenticated reconstruction)",
                details={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "vault_id": target_handle.vault_id,
                },
            ) from exc
        nonlocal secret
        secret = value
        _reconstructed.append(value)
        return value

    try:

        def check(gate: str) -> Optional[N12FT01Code]:
            """The FT-02 per-gate predicate (steps 1–8).

            Steps 1–6 evaluate on the PRESENTED shards (no secret). Step 6
            (foreign-shard) runs BEFORE reconstruction. The first gate that
            needs the secret (step 7) triggers the guarded lazy reconstruct, so
            reconstruction happens strictly between step 6 and step 7 — never
            before the foreign-shard gate has passed.
            """
            if gate == "clearance":
                # The cheap token presence-check (CL-01/02) + the force_stale
                # higher-capability check ran BEFORE resolution (above). Here, at
                # the canonical FT-02 step 1, run the full CL-02a tenant/domain
                # scoping + CL-04 cooling-off suspension AGAINST the resolved
                # vault tenant/domain (the substrate gate is domain-blind; this
                # is the binding-OWNED control). tenant→domain→token fail-closed
                # order; cooling-off suspends a 2nd materializing op inside the
                # 7-day window. A bound vault:restore in tenant/domain A fails
                # missing-clearance against this vault in tenant/domain B even
                # with k valid shards. evaluate_clearance raises on failure;
                # translate to the typed code for first_failing.
                try:
                    evaluate_clearance(
                        clearance,
                        resolved,
                        RESTORE_CAPABILITY,
                        posture_store=posture_store,
                        now=trust_anchored_now,
                        approver_configured=approver_configured,
                        approval_verified=approval_verified,
                    )
                except VaultBindingError as exc:
                    return exc.code
                return None
            if gate == "handle-type":
                # N12-IN-02: target MUST be KEK-class.
                if resolved.key_class.value != "kek":
                    return N12FT01Code.NOT_A_KEK
                return None
            if gate == "shard-count":
                # FT-02 step 3 — pre-reconstruction quorum count gate. Derive k
                # (the SLIP-0039 member-threshold) from the PRESENTED shards'
                # metadata via Share.from_mnemonic (no reconstruction). When a
                # shard fails to parse, defer (return None) — the reconstruct /
                # checksum path backstops it as corrupted-shard; do NOT mislabel a
                # malformed shard as a count problem. The wrapper's own under/over
                # "Wrong number" message is ambiguous (it names the count for BOTH
                # branches), so the count distinction is owned HERE, not by the
                # wrapper text.
                #
                # py pins the N12-FT-02 REJECT branch (too-many-shards): an
                # over-supply is REJECTED, the trim branch is not chosen.
                # Cross-SDK reconciliation with kailash-rs (which branch rs picks)
                # is the separate XSDK gate, out of scope here.
                k: Optional[int] = None
                for shard in shards:
                    mt = _shard_member_threshold(shard)
                    if mt is None:
                        return None  # unparseable → defer to corrupted-shard
                    k = mt
                if k is None:
                    return None  # empty presented set → defer to wrapper
                if len(shards) < k:
                    return N12FT01Code.INSUFFICIENT_SHARDS
                if len(shards) > k:
                    return N12FT01Code.TOO_MANY_SHARDS
                return None
            if gate == "parameter":
                # FT-02 step 4 — SLIP-0039 parameter disagreement stays
                # wrapper-backstopped (mapped via map_wrapper_exception at the
                # reconstruct() boundary). No pre-reconstruction predicate here.
                return None
            if gate == "mixed-identifier":
                # FT-02 step 5 — pre-reconstruction mixed-shard-set gate
                # (F-XSDK-13 determinism; runs BEFORE the step-6 foreign-shard
                # gate). Distinct SLIP-0039 identifiers across the presented shards
                # mean two different backups were combined → mixed-shard-set.
                # Defer (None) on any parse failure (backstopped as
                # corrupted-shard), NEVER mislabel.
                identifiers: set[int] = set()
                for shard in shards:
                    ident = _shard_identifier(shard)
                    if ident is None:
                        return None  # unparseable → defer to corrupted-shard
                    identifiers.add(ident)
                if len(identifiers) > 1:
                    return N12FT01Code.MIXED_SHARD_SET
                return None
            if gate == "foreign-shard":
                # N12-CB-03 — BEFORE reconstruction. Every PRESENTED shard's
                # ciphertext-hash MUST be in the distribution anchor's
                # shard_commitments. A shard whose hash is absent → unknown-shard
                # (foreign / old-generation), rejected before reconstruct().
                # When there is NO distribution to consult (no anchor AND no
                # caller-supplied array), fail-closed: a restore with no
                # foreign-shard source MUST NOT silently skip the gate (N12-RT-06).
                if not dist_shard_commitments:
                    return N12FT01Code.UNKNOWN_SHARD
                allowed = set(dist_shard_commitments)
                for shard in shards:
                    if _shard_commitment(shard) not in allowed:
                        return N12FT01Code.UNKNOWN_SHARD
                return None
            if gate == "commitment-auth":
                # N12-CB-02(b)(c)(d) — AFTER reconstruction. Lazily reconstruct
                # (guarded) on first need, then discriminate the 3-way:
                _secret = _reconstruct_guarded()
                # N12-CB-04(d) / V6 — offline KCV blob-tamper check. When the
                # caller supplies the receipt's KCV, recompute it over the
                # reconstructed secret + captured generation and constant-time
                # compare. A relabelled/tampered blob fails OFFLINE here (no
                # registry needed — works for the escrow-blob scenario). Skipped
                # when expected_kcv is None (backward-compat). Runs BEFORE the
                # registry lookup so the offline tamper signal is the FIRST
                # commitment-auth failure surfaced.
                if expected_kcv is not None:
                    recomputed_kcv = key_check_value(
                        vault_id=target_handle.vault_id,
                        kek_generation=resolved.kek_generation,
                        master_secret=_secret,
                        alg=kek_commitment_alg,
                    )
                    if not hmac.compare_digest(recomputed_kcv, expected_kcv):
                        return N12FT01Code.KCV_MISMATCH
                lookup = active_registry.lookup(
                    vault_id=target_handle.vault_id,
                    kek_generation=resolved.kek_generation,
                    kek_commitment_alg=kek_commitment_alg,
                )
                entry = lookup.entry
                if entry is None:
                    # No commitment registered under the recorded alg for this
                    # (vault_id, captured gen). If the caller supplied the
                    # Wave-2 interim expected_commitment, fall back to it
                    # (backward-compat); otherwise the recorded alg was never
                    # registered → commitment-alg-mismatch (N12-CB-04(b)).
                    if expected_commitment is not None:
                        ok = verify_commitment(
                            expected_commitment=expected_commitment,
                            vault_id=target_handle.vault_id,
                            kek_generation=resolved.kek_generation,
                            master_secret=_secret,
                            passphrase_provenance=resolved.passphrase_provenance,
                            alg=kek_commitment_alg,
                        )
                        return None if ok else N12FT01Code.KEK_COMMITMENT_MISMATCH
                    return N12FT01Code.COMMITMENT_ALG_MISMATCH
                if entry.retired:
                    # C2b sets retired=True; C2a always yields False. A retired
                    # entry MUST NOT silently verify (N12-CB-04(e)).
                    return N12FT01Code.RETIRED_COMMITMENT_ALG
                # (d) key-identity (N12-CB-02(d)): the target handle's captured
                # key_id MUST match the registered key_id (intra-vault
                # two-KEK-same-generation / cross-vault re-install). key_id is
                # bound at THIS registry layer (N12-IN-04), not in the §12.2
                # pre-image — so this is the control that detects the case the
                # vault_id-keyed commitment cannot.
                if resolved.key_id != entry.key_id:
                    return N12FT01Code.KEY_IDENTITY_MISMATCH
                # Live registered entry: recompute under the recorded alg +
                # constant-time compare (N12-CB-02(b)(c)). False → injection /
                # wrong passphrase / relabelled-gen-whose-ciphertexts-reached-7.
                ok = verify_commitment(
                    expected_commitment=entry.commitment,
                    vault_id=target_handle.vault_id,
                    kek_generation=resolved.kek_generation,
                    master_secret=_secret,
                    passphrase_provenance=resolved.passphrase_provenance,
                    alg=kek_commitment_alg,
                )
                return None if ok else N12FT01Code.KEK_COMMITMENT_MISMATCH
            if gate == "ordinal-generation":
                # N12-SG-02/03/05 — step 8, AFTER commitment-auth (step 7)
                # authenticated the captured generation. Operates on the
                # ALREADY-AUTHENTICATED captured generation
                # (resolved.kek_generation), NEVER a caller-supplied generation
                # in isolation. Two sub-gates, in this order:
                #
                #   (a) denylist (N12-SG-05) — revoked-generation. NOT
                #       force_stale-overridable: a compromised generation is
                #       refused EVEN WHEN it equals current AND EVEN UNDER
                #       force_stale (the stale guard is purely ordinal and would
                #       not catch a current-but-compromised KEK; F-CRYPTO-6).
                #   (b) ordinal staleness (N12-SG-02) — stale-generation. The
                #       current generation is derived from the AUDITED rotation
                #       chain (N12-RT-06), NOT a mutable counter. captured <
                #       current → stale-generation, UNLESS force_stale (N12-SG-03)
                #       overrides ONLY this ordinal step. When no rotation anchor
                #       exists the captured gen IS current (single-generation):
                #       no staleness.
                if active_denylist.is_revoked(
                    vault_id=target_handle.vault_id,
                    kek_generation=resolved.kek_generation,
                ):
                    return N12FT01Code.REVOKED_GENERATION
                current_gen = current_generation_from_chain(
                    dispatcher,
                    vault_id=target_handle.vault_id,
                    captured_generation=resolved.kek_generation,
                )
                if resolved.kek_generation < current_gen and not force_stale:
                    # A stale superseded generation that passed commitment-auth
                    # MUST refuse by default — never silently roll back to a KEK
                    # under which current data keys are no longer wrapped.
                    return N12FT01Code.STALE_GENERATION
                return None
            # Unknown gate name — fail-closed (the FT-02 order is closed).
            raise VaultBindingError(
                N12FT01Code.PARAMETER_MISMATCH,
                f"restore gate {gate!r} is not a recognized FT-02 gate "
                f"(closed order: {list(RESTORE_GATE_ORDER)})",
                details={"gate": gate},
            )

        first = first_failing(RESTORE_GATE_ORDER, check)
        if first is not None:
            # A gate failed → dispatch a restore denial to the safety tier and
            # raise the typed code (a foreign-shard / commitment / identity
            # mismatch IS a denial-class outcome under N12-AU-01).
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

        # Gates passed (incl. foreign-shard before reconstruct + commitment-auth
        # after). Re-establish the KEK opaquely. The reconstructed secret is
        # consumed for authentication ONLY and is del-ed in the finally — never
        # returned (N12-IN-05).
        ts = timestamp if (time_attested and timestamp is not None) else "unverified"
        # N12-AU-04 (§12.8): the restore anchor records the CURRENT-GENERATION
        # DISTRIBUTION (holders / shard_count / shard_commitments) sourced from
        # the recovery-tier distribution anchor (or the caller-supplied fallback),
        # NOT the presenting k-shard subset. shard_count is the distribution n
        # (len(shard_commitments)). The commitment recorded is the registered
        # (authenticated) one — the registry entry's commitment when present,
        # else the caller's expected_commitment fallback.
        registered_commitment = active_registry.lookup(
            vault_id=target_handle.vault_id,
            kek_generation=resolved.kek_generation,
            kek_commitment_alg=kek_commitment_alg,
        ).entry
        anchor_commitment = (
            registered_commitment.commitment
            if registered_commitment is not None
            else expected_commitment
        )
        if anchor_commitment is None:
            # Unreachable on a passing restore (commitment-auth passes ONLY via a
            # registered entry OR the expected_commitment fallback, both non-None),
            # but guard fail-closed rather than emit a None-commitment anchor —
            # no anchor without an authenticated commitment (N12-AU-01/CB-02).
            raise VaultBindingError(
                N12FT01Code.KEK_COMMITMENT_MISMATCH,
                "restore reached anchor build with no authenticated commitment "
                f"(vault_id={target_handle.vault_id}); fail-closed",
                details={"vault_id": target_handle.vault_id},
            )
        if force_stale:
            # N12-SG-03 forced-stale rollback: the step-8 ordinal gate was
            # overridden (steps 6/7 still ran — the genuine old set passed
            # foreign-shard against its CAPTURED distribution and commitment-auth
            # over its captured generation). Emit the LOUD distinct
            # vault_key_restore_forced_stale anchor DUAL-emitted to BOTH the
            # recovery AND safety tiers (N12-SG-03 MUST), carrying the captured
            # restored_generation + the overridden current generation. The
            # CAPTURED-generation distribution (dist_holders/dist_shard_commitments,
            # sourced by _find_distribution_anchor keyed on resolved.kek_generation)
            # is what is recorded (fix [2]).
            overridden_current = current_generation_from_chain(
                dispatcher,
                vault_id=target_handle.vault_id,
                captured_generation=resolved.kek_generation,
            )
            forced_payload = build_restore_forced_stale_anchor(
                alg_id=alg_id,
                re_established_handle_ref=(re_established_handle_ref or target_ref),
                vault_id=target_handle.vault_id,
                kek_generation=resolved.kek_generation,
                generation_checked=resolved.kek_generation,
                restored_generation=resolved.kek_generation,
                overridden_current_generation=overridden_current,
                kek_identity_commitment=anchor_commitment,
                kek_commitment_alg=kek_commitment_alg,
                holders=dist_holders,
                shard_count=len(dist_shard_commitments),
                shard_commitments=dist_shard_commitments,
                principal=acting_principal,
                timestamp=ts,
                time_attested=time_attested,
                approval=approval_payload,
            )
            # Dual-emit: recovery FIRST (the outcome-of-record), then safety (the
            # incident-response surface). BOTH are hard preconditions
            # (require_receipt_or_abort inside _sign_and_dispatch) — a forced
            # rollback that cannot durably record on BOTH tiers aborts before the
            # KEK is treated as re-established (N12-AU-02b fail-closed).
            _sign_and_dispatch(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                event_payload=forced_payload,
                tier=AuditTier.RECOVERY,
            )
            _sign_and_dispatch(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                event_payload=forced_payload,
                tier=AuditTier.SAFETY,
            )
        else:
            payload = build_restore_anchor(
                alg_id=alg_id,
                re_established_handle_ref=(re_established_handle_ref or target_ref),
                vault_id=target_handle.vault_id,
                kek_generation=resolved.kek_generation,
                generation_checked=resolved.kek_generation,
                kek_identity_commitment=anchor_commitment,
                kek_commitment_alg=kek_commitment_alg,
                holders=dist_holders,
                shard_count=len(dist_shard_commitments),
                shard_commitments=dist_shard_commitments,
                principal=acting_principal,
                timestamp=ts,
                time_attested=time_attested,
                approval=approval_payload,
            )
            _sign_and_dispatch(
                dispatcher=dispatcher,
                signer=signer,
                signer_identity=signer_identity,
                event_payload=payload,
                tier=AuditTier.RECOVERY,
            )

        # N12-RT-05 — ANY restore that MATERIALIZES the KEK (ordinary OR
        # forced-stale; NO re-wrap carve-out) triggers D6 by reference: downgrade
        # the principal's posture to SUPERVISED + start the 7-day cooling-off the
        # Wave-4 CL-04 gate consumes. Fired AFTER the outcome anchor is durably
        # dispatched (the KEK is materialized only past a successful anchor per
        # AU-02b) and BEFORE returning the receipt. When no posture_store is
        # injected the trigger is skipped with a loud WARN — a deployment claiming
        # Conformant level MUST wire the store (N12-RT-05); the Tier-2 tests inject
        # a real SQLitePostureStore.
        if posture_store is not None:
            # MED (Wave-4 gate): record the cooling-off START from the SAME
            # trust-anchored clock the CL-04 reader compares against — never the
            # producer's wall-clock. A wall-clock start measured against a
            # trust-anchored `now` at read time is a clock-source asymmetry an
            # attacker who skews host time at restore-1 could exploit to shift
            # the window's lower bound.
            trigger_d6_posture_downgrade(
                posture_store,
                principal=acting_principal,
                forced_stale=force_stale,
                now=trust_anchored_now,
            )
        else:
            logger.warning(
                "vault.restore.d6_not_triggered_no_posture_store",
                extra={
                    "vault_id": target_handle.vault_id,
                    "principal": acting_principal,
                    "forced_stale": force_stale,
                    "detail": (
                        "no posture_store injected; N12-RT-05 D6 downgrade NOT "
                        "fired — a Conformant deployment MUST inject the store"
                    ),
                },
            )

        receipt = RestoreReceipt(
            restored_handle=target_handle,
            kek_generation=resolved.kek_generation,
            audit_anchor_ref=target_ref,
            forced_stale=force_stale,
            metadata={"kek_commitment_alg": kek_commitment_alg},
        )
        logger.info(
            "vault.restore.ok",
            extra={
                "vault_id": target_handle.vault_id,
                "key_id": target_handle.key_id,
                "kek_generation": resolved.kek_generation,
                "forced_stale": force_stale,
            },
        )
        return receipt
    finally:
        # N12-IN-05: consume-and-del the reconstructed secret (if reconstruction
        # was reached) + the resolved target material in a finally so every exit
        # path (success, gate-fail, dispatch-fail, foreign-shard-reject-before-
        # reconstruct) drops the plaintext.
        del secret
        _reconstructed.clear()
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


def _shard_commitment(shard: Sequence[str]) -> str:
    """SHA-256 (lowercase hex) of a shard's canonical paper-print ciphertext.

    The within-deployment foreign-shard anchor (N12-CB-03) is the SHA-256 of each
    shard's canonical SLIP-0039 mnemonic form (the paper-print ciphertext produced
    by :func:`~kailash.trust.vault.shamir.serialize_shard` — space-joined words).
    Backup computes one per generated shard so the recovery-tier
    ``vault_key_backup`` anchor carries the per-deployment ``shard_commitments``
    array; restore re-hashes each PRESENTED shard the same way and rejects a shard
    whose hash is absent from that array with ``unknown-shard`` BEFORE
    reconstruction.
    """
    return hashlib.sha256(serialize_shard(list(shard)).encode("utf-8")).hexdigest()


#: The recovery-tier OUTCOME subtypes that establish a generation's shard
#: distribution (N12-CB-03 sources the foreign-shard array from one of these).
#: ``vault_kek_recommit`` / ``vault_kek_retire`` are EXCLUDED — they re-shard
#: nothing, so they carry no distribution.
_DISTRIBUTION_SUBTYPES: frozenset[str] = frozenset(
    {"vault_key_backup", "vault_holder_rotation", "vault_kek_rotation"}
)


def _find_distribution_anchor(
    dispatcher: AuditDispatcher,
    *,
    vault_id: str,
    kek_generation: int,
) -> Optional[dict[str, Any]]:
    """Find the recovery-tier distribution anchor for ``(vault_id, gen)`` (N12-CB-03).

    Scans the recovery-tier engine entries for the LATEST OUTCOME anchor whose
    ``subtype`` establishes a shard distribution AND whose ``vault_id`` +
    ``kek_generation`` match. Returns its ``event_payload`` (carrying
    ``shard_commitments`` + ``holders``) or ``None`` when no such anchor exists.

    For Wave-3 the ordinary in-generation restore reads the CURRENT-generation
    distribution anchor; the forced-stale captured-generation source (sourcing
    the CAPTURED old-generation distribution) is C3's. C2a sources the anchor
    matching the generation being restored (``resolved.kek_generation``).
    """
    engine = dispatcher._engines.get(AuditTier.RECOVERY.value)
    if engine is None:
        return None
    match: Optional[dict[str, Any]] = None
    for entry in engine.entries:
        payload = entry.event_payload
        if (
            payload.get("subtype") in _DISTRIBUTION_SUBTYPES
            and payload.get("vault_id") == vault_id
            and payload.get("kek_generation") == kek_generation
        ):
            match = payload  # latest-wins (entries are append-ordered)
    return match
