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
from kailash.trust.vault.shamir import (
    ShamirRitual,
    deserialize_shard,
    generate,
    reconstruct,
    rotate_holders,
    serialize_shard,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ShamirRitual",
    "back_up_vault_key",
    "deserialize_shard",
    "generate",
    "reconstruct",
    "rotate_holders",
    "serialize_shard",
]
