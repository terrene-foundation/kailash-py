# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Trust Vault — SLIP-0039 Shamir backup scaffold (issue #606).

The Trust Vault binding (mint ISS-37) is NOT YET STABLE. This package
exposes the SLIP-0039 wrapper API + a gate-documented stub
(:func:`back_up_vault_key`) that will fill in once the mint spec lands.

See :mod:`kailash.trust.vault.shamir` for the ritual surface.
"""

from __future__ import annotations

import logging

from kailash.trust.vault.backup import back_up_vault_key
from kailash.trust.vault.commitment import (
    kek_identity_commitment,
    key_check_value,
    verify_commitment,
    verify_kcv,
)
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.shamir import (
    ShamirRitual,
    deserialize_shard,
    generate,
    reconstruct,
    rotate_holders,
    serialize_shard,
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
