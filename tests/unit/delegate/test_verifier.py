# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash.delegate.verifier`` (#1035 C1 closure).

Per ``probe-driven-verification.md`` Rule 3, the verifier's cryptographic
contract is verified STRUCTURALLY — real Ed25519 keypairs, real signing,
real verification — no regex over prose. Per ``testing.md`` § 3-Tier
Testing, Tier-1 is allowed mocks (none used here; real ``cryptography``
library is the structural primitive).

Coverage axes:

- :class:`NullVerifier` always rejects every triple.
- :class:`Ed25519Verifier` returns True for valid (sig, msg, signer) triples
  produced under a known good keypair registered in the directory.
- :class:`Ed25519Verifier` returns False on EVERY failure axis (tampered
  message, tampered signature, unknown signer, malformed signer-id,
  missing key, wrong-length key, non-bytes signature).
- :class:`Ed25519Verifier` NEVER raises — every adversarial input
  surfaces as ``False``.
"""

from __future__ import annotations

import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kailash.delegate.types import DelegateIdentity, PrincipalDirectory
from kailash.delegate.verifier import Ed25519Verifier, NullVerifier, Verifier


def _make_identity() -> DelegateIdentity:
    return DelegateIdentity(
        delegate_id=uuid.uuid4(),
        sovereign_ref="sov-test",
        role_binding_ref="rb-test",
        genesis_ref="gen-test",
    )


def _make_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, pub


# ---------------------------------------------------------------------------
# NullVerifier — fail-closed default
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_null_verifier_satisfies_verifier_protocol() -> None:
    """NullVerifier MUST satisfy the runtime-checkable Verifier Protocol."""
    nv = NullVerifier()
    assert isinstance(nv, Verifier)


@pytest.mark.unit
def test_null_verifier_rejects_every_signature() -> None:
    """NullVerifier returns False unconditionally — the fail-closed default."""
    nv = NullVerifier()
    assert nv.verify(b"msg", b"sig", str(uuid.uuid4())) is False
    assert nv.verify(b"", b"", "") is False
    assert nv.verify(b"x" * 1024, b"y" * 64, str(uuid.uuid4())) is False


@pytest.mark.unit
def test_null_verifier_never_raises() -> None:
    """NullVerifier never raises — adversarial inputs all return False."""
    nv = NullVerifier()
    # Even pathological inputs return False without raising.
    nv.verify(None, None, None)  # type: ignore[arg-type]
    nv.verify("not-bytes", "not-bytes", 42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Ed25519Verifier — real cryptographic gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ed25519_verifier_satisfies_verifier_protocol() -> None:
    """Ed25519Verifier MUST satisfy the Verifier Protocol."""
    ident = _make_identity()
    _, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)
    assert isinstance(ev, Verifier)


@pytest.mark.unit
def test_ed25519_verifier_accepts_valid_signature_byte_for_byte() -> None:
    """Round-trip — generate keypair, sign canonical bytes, verify."""
    ident = _make_identity()
    priv, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)

    canonical_bytes = b'{"event": "test", "sequence": 0}'
    signature_bytes = priv.sign(canonical_bytes)

    assert ev.verify(canonical_bytes, signature_bytes, str(ident.delegate_id)) is True


@pytest.mark.unit
def test_ed25519_verifier_rejects_tampered_message() -> None:
    """A flipped byte in the message MUST fail verification."""
    ident = _make_identity()
    priv, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)

    canonical_bytes = b"original message"
    signature_bytes = priv.sign(canonical_bytes)

    assert (
        ev.verify(b"tampered message", signature_bytes, str(ident.delegate_id)) is False
    )


@pytest.mark.unit
def test_ed25519_verifier_rejects_tampered_signature() -> None:
    """A flipped byte in the signature MUST fail verification."""
    ident = _make_identity()
    priv, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)

    canonical_bytes = b"message to sign"
    sig = bytearray(priv.sign(canonical_bytes))
    sig[0] ^= 0xFF  # flip first byte

    assert ev.verify(canonical_bytes, bytes(sig), str(ident.delegate_id)) is False


@pytest.mark.unit
def test_ed25519_verifier_rejects_unknown_signer() -> None:
    """A signer-id not in the directory MUST fail verification."""
    ident = _make_identity()
    priv, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)

    canonical_bytes = b"message"
    sig = priv.sign(canonical_bytes)
    unknown_id = str(uuid.uuid4())

    assert ev.verify(canonical_bytes, sig, unknown_id) is False


@pytest.mark.unit
def test_ed25519_verifier_rejects_malformed_signer_id() -> None:
    """A signer-id that's not a parseable UUID MUST fail closed."""
    ident = _make_identity()
    priv, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)

    sig = priv.sign(b"msg")
    assert ev.verify(b"msg", sig, "not-a-uuid") is False
    assert ev.verify(b"msg", sig, "") is False


@pytest.mark.unit
def test_ed25519_verifier_rejects_when_no_key_wired_for_signer() -> None:
    """A signer registered in directory but with NO key MUST fail closed."""
    ident = _make_identity()
    priv, _ = _make_keypair()
    # Directory has the identity but NOT the public key — the key store
    # is empty. Per the public_key_for contract, None on miss.
    directory = PrincipalDirectory(identities=(ident,))
    ev = Ed25519Verifier(directory=directory)

    sig = priv.sign(b"msg")
    assert ev.verify(b"msg", sig, str(ident.delegate_id)) is False


@pytest.mark.unit
def test_ed25519_verifier_rejects_non_bytes_signature() -> None:
    """A signature that is not bytes MUST fail closed."""
    ident = _make_identity()
    _, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    ev = Ed25519Verifier(directory=directory)

    # str signature, not bytes
    assert ev.verify(b"msg", "not-bytes", str(ident.delegate_id)) is False  # type: ignore[arg-type]
    # int message, not bytes
    assert ev.verify(42, b"\x00" * 64, str(ident.delegate_id)) is False  # type: ignore[arg-type]


@pytest.mark.unit
def test_ed25519_verifier_construction_rejects_non_directory() -> None:
    """Ed25519Verifier(directory=<not a dir>) MUST TypeError per facade-manager rule 3."""
    with pytest.raises(TypeError, match="MUST be a PrincipalDirectory"):
        Ed25519Verifier(directory="not-a-directory")  # type: ignore[arg-type]


@pytest.mark.unit
def test_principal_directory_rejects_non_32_byte_key() -> None:
    """PrincipalDirectory enforces the 32-byte Ed25519 invariant at construction."""
    ident = _make_identity()
    with pytest.raises(ValueError, match="MUST be exactly 32 bytes"):
        PrincipalDirectory(
            identities=(ident,),
            verification_keys={ident.delegate_id: b"\x00" * 31},  # one byte short
        )


@pytest.mark.unit
def test_principal_directory_rejects_non_uuid_key_id() -> None:
    """PrincipalDirectory enforces UUID key ids at construction."""
    ident = _make_identity()
    with pytest.raises(TypeError, match="MUST be uuid.UUID"):
        PrincipalDirectory(
            identities=(ident,),
            verification_keys={"not-a-uuid": b"\x00" * 32},  # type: ignore[dict-item]
        )


@pytest.mark.unit
def test_principal_directory_public_key_for_returns_none_on_miss() -> None:
    """public_key_for returns None for an id not in the keys mapping."""
    ident = _make_identity()
    _, pub = _make_keypair()
    directory = PrincipalDirectory(
        identities=(ident,),
        verification_keys={ident.delegate_id: pub},
    )
    assert directory.public_key_for(uuid.uuid4()) is None
    assert directory.public_key_for(ident.delegate_id) == pub
