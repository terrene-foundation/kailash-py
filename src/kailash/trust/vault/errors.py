# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 vault-binding failure taxonomy (N12-FT-01/02/03).

This module is the **single source of truth** for the vault binding's typed
error codes (N12-FT-01) and the canonical first-failing gate orders (N12-FT-02
restore path, N12-FT-03 registry-write paths). No other vault-binding shard
re-defines a code or a gate order — they import :class:`N12FT01Code`, raise
:class:`VaultBindingError`, and drive their checks through the ordered-gate
helpers here.

Per EATP-12 §4.6 the binding MUST surface *distinct* typed errors (never a
single generic cryptographic failure) and MUST reuse the Published EATP-10
codes where the condition is the same. The wrapper's underlying
``ValueError``/``TypeError``/``RuntimeError`` text MUST NOT be the only signal;
:func:`map_wrapper_exception` translates the SLIP-0039 wrapper exceptions onto
the typed taxonomy.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Optional, Sequence

from kailash.trust.exceptions import TrustError

logger = logging.getLogger(__name__)

__all__ = [
    "N12FT01Code",
    "VaultBindingError",
    "map_wrapper_exception",
    "RESTORE_GATE_ORDER",
    "RECOMMIT_GATE_ORDER",
    "RETIRE_GATE_ORDER",
    "ROTATION_GATE_ORDER",
    "first_failing",
]


class N12FT01Code(str, Enum):
    """The closed set of EATP-12 §4.6 (N12-FT-01) typed error identifiers.

    Closed by construction: a vault-binding condition that is not one of these
    is a programming error, not a new string code. Codes that mirror a Published
    EATP-10 code carry the same string (``insufficient-shards``, ``unknown-shard``,
    ``unknown-tier``) so the vocabulary does not fork across SDKs.
    """

    # Clearance / input gates (pre key-resolution)
    MISSING_CLEARANCE = "missing-clearance"
    NOT_A_KEK = "not-a-kek"
    INVALID_RITUAL = "invalid-ritual"
    UNREGISTERED_HOLDER = "unregistered-holder"
    INVALID_SECRET_LENGTH = "invalid-secret-length"
    INVALID_PASSPHRASE = "invalid-passphrase"
    ESCAPE_HATCH_DISABLED = "escape-hatch-disabled"
    # Shard-count / parameter / integrity gates
    INSUFFICIENT_SHARDS = "insufficient-shards"  # EATP-10 V2 code
    TOO_MANY_SHARDS = "too-many-shards"
    PARAMETER_MISMATCH = "parameter-mismatch"
    CORRUPTED_SHARD = "corrupted-shard"  # integrity ONLY, never foreign-shard
    UNKNOWN_SHARD = "unknown-shard"  # EATP-10 N8-R-01; foreign / old-generation
    MIXED_SHARD_SET = "mixed-shard-set"
    REVOKED_HOLDER = "revoked-holder"
    # Commitment / identity authentication
    KEK_COMMITMENT_MISMATCH = "kek-commitment-mismatch"
    COMMITMENT_ALG_MISMATCH = "commitment-alg-mismatch"  # never-registered
    RETIRED_COMMITMENT_ALG = "retired-commitment-alg"  # retired entry
    KCV_MISMATCH = "kcv-mismatch"  # offline blob check
    KEY_IDENTITY_MISMATCH = "key-identity-mismatch"  # cross-vault
    # Ordinal generation / denylist
    STALE_GENERATION = "stale-generation"
    REVOKED_GENERATION = "revoked-generation"
    # Registry-write-path (recommit / retire) invariants
    RECOMMIT_GENERATION_ALTERED = "recommit-generation-altered"
    UNKNOWN_PRIOR_COMMITMENT = "unknown-prior-commitment"
    RECOMMIT_BINDING_MISMATCH = "recommit-binding-mismatch"
    # Audit dispatch
    UNKNOWN_TIER = "unknown-tier"  # EATP-09 N9-D-02


class VaultBindingError(TrustError):
    """A typed EATP-12 vault-binding failure (N12-FT-01).

    Carries the closed :class:`N12FT01Code` so callers branch on
    ``err.code is N12FT01Code.UNKNOWN_SHARD`` rather than parsing message text.
    Inherits :class:`~kailash.trust.exceptions.TrustError` so it is caught by the
    trust layer and carries structured ``.details``.
    """

    def __init__(
        self,
        code: N12FT01Code,
        message: Optional[str] = None,
        *,
        details: Optional[dict] = None,
    ) -> None:
        self.code = code
        merged = {"code": code.value}
        if details:
            merged.update(details)
        super().__init__(message or code.value, details=merged)


# --- wrapper-exception → typed-code mapping (N12-FT-01 closing clause) --------
#
# The shipped SLIP-0039 wrapper (kailash.trust.vault.shamir) raises bare
# ValueError/TypeError/RuntimeError. §4.6 makes the binding responsible for
# mapping these onto the typed taxonomy — the wrapper text MUST NOT be the only
# signal. Only the integrity / quorum / parameter conditions the wrapper itself
# can detect are mapped here; foreign-shard (unknown-shard), commitment, and
# generation conditions are decided by the binding's own gates, never by the
# wrapper, so they are intentionally NOT in this map.

_WRAPPER_TEXT_MAP: tuple[tuple[str, N12FT01Code], ...] = (
    # SLIP-0039 "identifier parameters don't match" IS the mixed-identifier error
    # (two backups combined). Defense-in-depth: if a mixed set ever reaches the
    # reconstruct() boundary (e.g. the pre-reconstruction mixed-identifier gate
    # deferred on a parse edge case), surface mixed-shard-set, NOT
    # parameter-mismatch. ORDER MATTERS — this specific needle is checked BEFORE
    # the generic "parameters don't match" below.
    ("identifier parameters don't match", N12FT01Code.MIXED_SHARD_SET),
    ("parameters don't match", N12FT01Code.PARAMETER_MISMATCH),
    # MAC / checksum integrity failure on a KNOWN shard
    ("invalid mnemonic checksum", N12FT01Code.CORRUPTED_SHARD),
    ("checksum", N12FT01Code.CORRUPTED_SHARD),
    ("mac", N12FT01Code.CORRUPTED_SHARD),
    # quorum under-supply
    ("insufficient", N12FT01Code.INSUFFICIENT_SHARDS),
    ("not enough", N12FT01Code.INSUFFICIENT_SHARDS),
)


def map_wrapper_exception(exc: BaseException) -> Optional[N12FT01Code]:
    """Map a SLIP-0039 wrapper exception onto a typed N12-FT-01 code.

    Returns ``None`` when the wrapper exception does not correspond to a
    binding-surface integrity/quorum/parameter condition (the binding's own
    gates own everything else; a ``None`` return means "re-raise as an internal
    error", never "silently treat as success" — fail-closed per EATP §4.6).
    """
    text = str(exc).lower()
    for needle, code in _WRAPPER_TEXT_MAP:
        if needle in text:
            return code
    return None


# --- ordered-gate skeletons (N12-FT-02 restore, N12-FT-03 write paths) --------
#
# Each gate order is the canonical first-failing sequence two conformant SDKs
# MUST share (F-XSDK-13 determinism). The order is data here; the wiring shards
# (C3 restore, C2b recommit/retire, R1 rotation) supply per-gate predicates and
# call first_failing() so the *order* lives in exactly one place.

# N12-FT-02 — restore path, 8 steps (§4.6).
RESTORE_GATE_ORDER: tuple[str, ...] = (
    "clearance",  # (1) N12-CL-01/02/02a/04 → missing-clearance
    "handle-type",  # (2) N12-IN-02 → not-a-kek
    "shard-count",  # (3) insufficient-shards / too-many-shards (or canonical trim)
    "parameter",  # (4) N12-CRY-PIN → parameter-mismatch
    "mixed-identifier",  # (5) → mixed-shard-set
    "foreign-shard",  # (6) N12-CB-03 → unknown-shard
    "commitment-auth",  # (7) kek-commitment / commitment-alg / retired / key-identity
    "ordinal-generation",  # (8) N12-SG-02/03/05 → stale-generation / revoked-generation
)

# N12-FT-03 — vault_kek_recommit, 4 steps (§4.6).
RECOMMIT_GATE_ORDER: tuple[str, ...] = (
    "clearance-tenant-domain",  # (1) N12-CL-01/02a + cooling-off N12-CL-04
    "generation-vault-unchanged",  # (2) → recommit-generation-altered
    "prior-commitment-exists",  # (3) → unknown-prior-commitment
    "new-commitment-binds-secret",  # (4) → recommit-binding-mismatch
)

# N12-FT-03 — vault_kek_retire, 4 steps (§4.6).
RETIRE_GATE_ORDER: tuple[str, ...] = (
    "clearance-tenant-domain",  # (1) vault:retire-alg / governance HELD
    "generation-vault-unchanged",  # (2) → recommit-generation-altered
    "retired-entry-exists",  # (3) → unknown-prior-commitment
    "recoverability-preserved",  # (4) live non-retired strong alg MUST remain
)

# N12-FT-03 — vault_kek_rotation / vault_holder_rotation (§4.6): clearance then floor.
ROTATION_GATE_ORDER: tuple[str, ...] = (
    "clearance-tenant-domain",  # (1) N12-CL-01 / N12-RT-01
    "ritual-floor",  # (2) N12-TH-01 → invalid-ritual
)


def first_failing(
    gate_order: Sequence[str],
    check: Callable[[str], Optional[N12FT01Code]],
) -> Optional[N12FT01Code]:
    """Apply ordered gates and return the FIRST gate's failing code, or ``None``.

    ``check(gate_name)`` returns the typed code if that gate fails, else ``None``.
    Pure + deterministic: given the same ``gate_order`` and a deterministic
    ``check``, two SDKs return the identical first code — the F-XSDK-13 guarantee.
    The wiring shards own ``check``; this function owns only the ORDER traversal.
    """
    for gate in gate_order:
        code = check(gate)
        if code is not None:
            return code
    return None
