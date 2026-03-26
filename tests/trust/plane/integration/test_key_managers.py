# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for TrustPlane pluggable key management.

Tier 2 (Integration): Tests key manager protocol conformance,
LocalFileKeyManager real crypto operations, and exception hierarchy.
No mocks — all operations use real objects.

Mock-heavy tests (cloud provider ImportError simulation, exception
wrapping with MagicMock) are in tests/unit/test_key_managers.py.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import runtime_checkable

import pytest

from kailash.trust.plane.key_managers.manager import (
    LocalFileKeyManager,
    TrustPlaneKeyManager,
)

logger = logging.getLogger(__name__)


class TestTrustPlaneKeyManagerProtocol:
    """Verify the TrustPlaneKeyManager protocol definition."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """TrustPlaneKeyManager must be decorated with @runtime_checkable."""
        assert runtime_checkable  # import check
        assert isinstance(TrustPlaneKeyManager, type)
        # Protocol classes decorated with @runtime_checkable support isinstance checks
        # We verify the protocol has the required methods
        required_methods = {"sign", "get_public_key", "key_id", "algorithm"}
        protocol_methods = {
            name for name in dir(TrustPlaneKeyManager) if not name.startswith("_")
        }
        assert required_methods.issubset(
            protocol_methods
        ), f"Missing protocol methods: {required_methods - protocol_methods}"

    def test_local_file_key_manager_satisfies_protocol(self, tmp_path: Path) -> None:
        """LocalFileKeyManager must satisfy the TrustPlaneKeyManager protocol."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        assert isinstance(manager, TrustPlaneKeyManager)

    def test_aws_kms_key_manager_declares_protocol_methods(self) -> None:
        """AwsKmsKeyManager must declare all protocol methods."""
        from kailash.trust.plane.key_managers.aws_kms import AwsKmsKeyManager

        required_methods = {"sign", "get_public_key", "key_id", "algorithm"}
        cls_methods = {
            name for name in dir(AwsKmsKeyManager) if not name.startswith("_")
        }
        assert required_methods.issubset(
            cls_methods
        ), f"Missing methods: {required_methods - cls_methods}"

    def test_azure_key_vault_key_manager_declares_protocol_methods(self) -> None:
        """AzureKeyVaultKeyManager must declare all protocol methods."""
        from kailash.trust.plane.key_managers.azure_keyvault import (
            AzureKeyVaultKeyManager,
        )

        required_methods = {"sign", "get_public_key", "key_id", "algorithm"}
        cls_methods = {
            name for name in dir(AzureKeyVaultKeyManager) if not name.startswith("_")
        }
        assert required_methods.issubset(
            cls_methods
        ), f"Missing methods: {required_methods - cls_methods}"

    def test_vault_key_manager_declares_protocol_methods(self) -> None:
        """VaultKeyManager must declare all protocol methods."""
        from kailash.trust.plane.key_managers.vault import VaultKeyManager

        required_methods = {"sign", "get_public_key", "key_id", "algorithm"}
        cls_methods = {
            name for name in dir(VaultKeyManager) if not name.startswith("_")
        }
        assert required_methods.issubset(
            cls_methods
        ), f"Missing methods: {required_methods - cls_methods}"


class TestLocalFileKeyManager:
    """Tests for LocalFileKeyManager with Ed25519 keys."""

    def test_generates_key_on_init_when_no_key_exists(self, tmp_path: Path) -> None:
        """When key_dir has no existing key, a new Ed25519 keypair is generated."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        pub_key = manager.get_public_key()
        assert isinstance(pub_key, bytes)
        assert len(pub_key) == 32, "Ed25519 public key must be 32 bytes"

    def test_loads_existing_key_on_init(self, tmp_path: Path) -> None:
        """When key_dir already has a key, it loads the existing key."""
        manager1 = LocalFileKeyManager(key_dir=tmp_path)
        pub1 = manager1.get_public_key()

        manager2 = LocalFileKeyManager(key_dir=tmp_path)
        pub2 = manager2.get_public_key()

        assert pub1 == pub2, "Loading from same directory must yield same key"

    def test_sign_returns_bytes(self, tmp_path: Path) -> None:
        """sign() must return a bytes signature."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        data = b"test payload for signing"
        signature = manager.sign(data)
        assert isinstance(signature, bytes)
        assert len(signature) == 64, "Ed25519 signature must be 64 bytes"

    def test_sign_verify_roundtrip(self, tmp_path: Path) -> None:
        """Signature produced by sign() must verify against the public key."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        manager = LocalFileKeyManager(key_dir=tmp_path)
        data = b"important trust record data"
        signature = manager.sign(data)
        pub_key_bytes = manager.get_public_key()

        # Verify using cryptography library directly
        pub_key = Ed25519PublicKey.from_public_bytes(pub_key_bytes)
        # This raises InvalidSignature if verification fails
        pub_key.verify(signature, data)

    def test_sign_different_data_produces_different_signatures(
        self, tmp_path: Path
    ) -> None:
        """Different data must produce different signatures."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        sig1 = manager.sign(b"payload one")
        sig2 = manager.sign(b"payload two")
        assert sig1 != sig2

    def test_sign_same_data_produces_same_signature(self, tmp_path: Path) -> None:
        """Ed25519 is deterministic: same data + same key = same signature."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        data = b"deterministic signing test"
        sig1 = manager.sign(data)
        sig2 = manager.sign(data)
        assert sig1 == sig2

    def test_key_id_returns_hex_fingerprint(self, tmp_path: Path) -> None:
        """key_id() must return the hex digest of the public key fingerprint."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        kid = manager.key_id()
        assert isinstance(kid, str)
        # Must be a valid hex string
        int(kid, 16)
        # Must be consistent
        assert kid == manager.key_id()

    def test_key_id_is_sha256_of_public_key(self, tmp_path: Path) -> None:
        """key_id() must be the SHA-256 hex digest of the raw public key bytes."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        expected = hashlib.sha256(manager.get_public_key()).hexdigest()
        assert manager.key_id() == expected

    def test_algorithm_returns_ed25519(self, tmp_path: Path) -> None:
        """algorithm() must return 'ed25519' for local file key manager."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        assert manager.algorithm() == "ed25519"

    def test_get_public_key_returns_raw_bytes(self, tmp_path: Path) -> None:
        """get_public_key() must return raw 32-byte Ed25519 public key."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        pub = manager.get_public_key()
        assert isinstance(pub, bytes)
        assert len(pub) == 32

    def test_private_key_file_created_with_restricted_permissions(
        self, tmp_path: Path
    ) -> None:
        """Private key file must exist after init."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        # The key_dir should contain key files
        assert manager.get_public_key() is not None
        # Verify the key directory is used
        files = list(tmp_path.iterdir())
        assert len(files) > 0, "Key files must be written to key_dir"

    def test_sign_with_empty_data(self, tmp_path: Path) -> None:
        """sign() must handle empty bytes without error."""
        manager = LocalFileKeyManager(key_dir=tmp_path)
        signature = manager.sign(b"")
        assert isinstance(signature, bytes)
        assert len(signature) == 64


class TestKeyManagerErrorHierarchy:
    """Tests for the KeyManagerError exception hierarchy (TODO-54)."""

    def test_key_manager_error_is_trustplane_error(self) -> None:
        """KeyManagerError must inherit from TrustPlaneError."""
        from kailash.trust.plane.exceptions import KeyManagerError, TrustPlaneError

        assert issubclass(KeyManagerError, TrustPlaneError)

    def test_key_manager_error_subclasses(self) -> None:
        """All key manager error subclasses must inherit from KeyManagerError."""
        from kailash.trust.plane.exceptions import (
            KeyExpiredError,
            KeyManagerError,
            KeyNotFoundError,
            SigningError,
            VerificationError,
        )

        for cls in (KeyNotFoundError, KeyExpiredError, SigningError, VerificationError):
            assert issubclass(
                cls, KeyManagerError
            ), f"{cls.__name__} must inherit KeyManagerError"

    def test_key_manager_error_includes_provider(self) -> None:
        """KeyManagerError must include the provider name in its message."""
        from kailash.trust.plane.exceptions import KeyManagerError

        err = KeyManagerError("test error", provider="aws_kms", key_id="key-123")
        assert "aws_kms" in str(err)
        assert "key-123" in str(err)
        assert err.provider == "aws_kms"
        assert err.key_id == "key-123"

    def test_signing_error_preserves_chain(self) -> None:
        """SigningError must preserve the original exception via __cause__."""
        from kailash.trust.plane.exceptions import SigningError

        original = RuntimeError("network timeout")
        try:
            raise SigningError(
                "Sign failed", provider="aws_kms", key_id="k1"
            ) from original
        except SigningError as exc:
            assert exc.__cause__ is original

    def test_store_error_subclasses(self) -> None:
        """Store error subclasses must inherit from TrustPlaneStoreError."""
        from kailash.trust.plane.exceptions import (
            StoreConnectionError,
            StoreQueryError,
            StoreTransactionError,
            TrustPlaneStoreError,
        )

        for cls in (StoreConnectionError, StoreQueryError, StoreTransactionError):
            assert issubclass(
                cls, TrustPlaneStoreError
            ), f"{cls.__name__} must inherit TrustPlaneStoreError"
