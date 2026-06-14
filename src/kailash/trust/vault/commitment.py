# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 KEK-identity commitment + key-check-value (N12-CB-01 / N12-CB-04(d)).

The anti-injection control: every backup registers a commitment over the
canonical tuple binding ``vault_id`` + captured ``kek_generation`` + the
reconstructed secret + passphrase provenance (N12-CB-01); restore recomputes it
and rejects ``kek-commitment-mismatch`` before re-establishing any key. The
standalone key-check-value (N12-CB-04(d)) is a key-free, domain-separated
8-byte tag on the ``BackupReceipt`` that detects a tampered/relabelled blob
offline, without the live vault.

**Canonical form (cross-SDK byte contract — EATP-12 §12.2/§12.3, normative).**
Both pre-images are serialized with :func:`kailash.trust._json.canonical_json_dumps`
(RFC-8785/JCS, ``ensure_ascii=False`` raw UTF-8, sorted keys) so kailash-py and
kailash-rs ``serde_json`` reproduce identical bytes. The fixed-input fixture
(§12.1) yields commitment ``f325754c…405c`` and KCV ``00051364b85b0a43`` — pinned
by the Tier-1 byte-pin harness. The §12 golden fixtures are ASCII-only; the
non-ASCII sentinel (``ensure_ascii=False`` divergence) is reconciled with
kailash-rs at the post-Wave-6 cross-SDK gate (HIGH-3 deferral), NOT here.

**N12-IN-04 note.** The normative §12.2 pre-image is ``vault_id``-keyed and does
**not** contain the KEK ``key_id``; the commitment hash MUST reproduce §12.2
byte-for-byte. The resolved KEK key-id is therefore recorded on the
``BackupReceipt`` and bound into the per-(handle, generation) registry key
(C2a), satisfying N12-IN-04 at the registration layer without perturbing the
cross-SDK commitment bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Callable, Dict

from kailash.trust._json import canonical_json_dumps
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError

logger = logging.getLogger(__name__)

__all__ = [
    "COMMITMENT_DOMAIN_SEP",
    "KCV_DOMAIN_SEP",
    "DEFAULT_KEK_COMMITMENT_ALG",
    "kek_identity_commitment",
    "key_check_value",
    "verify_commitment",
    "verify_kcv",
]

COMMITMENT_DOMAIN_SEP = "EATP-12/kek-identity-commitment/v1"
KCV_DOMAIN_SEP = "EATP-12/kcv/v1"
DEFAULT_KEK_COMMITMENT_ALG = "eatp-v1"

# Additive per-algorithm registry seed (N12-CB-04): the ``kek_commitment_alg``
# registry token → its hash primitive. ``eatp-v1`` resolves to SHA-256 per
# EATP-08 §3.3 (the Hash column). C2a extends this additively (recommit/sunset);
# entries are never removed except by an explicit signed retire (C2b).
_COMMITMENT_ALG_HASH: Dict[str, Callable[[bytes], "hashlib._Hash"]] = {
    "eatp-v1": hashlib.sha256,
    # The hash-sunset successor (EATP-08 §3.3): SHA-512/256 is a distinct
    # 64-hex digest, so a C2b ``vault_kek_recommit`` from ``eatp-v1`` to
    # ``eatp-v1.1`` ADDS a genuinely different commitment ``C_Y`` for the same
    # secret. Registered additively per N12-CB-04(c); removed only by a signed
    # ``vault_kek_retire`` (C2b), never silently.
    "eatp-v1.1": lambda data: hashlib.new("sha512_256", data),
}


def _resolve_hash(alg: str) -> Callable[[bytes], "hashlib._Hash"]:
    """Resolve a ``kek_commitment_alg`` registry token to its hash primitive.

    Fail-closed: an unregistered token raises ``commitment-alg-mismatch`` rather
    than defaulting to any primitive (EATP §4.6).
    """
    h = _COMMITMENT_ALG_HASH.get(alg)
    if h is None:
        raise VaultBindingError(
            N12FT01Code.COMMITMENT_ALG_MISMATCH,
            f"unregistered kek_commitment_alg: {alg!r}",
            details={"kek_commitment_alg": alg},
        )
    return h


def kek_identity_commitment(
    *,
    vault_id: str,
    kek_generation: int,
    master_secret: bytes,
    passphrase_provenance: str,
    alg: str = DEFAULT_KEK_COMMITMENT_ALG,
) -> str:
    """Compute the KEK-identity commitment (N12-CB-01) as lowercase hex.

    Binds the captured ``kek_generation`` *into* the commitment (N12-SG-01(b)) so
    the true generation is cryptographically recoverable — a relabelled-generation
    blob fails the recompute. The ``master_secret`` bytes are bound as their
    lowercase hex per the §12.2 canonical pre-image.
    """
    digest = _resolve_hash(alg)
    pre_image = canonical_json_dumps(
        {
            "domain_sep": COMMITMENT_DOMAIN_SEP,
            "kek_generation": kek_generation,
            "master_secret": master_secret.hex(),
            "passphrase_provenance": passphrase_provenance,
            "vault_id": vault_id,
        }
    )
    return digest(pre_image.encode("utf-8")).hexdigest()


def key_check_value(
    *,
    vault_id: str,
    kek_generation: int,
    master_secret: bytes,
    alg: str = DEFAULT_KEK_COMMITMENT_ALG,
) -> str:
    """Compute the key-free KCV (N12-CB-04(d)) — first 8 bytes (16 hex) of the hash.

    Domain-separated from the commitment (distinct ``domain_sep``) and excludes
    passphrase provenance, so the KCV is an independent offline tamper tag on the
    ``BackupReceipt`` blob.
    """
    digest = _resolve_hash(alg)
    pre_image = canonical_json_dumps(
        {
            "domain_sep": KCV_DOMAIN_SEP,
            "kek_generation": kek_generation,
            "master_secret": master_secret.hex(),
            "vault_id": vault_id,
        }
    )
    return digest(pre_image.encode("utf-8")).hexdigest()[:16]


def verify_commitment(
    *,
    expected_commitment: str,
    vault_id: str,
    kek_generation: int,
    master_secret: bytes,
    passphrase_provenance: str,
    alg: str = DEFAULT_KEK_COMMITMENT_ALG,
) -> bool:
    """Constant-time verify a reconstructed secret against a registered commitment.

    Uses :func:`hmac.compare_digest` (constant-time per `trust-plane-security.md`
    MUST NOT §1) so a mismatch does not leak a timing side-channel. Returns a bool;
    the caller (C2a) maps ``False`` to the typed ``kek-commitment-mismatch`` under
    the FT-02 gate order.
    """
    recomputed = kek_identity_commitment(
        vault_id=vault_id,
        kek_generation=kek_generation,
        master_secret=master_secret,
        passphrase_provenance=passphrase_provenance,
        alg=alg,
    )
    return hmac.compare_digest(recomputed, expected_commitment)


def verify_kcv(
    *,
    expected_kcv: str,
    vault_id: str,
    kek_generation: int,
    master_secret: bytes,
    alg: str = DEFAULT_KEK_COMMITMENT_ALG,
) -> bool:
    """Constant-time verify a KCV (offline blob tamper check, N12-CB-04(d))."""
    recomputed = key_check_value(
        vault_id=vault_id,
        kek_generation=kek_generation,
        master_secret=master_secret,
        alg=alg,
    )
    return hmac.compare_digest(recomputed, expected_kcv)
