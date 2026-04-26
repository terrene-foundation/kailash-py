# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Signing — Ed25519 cryptographic operations for trust chain integrity.

This module re-exports the core signing functions from
``kailash.trust.signing.crypto``. All functions require ``pynacl``
(included in the base ``pip install kailash``).

Functions:

- :func:`generate_keypair` — Generate an Ed25519 key pair.
- :func:`sign` — Sign a payload with a private key.
- :func:`verify_signature` — Verify a payload signature.
- :class:`DualSignature` — Combined Ed25519 + HMAC signature.
- :func:`dual_sign` — Sign with both Ed25519 and HMAC.
- :func:`dual_verify` — Verify a dual signature.
"""

from __future__ import annotations

# Issue #604 algorithm-agility scaffold — canonical namespace.
# `kailash.trust.signing.algorithm_id` is the module-level home; this
# re-export establishes `kailash.trust.signing` as the canonical import
# path per specs/trust-crypto.md § 21.1.
from kailash.trust.signing.algorithm_id import (
    ALGORITHM_DEFAULT,
    AlgorithmIdentifier,
    coerce_algorithm_id,
)
from kailash.trust.signing.crypto import (
    NACL_AVAILABLE,
    SALT_LENGTH,
    DualSignature,
    derive_key_with_salt,
    dual_sign,
    dual_verify,
    generate_keypair,
    generate_salt,
    hash_chain,
    hash_reasoning_trace,
    hash_trust_chain_state,
    hash_trust_chain_state_salted,
    hmac_sign,
    hmac_verify,
    serialize_for_signing,
    sign,
    sign_reasoning_trace,
    verify_reasoning_signature,
    verify_signature,
)

__all__ = [
    # Constants
    "NACL_AVAILABLE",
    "SALT_LENGTH",
    # Key generation
    "generate_keypair",
    "generate_salt",
    "derive_key_with_salt",
    # Ed25519 signing and verification
    "sign",
    "verify_signature",
    # Serialization and hashing
    "serialize_for_signing",
    "hash_chain",
    "hash_trust_chain_state",
    "hash_trust_chain_state_salted",
    # Reasoning trace crypto
    "hash_reasoning_trace",
    "sign_reasoning_trace",
    "verify_reasoning_signature",
    # Dual signature system
    "DualSignature",
    "hmac_sign",
    "hmac_verify",
    "dual_sign",
    "dual_verify",
    # Issue #604 algorithm-agility scaffold (canonical namespace)
    "ALGORITHM_DEFAULT",
    "AlgorithmIdentifier",
    "coerce_algorithm_id",
]
