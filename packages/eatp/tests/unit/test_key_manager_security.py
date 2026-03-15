# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for key_manager security fixes.

Tests cover three CRITICAL/HIGH security issues:

C2: get_key() exposes raw private key material
    - get_key() must be renamed to _get_key() (private)
    - New has_key(key_id) -> bool for existence checks
    - New sign_with_key(key_id, payload) -> str for signing without exposure
    - _get_key() still works for internal use

C3: register_key() bypasses revocation check
    - A revoked key_id must NOT be re-registerable
    - Revocation must be tracked in _revoked_key_ids: Set[str]
    - Attempting to register a revoked key_id raises KeyManagerError
    - Non-revoked keys can still be registered normally

H7: AWS KMS verify falls back to wrong key
    - When no matching public key ARN is found, must raise KeyManagerError
    - Must NOT fall back to first available ARN
    - Verify with matching public key still works
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from eatp.crypto import generate_keypair, sign
from eatp.key_manager import (
    AWSKMSKeyManager,
    InMemoryKeyManager,
    KeyManagerError,
    KeyMetadata,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_kms_client():
    """Create a mock boto3 KMS client with standard responses."""
    client = MagicMock()

    client.create_key.return_value = {
        "KeyMetadata": {
            "KeyId": "mrk-test-key-id-123",
            "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
            "KeyState": "Enabled",
            "KeyUsage": "SIGN_VERIFY",
            "KeySpec": "ECC_NIST_P256",
            "CreationDate": datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        }
    }

    fake_pub_key_bytes = b"fake-der-encoded-public-key-bytes-for-testing"
    client.get_public_key.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "PublicKey": fake_pub_key_bytes,
        "KeySpec": "ECC_NIST_P256",
        "KeyUsage": "SIGN_VERIFY",
        "SigningAlgorithms": ["ECDSA_SHA_256"],
    }

    fake_signature = b"fake-ecdsa-signature-bytes"
    client.sign.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "Signature": fake_signature,
        "SigningAlgorithm": "ECDSA_SHA_256",
    }

    client.verify.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "SignatureValid": True,
        "SigningAlgorithm": "ECDSA_SHA_256",
    }

    client.schedule_key_deletion.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "DeletionDate": datetime(2026, 1, 22, 10, 30, 0, tzinfo=timezone.utc),
        "KeyState": "PendingDeletion",
        "PendingWindowInDays": 7,
    }

    return client


# ===========================================================================
# C2: get_key() must not expose raw private key material
# ===========================================================================


class TestC2GetKeyPrivateKeyExposure:
    """C2: get_key() exposes raw private key material.

    After the fix:
    - get_key() must no longer exist as a public method
    - _get_key() is the private replacement (internal use only)
    - has_key(key_id) -> bool checks key existence without exposure
    - sign_with_key(key_id, payload) -> str signs without exposing the key
    """

    def test_get_key_public_method_removed(self):
        """The public get_key() method must not exist on InMemoryKeyManager."""
        km = InMemoryKeyManager()
        assert not hasattr(km, "get_key"), (
            "get_key() is a public method that exposes raw private key material. "
            "It must be renamed to _get_key() (private)."
        )

    def test_private_get_key_exists(self):
        """_get_key() must exist as a private method for internal use."""
        km = InMemoryKeyManager()
        assert hasattr(
            km, "_get_key"
        ), "_get_key() must exist as a private method for internal use."

    @pytest.mark.asyncio
    async def test_private_get_key_returns_key_for_valid_id(self):
        """_get_key() returns the private key for a known key_id."""
        km = InMemoryKeyManager()
        private_key, _public_key = await km.generate_keypair("test-key")
        result = km._get_key("test-key")
        assert result == private_key

    def test_private_get_key_returns_none_for_unknown_id(self):
        """_get_key() returns None for an unknown key_id."""
        km = InMemoryKeyManager()
        result = km._get_key("nonexistent")
        assert result is None

    # --- has_key() ---

    def test_has_key_method_exists(self):
        """has_key() must exist as a public method."""
        km = InMemoryKeyManager()
        assert hasattr(
            km, "has_key"
        ), "has_key(key_id) -> bool must exist for safe existence checking."

    @pytest.mark.asyncio
    async def test_has_key_returns_true_for_existing_key(self):
        """has_key() returns True for a key that exists."""
        km = InMemoryKeyManager()
        await km.generate_keypair("test-key")
        assert km.has_key("test-key") is True

    def test_has_key_returns_false_for_missing_key(self):
        """has_key() returns False for a key that does not exist."""
        km = InMemoryKeyManager()
        assert km.has_key("nonexistent") is False

    @pytest.mark.asyncio
    async def test_has_key_returns_true_for_registered_key(self):
        """has_key() returns True for a key registered via register_key()."""
        km = InMemoryKeyManager()
        private_key, _public_key = generate_keypair()
        km.register_key("reg-key", private_key)
        assert km.has_key("reg-key") is True

    # --- sign_with_key() ---

    def test_sign_with_key_method_exists(self):
        """sign_with_key() must exist as a public method."""
        km = InMemoryKeyManager()
        assert hasattr(km, "sign_with_key"), (
            "sign_with_key(key_id, payload) -> str must exist for signing "
            "without exposing the key."
        )

    @pytest.mark.asyncio
    async def test_sign_with_key_produces_valid_signature(self):
        """sign_with_key() produces a signature verifiable with the public key."""
        from eatp.crypto import verify_signature

        km = InMemoryKeyManager()
        _private_key, public_key = await km.generate_keypair("test-key")

        signature = km.sign_with_key("test-key", "test payload")

        assert verify_signature("test payload", signature, public_key)

    def test_sign_with_key_raises_for_unknown_key(self):
        """sign_with_key() raises KeyManagerError for unknown key_id."""
        km = InMemoryKeyManager()
        with pytest.raises(KeyManagerError, match="not found"):
            km.sign_with_key("nonexistent", "payload")

    @pytest.mark.asyncio
    async def test_sign_with_key_raises_for_revoked_key(self):
        """sign_with_key() raises KeyManagerError for revoked key_id."""
        km = InMemoryKeyManager()
        await km.generate_keypair("test-key")
        await km.revoke_key("test-key")

        with pytest.raises(KeyManagerError, match="revoked"):
            km.sign_with_key("test-key", "payload")

    @pytest.mark.asyncio
    async def test_sign_with_key_does_not_return_private_key(self):
        """sign_with_key() returns a signature string, not a private key."""
        km = InMemoryKeyManager()
        private_key, _public_key = await km.generate_keypair("test-key")

        result = km.sign_with_key("test-key", "payload")

        # The result must be a signature, not the private key
        assert result != private_key
        assert isinstance(result, str)


# ===========================================================================
# C3: register_key() must reject revoked key_ids
# ===========================================================================


class TestC3RegisterKeyRevocationBypass:
    """C3: register_key() bypasses revocation check.

    After the fix:
    - Attempting to register a key_id that was previously revoked
      must raise KeyManagerError
    - A _revoked_key_ids: Set[str] must track revoked key_ids
    - revoke_key() must add the key_id to _revoked_key_ids
    - Normal (non-revoked) key registration must still work
    """

    @pytest.mark.asyncio
    async def test_register_revoked_key_raises_error(self):
        """Registering a key_id that was revoked must raise KeyManagerError."""
        km = InMemoryKeyManager()
        await km.generate_keypair("test-key")
        await km.revoke_key("test-key")

        new_private_key, _public_key = generate_keypair()

        with pytest.raises(KeyManagerError, match="revoked"):
            km.register_key("test-key", new_private_key)

    @pytest.mark.asyncio
    async def test_revoked_key_ids_set_exists(self):
        """InMemoryKeyManager must have a _revoked_key_ids attribute."""
        km = InMemoryKeyManager()
        assert hasattr(km, "_revoked_key_ids"), (
            "_revoked_key_ids: Set[str] must exist to track permanently "
            "revoked key_ids."
        )
        assert isinstance(km._revoked_key_ids, set)

    @pytest.mark.asyncio
    async def test_revoke_populates_revoked_key_ids(self):
        """revoke_key() must add the key_id to _revoked_key_ids."""
        km = InMemoryKeyManager()
        await km.generate_keypair("test-key")
        await km.revoke_key("test-key")

        assert "test-key" in km._revoked_key_ids

    @pytest.mark.asyncio
    async def test_register_non_revoked_key_succeeds(self):
        """Registering a new (non-revoked) key_id must still work."""
        km = InMemoryKeyManager()
        private_key, _public_key = generate_keypair()

        # Should not raise
        km.register_key("fresh-key", private_key)

        assert km.has_key("fresh-key")

    @pytest.mark.asyncio
    async def test_register_revoked_key_error_includes_details(self):
        """The error raised for revoked re-registration must include key_id details."""
        km = InMemoryKeyManager()
        await km.generate_keypair("secret-key")
        await km.revoke_key("secret-key")

        new_private_key, _public_key = generate_keypair()

        with pytest.raises(KeyManagerError) as exc_info:
            km.register_key("secret-key", new_private_key)

        error = exc_info.value
        assert error.key_id == "secret-key"
        assert error.operation == "register_key"

    @pytest.mark.asyncio
    async def test_multiple_revocations_all_blocked(self):
        """Multiple different keys revoked are all blocked from re-registration."""
        km = InMemoryKeyManager()

        for key_id in ["key-1", "key-2", "key-3"]:
            await km.generate_keypair(key_id)
            await km.revoke_key(key_id)

        new_private_key, _public_key = generate_keypair()

        for key_id in ["key-1", "key-2", "key-3"]:
            with pytest.raises(KeyManagerError, match="revoked"):
                km.register_key(key_id, new_private_key)

    @pytest.mark.asyncio
    async def test_generate_keypair_also_blocks_revoked_key_id(self):
        """generate_keypair() must also refuse revoked key_ids (fail-closed)."""
        km = InMemoryKeyManager()
        await km.generate_keypair("test-key")
        await km.revoke_key("test-key")

        with pytest.raises(KeyManagerError, match="revoked"):
            await km.generate_keypair("test-key")


# ===========================================================================
# H7: AWS KMS verify must not fall back to wrong key
# ===========================================================================


class TestH7AWSKMSVerifyWrongKeyFallback:
    """H7: AWS KMS verify falls back to wrong key.

    After the fix:
    - When no matching public key ARN is found, verify must raise
      KeyManagerError immediately
    - Must NOT fall back to the first available ARN
    - Verify with a matching public key must still work normally
    """

    @pytest.mark.asyncio
    async def test_verify_unknown_public_key_raises_error(self):
        """verify() with an unrecognized public key must raise KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        sig = base64.b64encode(b"some-sig").decode("utf-8")
        unknown_pub_key = base64.b64encode(b"unknown-public-key").decode("utf-8")

        with pytest.raises(KeyManagerError, match="[Nn]o matching.*key"):
            await manager.verify("test payload", sig, unknown_pub_key)

    @pytest.mark.asyncio
    async def test_verify_does_not_fallback_to_first_arn(self):
        """verify() must NOT use the first available ARN when no match is found."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        sig = base64.b64encode(b"some-sig").decode("utf-8")
        unknown_pub_key = base64.b64encode(b"wrong-key-material").decode("utf-8")

        with pytest.raises(KeyManagerError):
            await manager.verify("test payload", sig, unknown_pub_key)

        # KMS verify should NOT have been called with the wrong key
        mock_client.verify.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_with_matching_public_key_works(self):
        """verify() with a recognized public key still works normally."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        _arn, public_key = await manager.generate_keypair("agent-001")

        sig = base64.b64encode(b"some-sig").decode("utf-8")
        result = await manager.verify("test payload", sig, public_key)

        assert result is True
        mock_client.verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_no_keys_at_all_raises_error(self):
        """verify() with no keys registered at all raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        sig = base64.b64encode(b"some-sig").decode("utf-8")
        pub_key = base64.b64encode(b"any-key").decode("utf-8")

        with pytest.raises(KeyManagerError):
            await manager.verify("test payload", sig, pub_key)

    @pytest.mark.asyncio
    async def test_verify_error_message_is_descriptive(self):
        """The error for unmatched public key must be descriptive."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        sig = base64.b64encode(b"sig").decode("utf-8")
        unknown_pub_key = base64.b64encode(b"unknown-key").decode("utf-8")

        with pytest.raises(KeyManagerError) as exc_info:
            await manager.verify("test", sig, unknown_pub_key)

        error_msg = str(exc_info.value)
        # Error must mention that no matching key was found
        assert "matching" in error_msg.lower() or "no" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_verify_with_multiple_keys_matches_correct_one(self):
        """verify() with multiple keys matches the correct one, not the first."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        # Generate first key
        await manager.generate_keypair("agent-001")

        # Setup second key with different ARN and public key
        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-second-key",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-second-key",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }
        second_pub_bytes = b"second-public-key-bytes"
        mock_client.get_public_key.return_value = {
            "PublicKey": second_pub_bytes,
            "KeySpec": "ECC_NIST_P256",
        }
        _arn2, public_key_2 = await manager.generate_keypair("agent-002")

        sig = base64.b64encode(b"some-sig").decode("utf-8")
        await manager.verify("test payload", sig, public_key_2)

        # Verify was called with the second key's ARN, not the first
        call_kwargs = mock_client.verify.call_args[1]
        assert (
            call_kwargs["KeyId"]
            == "arn:aws:kms:us-east-1:123456789012:key/mrk-second-key"
        )
