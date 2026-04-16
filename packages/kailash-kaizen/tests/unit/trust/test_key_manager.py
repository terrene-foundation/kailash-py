"""
Unit tests for CARE-005: HSM/KMS Integration.

Tests cover:
- KeyMetadata dataclass
- KeyManagerInterface contract
- InMemoryKeyManager implementation
- AWSKMSKeyManager stub behavior
- Key lifecycle (generate, rotate, revoke)
- Error handling

Test Categories:
1. test_generate_keypair - generates valid Ed25519 keypair
2. test_sign_and_verify - sign with key_id, verify with public key
3. test_sign_wrong_key_fails - verify with wrong key returns False
4. test_rotate_key - old key replaced, new key works
5. test_revoke_key - revoked key raises error on sign
6. test_get_key_metadata - metadata fields correct
7. test_list_keys - lists active keys, excludes revoked
8. test_key_not_found - KeyManagerError raised for unknown key_id
9. test_duplicate_key_id - error on duplicate generation
10. test_aws_kms_stub_raises - AWSKMSKeyManager raises NotImplementedError
"""

from datetime import datetime, timedelta, timezone

import pytest
from kailash.trust.key_manager import (
    AWSKMSKeyManager,
    InMemoryKeyManager,
    KeyManagerError,
    KeyManagerInterface,
    KeyMetadata,
)
from kailash.trust.signing.crypto import NACL_AVAILABLE

# Skip crypto tests if PyNaCl not available
pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not installed")


class TestKeyMetadata:
    """Tests for KeyMetadata dataclass."""

    def test_key_metadata_defaults(self):
        """KeyMetadata has sensible defaults."""
        metadata = KeyMetadata(key_id="test-key")

        assert metadata.key_id == "test-key"
        assert metadata.algorithm == "Ed25519"
        assert metadata.created_at is not None
        assert metadata.expires_at is None
        assert metadata.is_hardware_backed is False
        assert metadata.hsm_slot is None
        assert metadata.is_revoked is False
        assert metadata.revoked_at is None

    def test_key_metadata_is_active_when_not_revoked(self):
        """Active key returns True for is_active()."""
        metadata = KeyMetadata(key_id="test-key")
        assert metadata.is_active() is True

    def test_key_metadata_is_active_when_revoked(self):
        """Revoked key returns False for is_active()."""
        metadata = KeyMetadata(
            key_id="test-key",
            is_revoked=True,
            revoked_at=datetime.now(timezone.utc),
        )
        assert metadata.is_active() is False

    def test_key_metadata_is_active_when_expired(self):
        """Expired key returns False for is_active()."""
        metadata = KeyMetadata(
            key_id="test-key",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert metadata.is_active() is False

    def test_key_metadata_is_active_when_not_yet_expired(self):
        """Non-expired key with expiry returns True for is_active()."""
        metadata = KeyMetadata(
            key_id="test-key",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert metadata.is_active() is True


class TestInMemoryKeyManagerGenerate:
    """Tests for InMemoryKeyManager key generation."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh InMemoryKeyManager for each test."""
        return InMemoryKeyManager()

    @pytest.mark.asyncio
    async def test_generate_keypair(self, key_manager):
        """test_generate_keypair - generates valid Ed25519 keypair."""
        private_ref, public_key = await key_manager.generate_keypair("agent-001")

        # Keys should be non-empty strings
        assert isinstance(private_ref, str)
        assert isinstance(public_key, str)
        assert len(private_ref) > 0
        assert len(public_key) > 0

        # Should be valid base64
        import base64

        base64.b64decode(private_ref)
        base64.b64decode(public_key)

    @pytest.mark.asyncio
    async def test_generate_keypair_creates_unique_keys(self, key_manager):
        """Each key_id gets unique keys."""
        private1, public1 = await key_manager.generate_keypair("key-1")
        private2, public2 = await key_manager.generate_keypair("key-2")

        assert private1 != private2
        assert public1 != public2

    @pytest.mark.asyncio
    async def test_duplicate_key_id(self, key_manager):
        """test_duplicate_key_id - error on duplicate generation."""
        await key_manager.generate_keypair("agent-001")

        with pytest.raises(KeyManagerError) as exc_info:
            await key_manager.generate_keypair("agent-001")

        assert "already exists" in str(exc_info.value)
        assert exc_info.value.key_id == "agent-001"
        assert exc_info.value.operation == "generate_keypair"


class TestInMemoryKeyManagerSign:
    """Tests for InMemoryKeyManager signing and verification."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh InMemoryKeyManager for each test."""
        return InMemoryKeyManager()

    @pytest.mark.asyncio
    async def test_sign_and_verify(self, key_manager):
        """test_sign_and_verify - sign with key_id, verify with public key."""
        private_ref, public_key = await key_manager.generate_keypair("agent-001")

        payload = "test payload"
        signature = await key_manager.sign(payload, "agent-001")

        # Signature should be valid base64
        assert isinstance(signature, str)
        assert len(signature) > 0

        # Verification should pass
        is_valid = await key_manager.verify(payload, signature, public_key)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_sign_wrong_key_fails(self, key_manager):
        """test_sign_wrong_key_fails - verify with wrong key returns False."""
        _, public_key1 = await key_manager.generate_keypair("agent-001")
        _, public_key2 = await key_manager.generate_keypair("agent-002")

        payload = "test payload"
        signature = await key_manager.sign(payload, "agent-001")

        # Verify with wrong public key should fail
        is_valid = await key_manager.verify(payload, signature, public_key2)
        assert is_valid is False

        # Verify with correct public key should pass
        is_valid = await key_manager.verify(payload, signature, public_key1)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_sign_tampered_payload_fails(self, key_manager):
        """Tampered payload fails verification."""
        _, public_key = await key_manager.generate_keypair("agent-001")

        signature = await key_manager.sign("original payload", "agent-001")
        is_valid = await key_manager.verify("tampered payload", signature, public_key)

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_key_not_found(self, key_manager):
        """test_key_not_found - KeyManagerError raised for unknown key_id."""
        with pytest.raises(KeyManagerError) as exc_info:
            await key_manager.sign("test", "nonexistent-key")

        assert "not found" in str(exc_info.value)
        assert exc_info.value.key_id == "nonexistent-key"
        assert exc_info.value.operation == "sign"


class TestInMemoryKeyManagerRotate:
    """Tests for InMemoryKeyManager key rotation."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh InMemoryKeyManager for each test."""
        return InMemoryKeyManager()

    @pytest.mark.asyncio
    async def test_rotate_key(self, key_manager):
        """test_rotate_key - old key replaced, new key works."""
        # Generate initial key
        old_private, old_public = await key_manager.generate_keypair("agent-001")

        # Sign with old key
        old_signature = await key_manager.sign("test payload", "agent-001")

        # Rotate the key
        new_private, new_public = await key_manager.rotate_key("agent-001")

        # New keys should be different
        assert new_private != old_private
        assert new_public != old_public

        # New key should work for signing
        new_signature = await key_manager.sign("test payload", "agent-001")
        is_valid = await key_manager.verify("test payload", new_signature, new_public)
        assert is_valid is True

        # Old signature should still verify with old public key (grace period)
        is_valid = await key_manager.verify("test payload", old_signature, old_public)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_rotate_nonexistent_key_fails(self, key_manager):
        """Rotating nonexistent key raises error."""
        with pytest.raises(KeyManagerError) as exc_info:
            await key_manager.rotate_key("nonexistent-key")

        assert "not found" in str(exc_info.value)
        assert exc_info.value.operation == "rotate_key"

    @pytest.mark.asyncio
    async def test_rotate_key_updates_metadata(self, key_manager):
        """Rotation updates key metadata."""
        await key_manager.generate_keypair("agent-001")
        original_metadata = await key_manager.get_key_metadata("agent-001")
        original_created = original_metadata.created_at

        # Small delay to ensure different timestamp
        import time

        time.sleep(0.01)

        await key_manager.rotate_key("agent-001")
        new_metadata = await key_manager.get_key_metadata("agent-001")

        # Created_at should be updated
        assert new_metadata.created_at > original_created
        # rotated_from should be set
        assert new_metadata.rotated_from is not None


class TestInMemoryKeyManagerRevoke:
    """Tests for InMemoryKeyManager key revocation."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh InMemoryKeyManager for each test."""
        return InMemoryKeyManager()

    @pytest.mark.asyncio
    async def test_revoke_key(self, key_manager):
        """test_revoke_key - revoked key raises error on sign."""
        await key_manager.generate_keypair("agent-001")

        # Key should work before revocation
        signature = await key_manager.sign("test", "agent-001")
        assert len(signature) > 0

        # Revoke the key
        await key_manager.revoke_key("agent-001")

        # Key should not work after revocation
        with pytest.raises(KeyManagerError) as exc_info:
            await key_manager.sign("test", "agent-001")

        assert "revoked" in str(exc_info.value).lower()
        assert exc_info.value.key_id == "agent-001"

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_key_fails(self, key_manager):
        """Revoking nonexistent key raises error."""
        with pytest.raises(KeyManagerError) as exc_info:
            await key_manager.revoke_key("nonexistent-key")

        assert "not found" in str(exc_info.value)
        assert exc_info.value.operation == "revoke_key"

    @pytest.mark.asyncio
    async def test_revoke_key_updates_metadata(self, key_manager):
        """Revocation updates key metadata."""
        await key_manager.generate_keypair("agent-001")
        await key_manager.revoke_key("agent-001")

        metadata = await key_manager.get_key_metadata("agent-001")
        assert metadata.is_revoked is True
        assert metadata.revoked_at is not None
        assert metadata.is_active() is False


class TestInMemoryKeyManagerMetadata:
    """Tests for InMemoryKeyManager metadata operations."""

    @pytest.fixture
    def key_manager(self):
        """Create a fresh InMemoryKeyManager for each test."""
        return InMemoryKeyManager()

    @pytest.mark.asyncio
    async def test_get_key_metadata(self, key_manager):
        """test_get_key_metadata - metadata fields correct."""
        await key_manager.generate_keypair("agent-001")
        metadata = await key_manager.get_key_metadata("agent-001")

        assert metadata is not None
        assert metadata.key_id == "agent-001"
        assert metadata.algorithm == "Ed25519"
        assert metadata.created_at is not None
        assert isinstance(metadata.created_at, datetime)
        assert metadata.is_hardware_backed is False
        assert metadata.hsm_slot is None
        assert metadata.is_revoked is False

    @pytest.mark.asyncio
    async def test_get_key_metadata_nonexistent(self, key_manager):
        """Nonexistent key returns None."""
        metadata = await key_manager.get_key_metadata("nonexistent")
        assert metadata is None

    @pytest.mark.asyncio
    async def test_list_keys(self, key_manager):
        """test_list_keys - lists active keys, excludes revoked."""
        # Create several keys
        await key_manager.generate_keypair("key-1")
        await key_manager.generate_keypair("key-2")
        await key_manager.generate_keypair("key-3")

        # Revoke one key
        await key_manager.revoke_key("key-2")

        # List active keys only
        active_keys = await key_manager.list_keys(active_only=True)
        active_ids = {k.key_id for k in active_keys}

        assert "key-1" in active_ids
        assert "key-2" not in active_ids  # Revoked
        assert "key-3" in active_ids

        # List all keys including revoked
        all_keys = await key_manager.list_keys(active_only=False)
        all_ids = {k.key_id for k in all_keys}

        assert "key-1" in all_ids
        assert "key-2" in all_ids
        assert "key-3" in all_ids

    @pytest.mark.asyncio
    async def test_list_keys_empty(self, key_manager):
        """Empty key manager returns empty list."""
        keys = await key_manager.list_keys()
        assert keys == []


class TestInMemoryKeyManagerBackwardCompat:
    """Tests for backward compatibility with TrustKeyManager."""

    def test_register_key(self):
        """register_key works for backward compatibility.

        Note: The original test relied on a public ``get_key()`` accessor.
        That accessor was removed as a hardening measure -- returning raw
        private-key material from a public API is a key-exfiltration
        vector. The equivalent behavior is now verified through the safe
        surfaces: ``has_key()`` confirms registration, and
        ``sign_with_key()`` proves the registered key is usable.
        """
        key_manager = InMemoryKeyManager()

        # Generate a test key
        from kailash.trust.signing.crypto import generate_keypair

        private_key, _ = generate_keypair()

        # Register it
        key_manager.register_key("legacy-key", private_key)

        # Should be retrievable via the safe API surface
        assert key_manager.has_key("legacy-key") is True
        # And actually usable for signing (proves the stored material is intact)
        signature = key_manager.sign_with_key("legacy-key", "test payload")
        assert isinstance(signature, str) and len(signature) > 0

    def test_get_key_nonexistent(self):
        """has_key returns False for nonexistent key.

        Replaces the original ``get_key("nonexistent") is None`` check.
        ``get_key`` was removed (see ``test_register_key``); ``has_key``
        is the safe public equivalent.
        """
        key_manager = InMemoryKeyManager()
        assert key_manager.has_key("nonexistent") is False

    @pytest.mark.asyncio
    async def test_registered_key_can_sign(self):
        """Registered key can be used for signing."""
        key_manager = InMemoryKeyManager()

        from kailash.trust.signing.crypto import generate_keypair

        private_key, public_key = generate_keypair()

        key_manager.register_key("legacy-key", private_key)

        signature = await key_manager.sign("test", "legacy-key")
        is_valid = await key_manager.verify("test", signature, public_key)

        assert is_valid is True


class TestAWSKMSKeyManager:
    """Tests for AWSKMSKeyManager.

    AWSKMSKeyManager is a full boto3-backed implementation (not a stub).
    It uses AWS KMS ECDSA P-256 for signing (Ed25519 is unavailable in KMS).
    These tests verify the init-time contract against both the injected-
    client and ambient-boto3 paths; operational methods (generate_keypair,
    sign, verify, rotate_key, revoke_key, list_keys) are covered by the
    integration suite which runs against real KMS or moto.
    """

    def test_init_accepts_kms_client(self):
        """Can be initialized with an injected KMS client (DI path)."""
        # Injected client bypasses the boto3 import entirely -- this is
        # the path tests and dependency-injected callers use.
        mock_client = object()
        key_manager = AWSKMSKeyManager(kms_client=mock_client)
        assert key_manager._kms_client is mock_client

    def test_init_without_client_requires_boto3(self):
        """When no client is injected, boto3 must be available.

        Production behavior in src/kailash/trust/key_manager.py
        ``AWSKMSKeyManager.__init__``: if ``kms_client is None`` and
        boto3 is not importable, raise ``ImportError`` naming the
        missing extra. This is the fail-loud contract -- silent
        ``_kms_client = None`` would defer the failure to the first
        operational call with a worse error.
        """
        try:
            import boto3  # noqa: F401
        except ImportError:
            with pytest.raises(ImportError, match="boto3 is required"):
                AWSKMSKeyManager()
        else:
            # boto3 present: init succeeds and wires a real KMS client
            key_manager = AWSKMSKeyManager()
            assert key_manager._kms_client is not None

    def test_init_stores_pending_deletion_days(self):
        """The ``pending_deletion_days`` argument is persisted on the instance."""
        key_manager = AWSKMSKeyManager(kms_client=object(), pending_deletion_days=14)
        assert key_manager._pending_deletion_days == 14

    def test_init_empty_state_collections(self):
        """A fresh manager starts with empty key_arns / public_keys / metadata."""
        key_manager = AWSKMSKeyManager(kms_client=object())
        assert key_manager._key_arns == {}
        assert key_manager._public_keys == {}
        assert key_manager._metadata == {}


class TestKeyManagerInterface:
    """Tests for KeyManagerInterface contract."""

    def test_inmemory_implements_interface(self):
        """InMemoryKeyManager is a proper subclass."""
        key_manager = InMemoryKeyManager()
        assert isinstance(key_manager, KeyManagerInterface)

    def test_awskms_implements_interface(self):
        """AWSKMSKeyManager is a proper subclass.

        Uses the injected-client path so the test does not require boto3
        to be installed in the unit test environment. The interface
        check is about type hierarchy, not runtime behavior.
        """
        key_manager = AWSKMSKeyManager(kms_client=object())
        assert isinstance(key_manager, KeyManagerInterface)


class TestKeyManagerError:
    """Tests for KeyManagerError exception."""

    def test_error_with_key_id(self):
        """Error captures key_id."""
        error = KeyManagerError(
            "Key not found",
            key_id="agent-001",
            operation="sign",
        )

        assert error.key_id == "agent-001"
        assert error.operation == "sign"
        assert "Key not found" in str(error)

    def test_error_details(self):
        """Error includes details dict."""
        error = KeyManagerError(
            "Test error",
            key_id="key-1",
            operation="generate",
        )

        assert error.details["key_id"] == "key-1"
        assert error.details["operation"] == "generate"

    def test_error_inherits_from_trust_error(self):
        """KeyManagerError inherits from TrustError."""
        from kailash.trust.exceptions import TrustError

        error = KeyManagerError("Test")
        assert isinstance(error, TrustError)


class TestInMemoryKeyManagerSecurityMethods:
    """
    Tests for CARE-047: InMemoryKeyManager security methods.

    These tests verify that private keys are not accidentally exposed via:
    - repr() output
    - str() output
    - pickle serialization
    - state serialization (__getstate__)
    """

    @pytest.fixture
    def key_manager_with_keys(self):
        """Create an InMemoryKeyManager loaded with two known keypairs.

        Uses ``register_key`` with freshly generated keypairs so each test
        knows the exact base64-encoded private-key string that landed in
        ``_keys``. This is what allows the repr/str tests to assert the
        known secret value is absent from the representation without
        relying on the removed public ``get_key()`` accessor. The public
        half of each pair is also stored under ``_public_keys`` so the
        later ``test_key_manager_still_functional_after_security_methods``
        test can verify signatures using ``get_public_key()``.
        """
        from kailash.trust.signing.crypto import generate_keypair

        key_manager = InMemoryKeyManager()
        private1, public1 = generate_keypair()
        private2, public2 = generate_keypair()
        key_manager.register_key("test-key-1", private1)
        key_manager.register_key("test-key-2", private2)
        # register_key only populates _keys / _metadata; populate _public_keys
        # directly so get_public_key() works the same as a generate_keypair()
        # path would have provided.
        key_manager._public_keys["test-key-1"] = public1
        key_manager._public_keys["test-key-2"] = public2
        # Attach known private-key strings to the fixture for test assertions;
        # this is test-only metadata, not a production access path.
        key_manager._test_private_keys = {
            "test-key-1": private1,
            "test-key-2": private2,
        }
        return key_manager

    def test_repr_does_not_expose_keys(self, key_manager_with_keys):
        """repr() should show key count but not key material."""
        representation = repr(key_manager_with_keys)

        # Should contain the class name and key count
        assert "InMemoryKeyManager" in representation
        assert "2 keys" in representation

        # Should NOT contain any base64 key material (keys are long base64 strings)
        # Private keys are typically 64+ bytes when base64 encoded
        assert "==" not in representation  # Base64 padding
        # Check that the actual registered private-key strings are absent
        for private_key in key_manager_with_keys._test_private_keys.values():
            assert private_key not in representation

    def test_str_does_not_expose_keys(self, key_manager_with_keys):
        """str() should show key count but not key material."""
        string_rep = str(key_manager_with_keys)

        # Should contain the class name and key count
        assert "InMemoryKeyManager" in string_rep
        assert "2 keys" in string_rep

        # Should NOT contain any base64 key material
        assert "==" not in string_rep  # Base64 padding
        # Check that the actual registered private-key strings are absent
        for private_key in key_manager_with_keys._test_private_keys.values():
            assert private_key not in string_rep

    def test_pickle_raises_type_error(self, key_manager_with_keys):
        """pickle.dumps() should raise TypeError to prevent serialization."""
        import pickle

        with pytest.raises(TypeError) as exc_info:
            pickle.dumps(key_manager_with_keys)

        assert "cannot be pickled" in str(exc_info.value)
        assert "private key material" in str(exc_info.value)

    def test_pickle_with_protocol_raises_type_error(self, key_manager_with_keys):
        """pickle.dumps() with any protocol should raise TypeError."""
        import pickle

        # Test multiple pickle protocols
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with pytest.raises(TypeError) as exc_info:
                pickle.dumps(key_manager_with_keys, protocol=protocol)

            assert "cannot be pickled" in str(exc_info.value)

    def test_getstate_raises_type_error(self, key_manager_with_keys):
        """__getstate__() should raise TypeError directly."""
        with pytest.raises(TypeError) as exc_info:
            key_manager_with_keys.__getstate__()

        assert "cannot be serialized" in str(exc_info.value)
        assert "private key material" in str(exc_info.value)

    def test_setstate_raises_type_error(self, key_manager_with_keys):
        """__setstate__() should raise TypeError."""
        with pytest.raises(TypeError) as exc_info:
            key_manager_with_keys.__setstate__({})

        assert "cannot be deserialized" in str(exc_info.value)

    def test_key_manager_still_functional_after_security_methods(
        self, key_manager_with_keys
    ):
        """Key manager should still work normally after adding security methods."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            # Should be able to sign and verify
            signature = loop.run_until_complete(
                key_manager_with_keys.sign("test payload", "test-key-1")
            )
            assert len(signature) > 0

            public_key = key_manager_with_keys.get_public_key("test-key-1")
            is_valid = loop.run_until_complete(
                key_manager_with_keys.verify("test payload", signature, public_key)
            )
            assert is_valid is True

            # Should be able to generate new keys
            private, public = loop.run_until_complete(
                key_manager_with_keys.generate_keypair("test-key-3")
            )
            assert len(private) > 0
            assert len(public) > 0

            # Should be able to get metadata
            metadata = loop.run_until_complete(
                key_manager_with_keys.get_key_metadata("test-key-1")
            )
            assert metadata is not None
            assert metadata.key_id == "test-key-1"
        finally:
            loop.close()

    def test_empty_key_manager_repr(self):
        """repr() works correctly for empty key manager."""
        key_manager = InMemoryKeyManager()
        representation = repr(key_manager)

        assert "InMemoryKeyManager" in representation
        assert "0 keys" in representation

    def test_empty_key_manager_str(self):
        """str() works correctly for empty key manager."""
        key_manager = InMemoryKeyManager()
        string_rep = str(key_manager)

        assert "InMemoryKeyManager" in string_rep
        assert "0 keys" in string_rep
