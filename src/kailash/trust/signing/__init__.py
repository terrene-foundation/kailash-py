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

# EATP-08 v1.1 algorithm-identifier surface — canonical namespace.
# `kailash.trust.signing.algorithm_id` is the module-level home; this
# re-export establishes `kailash.trust.signing` as the canonical import
# path per specs/trust-crypto.md § 21.1.
from kailash.trust.signing.algorithm_id import (
    ADOPTION_DATE,
    ADOPTION_DATE_PARSED,
    ALGORITHM_DEFAULT,
    ALGORITHM_REGISTRY,
    DEPRECATED_PRE_REGISTRY_LITERAL,
    AlgorithmIdentifier,
    AlgorithmStatus,
    D2dVerifierKeys,
    D2dWitness,
    RegistryEntry,
    UnsupportedAlgorithmError,
    assert_d2d_witness_pre_adoption,
    coerce_algorithm_id,
    d2d_legacy_acceptance_count,
    decode_wire_alg_id,
    is_active,
    is_pre_registry_form,
    is_registered,
    resolve_dispatch,
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
from kailash.trust.signing.delegation_payload import (
    ConstraintDimensions,
    DelegationScope,
    DelegationSigningInput,
    MultiSigSigningPolicy,
    ResourceLimits,
    SigningPayloadVersion,
    TrustLevel,
    delegation_signing_payload,
)
from kailash.trust.signing.delegation_record_signing import (
    build_delegation_signing_input,
    delegation_canonical_payload_str,
    delegation_record_signing_payload,
)
from kailash.trust.signing.derivation import derive_trace_token

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
    # Disclosure-trace token derivation (issue #1482)
    "derive_trace_token",
    # Cross-SDK canonical delegation signing pre-image engine (#1841 §5.3)
    "TrustLevel",
    "SigningPayloadVersion",
    "ConstraintDimensions",
    "ResourceLimits",
    "DelegationScope",
    "MultiSigSigningPolicy",
    "DelegationSigningInput",
    "delegation_signing_payload",
    # Version-gated DelegationRecord signing/verify bridge (#1841 shard 2)
    "delegation_canonical_payload_str",
    "build_delegation_signing_input",
    "delegation_record_signing_payload",
    # EATP-08 v1.1 algorithm-identifier surface (canonical namespace)
    "ADOPTION_DATE",
    "ADOPTION_DATE_PARSED",
    "ALGORITHM_DEFAULT",
    "ALGORITHM_REGISTRY",
    "AlgorithmIdentifier",
    "AlgorithmStatus",
    "D2dVerifierKeys",
    "D2dWitness",
    "DEPRECATED_PRE_REGISTRY_LITERAL",
    "RegistryEntry",
    "UnsupportedAlgorithmError",
    "assert_d2d_witness_pre_adoption",
    "coerce_algorithm_id",
    "d2d_legacy_acceptance_count",
    "decode_wire_alg_id",
    "is_active",
    "is_pre_registry_form",
    "is_registered",
    "resolve_dispatch",
]
