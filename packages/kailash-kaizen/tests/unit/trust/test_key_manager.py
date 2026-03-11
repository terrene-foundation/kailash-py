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
from kaizen.trust.crypto import NACL_AVAILABLE
from kaizen.trust.key_manager import (
    AWSKMSKeyManager,
    InMemoryKeyManager,
    KeyManagerError,
    KeyManagerInterface,
    KeyMetadata,
)

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
        """register_key works for backward compatibility."""
        key_manager = InMemoryKeyManager()

        # Generate a test key
        from kaizen.trust.crypto import generate_keypair

        private_key, _ = generate_keypair()

        # Register it
        key_manager.register_key("legacy-key", private_key)

        # Should be retrievable
        assert key_manager.get_key("legacy-key") == private_key

    def test_get_key_nonexistent(self):
        """get_key returns None for nonexistent key."""
        key_manager = InMemoryKeyManager()
        assert key_manager.get_key("nonexistent") is None

    @pytest.mark.asyncio
    async def test_registered_key_can_sign(self):
        """Registered key can be used for signing."""
        key_manager = InMemoryKeyManager()

        from kaizen.trust.crypto import generate_keypair

        private_key, public_key = generate_keypair()

        key_manager.register_key("legacy-key", private_key)

        signature = await key_manager.sign("test", "legacy-key")
        is_valid = await key_manager.verify("test", signature, public_key)

        assert is_valid is True


class TestAWSKMSKeyManager:
    """Tests for AWSKMSKeyManager stub."""

    def test_init_accepts_kms_client(self):
        """Can be initialized with a KMS client."""
        # Mock client
        mock_client = object()
        key_manager = AWSKMSKeyManager(kms_client=mock_client)
        assert key_manager._kms_client == mock_client

    def test_init_without_client(self):
        """Can be initialized without a client."""
        key_manager = AWSKMSKeyManager()
        assert key_manager._kms_client is None

    @pytest.mark.asyncio
    async def test_aws_kms_stub_raises(self):
        """test_aws_kms_stub_raises - AWSKMSKeyManager raises NotImplementedError."""
        key_manager = AWSKMSKeyManager()

        # generate_keypair
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.generate_keypair("key-1")
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "create_key" in str(exc_info.value)

        # sign
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.sign("payload", "key-1")
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "sign" in str(exc_info.value).lower()

        # verify
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.verify("payload", "sig", "pubkey")
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "verify" in str(exc_info.value).lower()

        # rotate_key
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.rotate_key("key-1")
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "schedule_key_deletion" in str(exc_info.value)

        # revoke_key
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.revoke_key("key-1")
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "schedule_key_deletion" in str(exc_info.value)

        # get_key_metadata
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.get_key_metadata("key-1")
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "describe_key" in str(exc_info.value)

        # list_keys
        with pytest.raises(NotImplementedError) as exc_info:
            await key_manager.list_keys()
        assert "AWS KMS integration not yet implemented" in str(exc_info.value)
        assert "list_keys" in str(exc_info.value)


class TestKeyManagerInterface:
    """Tests for KeyManagerInterface contract."""

    def test_inmemory_implements_interface(self):
        """InMemoryKeyManager is a proper subclass."""
        key_manager = InMemoryKeyManager()
        assert isinstance(key_manager, KeyManagerInterface)

    def test_awskms_implements_interface(self):
        """AWSKMSKeyManager is a proper subclass."""
        key_manager = AWSKMSKeyManager()
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
        from kaizen.trust.exceptions import TrustError

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
        """Create an InMemoryKeyManager with some keys loaded."""
        import asyncio

        key_manager = InMemoryKeyManager()
        # Use run to execute async in sync context for fixture
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(key_manager.generate_keypair("test-key-1"))
            loop.run_until_complete(key_manager.generate_keypair("test-key-2"))
        finally:
            loop.close()
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
        # Check that actual key values are not in the repr
        for key_id in ["test-key-1", "test-key-2"]:
            private_key = key_manager_with_keys.get_key(key_id)
            if private_key:
                assert private_key not in representation

    def test_str_does_not_expose_keys(self, key_manager_with_keys):
        """str() should show key count but not key material."""
        string_rep = str(key_manager_with_keys)

        # Should contain the class name and key count
        assert "InMemoryKeyManager" in string_rep
        assert "2 keys" in string_rep

        # Should NOT contain any base64 key material
        assert "==" not in string_rep  # Base64 padding
        # Check that actual key values are not in the str
        for key_id in ["test-key-1", "test-key-2"]:
            private_key = key_manager_with_keys.get_key(key_id)
            if private_key:
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
