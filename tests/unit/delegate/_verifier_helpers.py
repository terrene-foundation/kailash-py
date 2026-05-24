# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Test helpers for ``kailash.delegate`` signature-verification wiring.

These helpers are Protocol-Satisfying Deterministic Adapters per
``testing.md`` § "3-Tier Testing" — a class satisfying a
``typing.Protocol`` at runtime with deterministic output is NOT a mock.

The two helpers cover the two test postures shard-y tests need:

- :class:`AcceptAnyVerifier` — verifies every (message, signature, signer)
  triple as valid. Used by Tier-1 unit tests that focus on the audit
  chain's monotonicity / hash linkage / sequencing properties; the
  signature surface is exercised separately in
  ``test_verifier.py`` + ``test_signature_verification_wiring.py``.
  Without this helper, every legacy unit test that constructs
  ``AuditChainEngine(chain=...)`` and emits a hex-string signature
  would have to be rewritten to wire a real Ed25519 keypair — a
  ~36-call-site sweep that costs more than the helper and produces
  no additional coverage of the C1 closure (which the dedicated
  verifier tests already exercise byte-for-byte).
- :func:`build_real_verifier_pair` — produces a real Ed25519 keypair
  + directory + signer callable for tests that exercise the
  cryptographic gate end-to-end.

Per the Tier-1 conftest-stub pattern in ``testing.md``, the
:class:`AcceptAnyVerifier` is a deterministic structural double — its
verify() always returns True. The verifier under test
(:class:`kailash.delegate.verifier.Ed25519Verifier`) has its own
dedicated Tier-1 + Tier-2 tests that exercise the cryptographic
contract; this helper exists ONLY so legacy audit-chain tests are not
forced to construct keypairs to assert chain-linkage invariants.
"""

from __future__ import annotations

import uuid
from typing import Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.types import DelegateIdentity, PrincipalDirectory


class AcceptAnyVerifier:
    """Deterministic Protocol adapter — accepts every signature as valid.

    NOT A MOCK per ``testing.md`` § "Protocol-Satisfying Deterministic
    Adapters" — this is a structural double whose output is fully
    deterministic (always True). The real cryptographic gate is
    :class:`kailash.delegate.verifier.Ed25519Verifier`; this helper
    exists so legacy audit-chain Tier-1 tests that focus on chain
    linkage / sequencing / monotonicity invariants do not need to
    construct an Ed25519 keypair to assert those properties.

    Tests exercising the cryptographic gate itself MUST use
    :func:`build_real_verifier_pair` + real :class:`Ed25519Verifier`.
    """

    def verify(
        self,
        message: bytes,  # noqa: ARG002 - protocol signature
        signature: bytes,  # noqa: ARG002 - protocol signature
        signer_delegate_id: str,  # noqa: ARG002 - protocol signature
    ) -> bool:
        return True


def build_real_verifier_pair(
    *, identity: DelegateIdentity | None = None
) -> tuple[DelegateIdentity, PrincipalDirectory, Callable[[bytes], str]]:
    """Build a (identity, directory, signer) triple wiring a real Ed25519 key.

    Returns three things tests need to exercise the real cryptographic
    gate end-to-end:

    1. A :class:`DelegateIdentity` (constructed if not supplied).
    2. A :class:`PrincipalDirectory` carrying the identity AND the
       32-byte Ed25519 public key registered under the identity's
       ``delegate_id``.
    3. A signer callable that takes canonical bytes and returns the
       128-char hex Ed25519 signature — drop-in compatible with the
       ``signer: Callable[[bytes], str]`` parameter of
       :class:`DelegateRuntime`.

    Use this when a test needs to assert "valid signature succeeds /
    invalid fails" through the verifier — i.e., the cryptographic
    contract, not the chain-linkage contract.
    """
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if identity is None:
        identity = DelegateIdentity(
            delegate_id=uuid.uuid4(),
            sovereign_ref="sov-test",
            role_binding_ref="rb-test",
            genesis_ref="gen-test",
        )
    directory = PrincipalDirectory(
        identities=(identity,),
        verification_keys={identity.delegate_id: pub_bytes},
    )

    def signer(canonical_bytes: bytes) -> str:
        return priv.sign(canonical_bytes).hex()

    return identity, directory, signer
