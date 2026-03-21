# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Encryption-at-rest utilities for TrustPlane records.

Provides AES-256-GCM encryption and decryption with HKDF-SHA256
key derivation. The ciphertext format is ``nonce (12 bytes) || ciphertext``.
"""

from __future__ import annotations

import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from kailash.trust.plane.exceptions import TrustDecryptionError

logger = logging.getLogger(__name__)

__all__ = [
    "TrustDecryptionError",
    "derive_encryption_key",
    "encrypt_record",
    "decrypt_record",
]

_NONCE_SIZE = 12
_KEY_SIZE = 32
_HKDF_INFO = b"trustplane-encryption-v1"


def derive_encryption_key(private_key_bytes: bytes) -> bytes:
    """Derive a 32-byte AES-256 key from arbitrary key material using HKDF-SHA256.

    Args:
        private_key_bytes: Raw key material (must be non-empty).

    Returns:
        A 32-byte derived key suitable for AES-256-GCM.

    Raises:
        ValueError: If *private_key_bytes* is empty.
    """
    if not private_key_bytes:
        raise ValueError("derive_encryption_key requires non-empty key material")

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=None,
        info=_HKDF_INFO,
    )
    return hkdf.derive(private_key_bytes)


def encrypt_record(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt *plaintext* with AES-256-GCM, returning ``nonce || ciphertext``.

    A fresh 12-byte random nonce is generated for every call.

    Args:
        plaintext: Data to encrypt (may be empty).
        key: 32-byte AES-256 key.

    Returns:
        The nonce prepended to the GCM ciphertext (includes the 16-byte tag).

    Raises:
        TypeError: If *plaintext* or *key* is not ``bytes``.
        ValueError: If *key* is not exactly 32 bytes.
    """
    if not isinstance(plaintext, bytes):
        raise TypeError(f"plaintext must be bytes, got {type(plaintext).__name__}")
    if not isinstance(key, bytes):
        raise TypeError(f"key must be bytes, got {type(key).__name__}")
    if len(key) != _KEY_SIZE:
        raise ValueError(f"key must be {_KEY_SIZE} bytes, got {len(key)}")

    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    logger.debug("Encrypted %d bytes of plaintext", len(plaintext))
    return nonce + ciphertext


def decrypt_record(ciphertext: bytes, key: bytes) -> bytes:
    """Decrypt an AES-256-GCM record previously produced by :func:`encrypt_record`.

    Args:
        ciphertext: The ``nonce || ciphertext`` blob.
        key: 32-byte AES-256 key (must match the key used for encryption).

    Returns:
        The original plaintext.

    Raises:
        TypeError: If *ciphertext* or *key* is not ``bytes``.
        ValueError: If *key* is not exactly 32 bytes.
        TrustDecryptionError: If decryption fails (wrong key, tampered data,
            or truncated ciphertext).
    """
    if not isinstance(ciphertext, bytes):
        raise TypeError(f"ciphertext must be bytes, got {type(ciphertext).__name__}")
    if not isinstance(key, bytes):
        raise TypeError(f"key must be bytes, got {type(key).__name__}")
    if len(key) != _KEY_SIZE:
        raise ValueError(f"key must be {_KEY_SIZE} bytes, got {len(key)}")

    if len(ciphertext) < _NONCE_SIZE + 16:
        raise TrustDecryptionError(
            f"Ciphertext too short ({len(ciphertext)} bytes); "
            f"minimum is {_NONCE_SIZE + 16} bytes (nonce + GCM tag)"
        )

    nonce = ciphertext[:_NONCE_SIZE]
    data = ciphertext[_NONCE_SIZE:]

    try:
        plaintext = AESGCM(key).decrypt(nonce, data, None)
    except InvalidTag:
        raise TrustDecryptionError(
            "Decryption failed: invalid authentication tag "
            "(wrong key or tampered ciphertext)"
        )

    logger.debug("Decrypted %d bytes of plaintext", len(plaintext))
    return plaintext
