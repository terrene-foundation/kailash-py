# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for encryption-at-rest utilities (TODO-26).

Covers AES-256-GCM encryption/decryption, HKDF key derivation,
and the TrustDecryptionError exception.
"""

from __future__ import annotations

import os

import pytest

from kailash.trust.plane.encryption.crypto_utils import (
    TrustDecryptionError,
    decrypt_record,
    derive_encryption_key,
    encrypt_record,
)
from kailash.trust.plane.exceptions import TrustPlaneError


class TestTrustDecryptionError:
    """TrustDecryptionError must fit into the exception hierarchy."""

    def test_is_subclass_of_trustplane_error(self) -> None:
        assert issubclass(TrustDecryptionError, TrustPlaneError)

    def test_can_be_caught_as_trustplane_error(self) -> None:
        with pytest.raises(TrustPlaneError):
            raise TrustDecryptionError("decryption failed")

    def test_message_preserved(self) -> None:
        exc = TrustDecryptionError("bad ciphertext")
        assert str(exc) == "bad ciphertext"


class TestDeriveEncryptionKey:
    """HKDF-SHA256 key derivation produces a 32-byte AES-256 key."""

    def test_produces_32_bytes(self) -> None:
        key_material = os.urandom(32)
        derived = derive_encryption_key(key_material)
        assert isinstance(derived, bytes)
        assert len(derived) == 32

    def test_deterministic_for_same_input(self) -> None:
        key_material = b"fixed-test-key-material-1234567890"
        k1 = derive_encryption_key(key_material)
        k2 = derive_encryption_key(key_material)
        assert k1 == k2

    def test_different_inputs_produce_different_keys(self) -> None:
        k1 = derive_encryption_key(b"key-material-alpha")
        k2 = derive_encryption_key(b"key-material-bravo")
        assert k1 != k2

    def test_short_input_accepted(self) -> None:
        """HKDF handles input key material of any length >= 1 byte."""
        derived = derive_encryption_key(b"x")
        assert len(derived) == 32

    def test_empty_input_raises(self) -> None:
        """Empty key material must raise ValueError, not silently succeed."""
        with pytest.raises(ValueError, match="key material"):
            derive_encryption_key(b"")


class TestEncryptDecryptRoundTrip:
    """AES-256-GCM encrypt/decrypt round-trip."""

    @pytest.fixture()
    def key(self) -> bytes:
        return derive_encryption_key(os.urandom(32))

    def test_round_trip(self, key: bytes) -> None:
        plaintext = b"hello trust-plane"
        ciphertext = encrypt_record(plaintext, key)
        recovered = decrypt_record(ciphertext, key)
        assert recovered == plaintext

    def test_empty_plaintext_round_trip(self, key: bytes) -> None:
        """Empty plaintext must encrypt and decrypt without error."""
        ciphertext = encrypt_record(b"", key)
        recovered = decrypt_record(ciphertext, key)
        assert recovered == b""

    def test_large_plaintext_round_trip(self, key: bytes) -> None:
        plaintext = os.urandom(1_000_000)  # 1 MB
        ciphertext = encrypt_record(plaintext, key)
        recovered = decrypt_record(ciphertext, key)
        assert recovered == plaintext

    def test_ciphertext_longer_than_plaintext(self, key: bytes) -> None:
        """Ciphertext includes 12-byte nonce + 16-byte GCM tag overhead."""
        plaintext = b"test"
        ciphertext = encrypt_record(plaintext, key)
        # 12 (nonce) + len(plaintext) + 16 (GCM tag) = 32
        assert len(ciphertext) == 12 + len(plaintext) + 16


class TestDecryptionFailures:
    """Wrong keys, truncated ciphertexts, and tampered data must raise TrustDecryptionError."""

    @pytest.fixture()
    def key(self) -> bytes:
        return derive_encryption_key(os.urandom(32))

    def test_wrong_key_raises_trust_decryption_error(self, key: bytes) -> None:
        other_key = derive_encryption_key(os.urandom(32))
        ciphertext = encrypt_record(b"secret", key)
        with pytest.raises(TrustDecryptionError):
            decrypt_record(ciphertext, other_key)

    def test_truncated_ciphertext_raises(self, key: bytes) -> None:
        ciphertext = encrypt_record(b"data", key)
        with pytest.raises(TrustDecryptionError):
            decrypt_record(ciphertext[:10], key)  # shorter than nonce

    def test_tampered_ciphertext_raises(self, key: bytes) -> None:
        ciphertext = bytearray(encrypt_record(b"data", key))
        # Flip a byte in the encrypted portion (after the 12-byte nonce)
        ciphertext[15] ^= 0xFF
        with pytest.raises(TrustDecryptionError):
            decrypt_record(bytes(ciphertext), key)

    def test_empty_ciphertext_raises(self, key: bytes) -> None:
        with pytest.raises(TrustDecryptionError):
            decrypt_record(b"", key)


class TestNonceUniqueness:
    """Each encryption call must use a unique random nonce."""

    def test_different_ciphertexts_for_same_plaintext(self) -> None:
        key = derive_encryption_key(os.urandom(32))
        plaintext = b"identical content"
        c1 = encrypt_record(plaintext, key)
        c2 = encrypt_record(plaintext, key)
        assert c1 != c2, (
            "Two encryptions of the same plaintext must differ (nonce uniqueness)"
        )

    def test_nonces_differ(self) -> None:
        key = derive_encryption_key(os.urandom(32))
        c1 = encrypt_record(b"x", key)
        c2 = encrypt_record(b"x", key)
        nonce1 = c1[:12]
        nonce2 = c2[:12]
        assert nonce1 != nonce2


class TestInputValidation:
    """Encryption functions must validate their inputs explicitly."""

    def test_encrypt_rejects_non_bytes_plaintext(self) -> None:
        key = derive_encryption_key(os.urandom(32))
        with pytest.raises(TypeError, match="plaintext"):
            encrypt_record("not bytes", key)  # type: ignore[arg-type]

    def test_encrypt_rejects_non_bytes_key(self) -> None:
        with pytest.raises(TypeError, match="key"):
            encrypt_record(b"data", "not bytes")  # type: ignore[arg-type]

    def test_decrypt_rejects_non_bytes_ciphertext(self) -> None:
        key = derive_encryption_key(os.urandom(32))
        with pytest.raises(TypeError, match="ciphertext"):
            decrypt_record("not bytes", key)  # type: ignore[arg-type]

    def test_decrypt_rejects_non_bytes_key(self) -> None:
        with pytest.raises(TypeError, match="key"):
            decrypt_record(b"data", "not bytes")  # type: ignore[arg-type]

    def test_encrypt_rejects_wrong_key_length(self) -> None:
        with pytest.raises(ValueError, match="key.*32 bytes"):
            encrypt_record(b"data", b"short-key")

    def test_decrypt_rejects_wrong_key_length(self) -> None:
        with pytest.raises(ValueError, match="key.*32 bytes"):
            decrypt_record(b"x" * 28, b"short-key")
