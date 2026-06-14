# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust Vault — EATP-12 v1.0 key-binding (issue #1312).

The EATP-12 Trust-Vault key-binding composes the SLIP-0039 wrapper
(:mod:`kailash.trust.vault.shamir`) with a commitment/KCV control, a
clearance/authz gate, a named-tier audit dispatcher, a per-(vault, generation)
commitment registry, a stale-generation guard, holder rotation, and
Complete-level governance gates. The two operator-facing operations are
:func:`back_up_vault_key` (resolve a KEK handle internally, shard it under a
vetted ritual, register the commitment + KCV, dispatch a signed
``vault_key_backup`` anchor, return a :class:`BackupReceipt`) and
:func:`restore_vault_key` (reconstruct + re-establish the KEK opaquely through
the canonical FT-02 gate order, return a :class:`RestoreReceipt`). Raw KEK bytes
never cross the public API (N12-IN-01); the resolved secret is consumed-and-
``del``-eted in a ``finally`` (N12-IN-05). The raw-bytes escape hatch
(:func:`back_up_raw_vault_key`) is DISABLED by default (N12-IN-03).

See ``specs/trust-crypto.md`` § Trust-Vault Binding (EATP-12) for the full
contract and ``kailash.trust.vault.complete.ConformanceLevel`` for the
Conformant vs Complete level gate.
"""

from __future__ import annotations

import logging

from kailash.trust.vault.backup import (
    AnchorSigner,
    back_up_raw_vault_key,
    back_up_vault_key,
    restore_vault_key,
)
from kailash.trust.vault.clearance import (
    COOLING_OFF_SUSPENDED_CAPABILITIES,
    ROTATE_CAPABILITY,
    domain_covers,
    evaluate_clearance,
    is_in_cooling_off,
    read_cooling_off_start,
)
from kailash.trust.vault.commitment import (
    kek_identity_commitment,
    key_check_value,
    verify_commitment,
    verify_kcv,
)
from kailash.trust.vault.complete import (
    APPROVE_CAPABILITY,
    WITNESS_CAPABILITY,
    CeremonyWitness,
    ConformanceLevel,
    GovernanceApproval,
    HolderRevocationRegistry,
    unwrap_shard_for_holder,
    verify_ceremony_witness,
    verify_governance_approval,
    wrap_shard_for_holder,
)
from kailash.trust.vault.dispatch import (
    AuditDispatcher,
    AuditTier,
    DispatchReceipt,
    require_receipt_or_abort,
)
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.holder_registry import (
    HolderRegistry,
    check_revocation_k_floor,
    default_holder_registry,
    require_registered_holders,
)
from kailash.trust.vault.input_gates import ResolvedKek, VaultKeyResolver
from kailash.trust.vault.registry import (
    CommitmentEntry,
    CommitmentRegistry,
    RegistryLookup,
    default_commitment_registry,
)
from kailash.trust.vault.registry_ops import (
    RETIRE_ALG_CAPABILITY,
    recommit_vault_kek,
    retire_vault_kek_alg,
)
from kailash.trust.vault.rotation import revoke_holder_for_cause, rotate_vault_holders
from kailash.trust.vault.shamir import (
    ShamirRitual,
    deserialize_shard,
    generate,
    reconstruct,
    rotate_holders,
    serialize_shard,
)
from kailash.trust.vault.stale_guard import (
    COOLING_OFF_DAYS,
    RESTORE_STALE_CAPABILITY,
    CompromisedGenerationDenylist,
    current_generation_from_chain,
    default_compromised_generation_denylist,
    trigger_d6_posture_downgrade,
)
from kailash.trust.vault.types import (
    BackupReceipt,
    ClearanceContext,
    HolderId,
    PassphraseRef,
    RestoreReceipt,
    VaultKeyHandle,
)

logger = logging.getLogger(__name__)

__all__ = [
    # SLIP-0039 wrapper (pre-existing)
    "ShamirRitual",
    "back_up_vault_key",
    "deserialize_shard",
    "generate",
    "reconstruct",
    "rotate_holders",
    "serialize_shard",
    # EATP-12 W2-I1 — handle-based binding surface + resolver boundary
    "restore_vault_key",
    "back_up_raw_vault_key",
    "AnchorSigner",
    "VaultKeyResolver",
    "ResolvedKek",
    # EATP-12 W2-D1 — named-tier audit dispatcher (deployment wires this)
    "AuditDispatcher",
    "AuditTier",
    "DispatchReceipt",
    "require_receipt_or_abort",
    # EATP-12 W3-C2a — per-(handle, generation) commitment registry (N12-CB-04(c))
    "CommitmentRegistry",
    "CommitmentEntry",
    "RegistryLookup",
    "default_commitment_registry",
    # EATP-12 W4-B2 — deployment holder registry (N12-SH-01) + k-floor guard (N12-SH-03)
    "HolderRegistry",
    "default_holder_registry",
    "require_registered_holders",
    "check_revocation_k_floor",
    # EATP-12 W3-C2b — commitment-registry write ops (recommit + retire)
    "recommit_vault_kek",
    "retire_vault_kek_alg",
    "RETIRE_ALG_CAPABILITY",
    # EATP-12 W5-R1 — rotation trigger (amicable holder rotation + for-cause gen-advance)
    "rotate_vault_holders",
    "revoke_holder_for_cause",
    # EATP-12 W5-X1 — Complete-level optional knobs (approver / witness / per-holder-wrap)
    "ConformanceLevel",
    "APPROVE_CAPABILITY",
    "WITNESS_CAPABILITY",
    "GovernanceApproval",
    "CeremonyWitness",
    "verify_governance_approval",
    "verify_ceremony_witness",
    "HolderRevocationRegistry",
    "wrap_shard_for_holder",
    "unwrap_shard_for_holder",
    # EATP-12 W3-C3 — stale-generation guard + denylist + RT-05 D6 trigger
    "CompromisedGenerationDenylist",
    "default_compromised_generation_denylist",
    "current_generation_from_chain",
    "trigger_d6_posture_downgrade",
    "RESTORE_STALE_CAPABILITY",
    "COOLING_OFF_DAYS",
    # EATP-12 W4-B1 — clearance eval (CL-01/02/02a token+scope + CL-04 cooling-off)
    "evaluate_clearance",
    "domain_covers",
    "read_cooling_off_start",
    "is_in_cooling_off",
    "ROTATE_CAPABILITY",
    "COOLING_OFF_SUSPENDED_CAPABILITIES",
    # EATP-12 Wave-1 substrate — taxonomy (N12-FT-01)
    "N12FT01Code",
    "VaultBindingError",
    # commitment + KCV (N12-CB-01 / N12-CB-04(d))
    "kek_identity_commitment",
    "key_check_value",
    "verify_commitment",
    "verify_kcv",
    # core DTOs (§4.1/§4.4/§4.5)
    "BackupReceipt",
    "ClearanceContext",
    "HolderId",
    "PassphraseRef",
    "RestoreReceipt",
    "VaultKeyHandle",
]
