# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Pluggable key management for TrustPlane (TODO-23).

Defines a protocol-based interface for HSM/KMS key management backends
and provides a local file-based implementation using Ed25519.

Backends:
- LocalFileKeyManager: Ed25519 keys stored in .trust-plane/keys/
- AwsKmsKeyManager: AWS KMS with ECDSA P-256 (see key_managers.aws_kms)
- AzureKeyVaultKeyManager: Azure Key Vault with EC P-256 (see key_managers.azure_keyvault)
- VaultKeyManager: HashiCorp Vault Transit engine (see key_managers.vault)

Example:
    from trustplane.key_manager import LocalFileKeyManager

    manager = LocalFileKeyManager(key_dir=Path(".trust-plane/keys"))
    signature = manager.sign(b"data to sign")
    pub_key = manager.get_public_key()
    print(manager.key_id())       # hex fingerprint
    print(manager.algorithm())    # "ed25519"
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

logger = logging.getLogger(__name__)

__all__ = [
    "TrustPlaneKeyManager",
    "LocalFileKeyManager",
]


@runtime_checkable
class TrustPlaneKeyManager(Protocol):
    """Protocol for pluggable TrustPlane key management backends.

    All key managers must implement these four methods. The protocol
    is runtime-checkable, allowing isinstance() verification.

    Method signatures:
        sign(data: bytes) -> bytes
        get_public_key() -> bytes
        key_id() -> str
        algorithm() -> str  (e.g. "ed25519", "ecdsa-p256")
    """

    def sign(self, data: bytes) -> bytes:
        """Sign data and return the raw signature bytes.

        Args:
            data: The bytes to sign.

        Returns:
            Raw signature bytes (64 bytes for Ed25519, variable for ECDSA).

        Raises:
            TrustPlaneError: If signing fails.
        """
        ...

    def get_public_key(self) -> bytes:
        """Return the raw public key bytes.

        Returns:
            Raw public key bytes (32 bytes for Ed25519).
        """
        ...

    def key_id(self) -> str:
        """Return a hex fingerprint identifying this key.

        Returns:
            Hex string of the SHA-256 hash of the public key bytes.
        """
        ...

    def algorithm(self) -> str:
        """Return the signing algorithm name.

        Returns:
            Algorithm identifier string (e.g. "ed25519", "ecdsa-p256").
        """
        ...


class LocalFileKeyManager:
    """Ed25519 key manager backed by local filesystem.

    Loads an existing Ed25519 private key from key_dir, or generates
    a new keypair if none exists. Keys are stored in PEM format with
    restricted file permissions (0o600 for private key).

    Args:
        key_dir: Directory for key storage. Created if it does not exist.

    File layout:
        key_dir/
            private.pem   # Ed25519 private key (PEM, 0o600)
            public.pem    # Ed25519 public key (PEM, 0o644)
    """

    _PRIVATE_KEY_FILE = "private.pem"
    _PUBLIC_KEY_FILE = "public.pem"

    def __init__(self, key_dir: Path) -> None:
        self._key_dir = Path(key_dir)
        self._key_dir.mkdir(parents=True, exist_ok=True)

        priv_path = self._key_dir / self._PRIVATE_KEY_FILE

        if priv_path.exists():
            logger.info("Loading existing Ed25519 key from %s", self._key_dir)
            self._private_key = self._load_private_key(priv_path)
        else:
            logger.info("Generating new Ed25519 keypair in %s", self._key_dir)
            self._private_key = Ed25519PrivateKey.generate()
            self._save_keys()

        self._public_key: Ed25519PublicKey = self._private_key.public_key()

    def sign(self, data: bytes) -> bytes:
        """Sign data with the Ed25519 private key.

        Args:
            data: Bytes to sign.

        Returns:
            64-byte Ed25519 signature.
        """
        return self._private_key.sign(data)

    def get_public_key(self) -> bytes:
        """Return the raw 32-byte Ed25519 public key.

        Returns:
            32-byte raw public key.
        """
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def key_id(self) -> str:
        """Return SHA-256 hex digest of the raw public key bytes.

        Returns:
            64-character hex string fingerprint.
        """
        return hashlib.sha256(self.get_public_key()).hexdigest()

    def algorithm(self) -> str:
        """Return the algorithm identifier.

        Returns:
            Always "ed25519" for this manager.
        """
        return "ed25519"

    def _load_private_key(self, path: Path) -> Ed25519PrivateKey:
        """Load an Ed25519 private key from a PEM file.

        Uses O_NOFOLLOW where available to prevent symlink attacks
        (consistent with trust-plane security patterns).

        Args:
            path: Path to the PEM-encoded private key file.

        Returns:
            The loaded Ed25519PrivateKey.

        Raises:
            ValueError: If the file does not contain a valid Ed25519 private key.
        """
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd = os.open(str(path), flags)
        try:
            f = os.fdopen(fd, "rb")
        except Exception:
            os.close(fd)
            raise
        with f:
            pem_data = f.read()

        private_key = serialization.load_pem_private_key(pem_data, password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError(
                f"Expected Ed25519 private key, got {type(private_key).__name__}"
            )
        return private_key

    def _save_keys(self) -> None:
        """Persist the keypair to PEM files with restricted permissions.

        Private key is created with 0o600 permissions (owner read/write only).
        Public key is created with 0o644 permissions.
        O_NOFOLLOW is used where available to prevent symlink attacks.
        """
        priv_path = self._key_dir / self._PRIVATE_KEY_FILE
        pub_path = self._key_dir / self._PUBLIC_KEY_FILE

        priv_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        pub_pem = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Write private key with restricted permissions and symlink protection
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(str(priv_path), flags, 0o600)
        try:
            os.write(fd, priv_pem)
        finally:
            os.close(fd)

        # Write public key with standard read permissions
        pub_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            pub_flags |= os.O_NOFOLLOW
        pub_fd = os.open(str(pub_path), pub_flags, 0o644)
        try:
            os.write(pub_fd, pub_pem)
        finally:
            os.close(pub_fd)

        logger.debug("Saved Ed25519 keypair to %s", self._key_dir)
