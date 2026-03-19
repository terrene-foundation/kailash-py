# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for AWSKMSKeyManager.

Tests cover:
- Initialization: boto3 dependency check, client injection, default creation
- generate_keypair: KMS CreateKey + GetPublicKey calls, error handling
- sign: KMS Sign API, payload serialization, revoked key rejection
- verify: KMS Verify API
- rotate_key: New key creation, old key scheduled for deletion
- revoke_key: ScheduleKeyDeletion with configurable pending window
- get_key_metadata: DescribeKey mapping to KeyMetadata
- list_keys: Pagination, tag filtering, active_only filtering
- Error handling: ClientError mapping to KeyManagerError, fail-closed behavior
- Algorithm: ECDSA P-256 (NOT Ed25519)

All tests use a mock KMS client since this is Tier 1 (unit) testing.
Real AWS KMS testing belongs in Tier 2/3.
"""

import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from eatp.key_manager import (
    AWSKMSKeyManager,
    KeyManagerError,
    KeyMetadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_kms_client():
    """Create a mock boto3 KMS client with standard responses."""
    client = MagicMock()

    # Default CreateKey response
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

    # Default GetPublicKey response (DER-encoded public key bytes, base64 for test)
    fake_pub_key_bytes = b"fake-der-encoded-public-key-bytes-for-testing"
    client.get_public_key.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "PublicKey": fake_pub_key_bytes,
        "KeySpec": "ECC_NIST_P256",
        "KeyUsage": "SIGN_VERIFY",
        "SigningAlgorithms": ["ECDSA_SHA_256"],
    }

    # Default Sign response
    fake_signature = b"fake-ecdsa-signature-bytes"
    client.sign.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "Signature": fake_signature,
        "SigningAlgorithm": "ECDSA_SHA_256",
    }

    # Default Verify response
    client.verify.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "SignatureValid": True,
        "SigningAlgorithm": "ECDSA_SHA_256",
    }

    # Default DescribeKey response
    client.describe_key.return_value = {
        "KeyMetadata": {
            "KeyId": "mrk-test-key-id-123",
            "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
            "KeyState": "Enabled",
            "KeyUsage": "SIGN_VERIFY",
            "KeySpec": "ECC_NIST_P256",
            "CreationDate": datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "Description": "",
            "Enabled": True,
        }
    }

    # Default ScheduleKeyDeletion response
    client.schedule_key_deletion.return_value = {
        "KeyId": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
        "DeletionDate": datetime(2026, 1, 22, 10, 30, 0, tzinfo=timezone.utc),
        "KeyState": "PendingDeletion",
        "PendingWindowInDays": 7,
    }

    # Default ListKeys response (single page)
    client.list_keys.return_value = {
        "Keys": [
            {
                "KeyId": "mrk-test-key-id-123",
                "KeyArn": "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
            }
        ],
        "Truncated": False,
    }

    # Default ListResourceTags response
    client.list_resource_tags.return_value = {
        "Tags": [
            {"TagKey": "eatp_key_id", "TagValue": "agent-001"},
        ],
        "Truncated": False,
    }

    return client


def _make_client_error(error_code, message="Test error"):
    """Create a botocore ClientError for testing."""
    # Import the real or mock ClientError
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        # If botocore not installed, create a compatible mock
        class ClientError(Exception):
            def __init__(self, error_response, operation_name):
                self.response = error_response
                self.operation_name = operation_name
                super().__init__(str(error_response))

    return ClientError(
        error_response={
            "Error": {
                "Code": error_code,
                "Message": message,
            }
        },
        operation_name="TestOperation",
    )


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


class TestAWSKMSKeyManagerInit:
    """Test AWSKMSKeyManager initialization."""

    def test_init_with_injected_client(self):
        """Injected kms_client is stored and used directly."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        assert manager._kms_client is mock_client

    def test_init_without_boto3_raises_import_error(self):
        """When boto3 is not available, init raises ImportError with helpful message."""
        with patch("eatp.key_manager.BOTO3_AVAILABLE", False):
            with pytest.raises(ImportError, match="boto3"):
                AWSKMSKeyManager()

    def test_init_creates_default_client_when_boto3_available(self):
        """When boto3 available and no client provided, creates default client."""
        with patch("eatp.key_manager.BOTO3_AVAILABLE", True):
            with patch("eatp.key_manager.boto3") as mock_boto3:
                mock_boto3.client.return_value = MagicMock()
                manager = AWSKMSKeyManager(region_name="us-west-2")
                mock_boto3.client.assert_called_once_with("kms", region_name="us-west-2")

    def test_init_default_pending_deletion_days(self):
        """Default pending_deletion_days is 7."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        assert manager._pending_deletion_days == 7

    def test_init_custom_pending_deletion_days(self):
        """Custom pending_deletion_days is stored."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client, pending_deletion_days=30)
        assert manager._pending_deletion_days == 30

    def test_init_empty_key_arns_and_metadata(self):
        """Fresh manager has empty key_arns and metadata dicts."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        assert manager._key_arns == {}
        assert manager._metadata == {}


# ---------------------------------------------------------------------------
# generate_keypair Tests
# ---------------------------------------------------------------------------


class TestAWSKMSGenerateKeypair:
    """Test AWSKMSKeyManager.generate_keypair()."""

    @pytest.mark.asyncio
    async def test_generate_keypair_calls_create_key_with_correct_params(self):
        """create_key called with SIGN_VERIFY usage and ECC_NIST_P256 spec."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        await manager.generate_keypair("agent-001")

        mock_client.create_key.assert_called_once()
        call_kwargs = mock_client.create_key.call_args[1]
        assert call_kwargs["KeyUsage"] == "SIGN_VERIFY"
        assert call_kwargs["KeySpec"] == "ECC_NIST_P256"

    @pytest.mark.asyncio
    async def test_generate_keypair_tags_with_eatp_key_id(self):
        """create_key is called with eatp_key_id tag."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        await manager.generate_keypair("agent-001")

        call_kwargs = mock_client.create_key.call_args[1]
        tags = call_kwargs["Tags"]
        eatp_tag = next(t for t in tags if t["TagKey"] == "eatp_key_id")
        assert eatp_tag["TagValue"] == "agent-001"

    @pytest.mark.asyncio
    async def test_generate_keypair_calls_get_public_key(self):
        """get_public_key called with the ARN from create_key response."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        await manager.generate_keypair("agent-001")

        expected_arn = "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123"
        mock_client.get_public_key.assert_called_once_with(KeyId=expected_arn)

    @pytest.mark.asyncio
    async def test_generate_keypair_returns_arn_and_base64_public_key(self):
        """Returns (arn, base64-encoded-public-key)."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        arn, public_key = await manager.generate_keypair("agent-001")

        expected_arn = "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123"
        assert arn == expected_arn

        # Public key should be base64-encoded version of the raw bytes
        expected_pub = base64.b64encode(b"fake-der-encoded-public-key-bytes-for-testing").decode("utf-8")
        assert public_key == expected_pub

    @pytest.mark.asyncio
    async def test_generate_keypair_stores_arn_mapping(self):
        """key_id -> ARN mapping is stored internally."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        await manager.generate_keypair("agent-001")

        expected_arn = "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123"
        assert manager._key_arns["agent-001"] == expected_arn

    @pytest.mark.asyncio
    async def test_generate_keypair_stores_metadata(self):
        """KeyMetadata is created and stored."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        await manager.generate_keypair("agent-001")

        meta = manager._metadata["agent-001"]
        assert isinstance(meta, KeyMetadata)
        assert meta.key_id == "agent-001"
        assert meta.algorithm == "ECDSA_P256"
        assert meta.is_hardware_backed is True
        assert meta.hsm_slot is not None  # Should be the ARN

    @pytest.mark.asyncio
    async def test_generate_keypair_duplicate_key_id_raises_error(self):
        """Generating a key with an existing key_id raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        await manager.generate_keypair("agent-001")

        with pytest.raises(KeyManagerError, match="already exists"):
            await manager.generate_keypair("agent-001")

    @pytest.mark.asyncio
    async def test_generate_keypair_kms_error_raises_key_manager_error(self):
        """KMS ClientError is wrapped in KeyManagerError."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = _make_client_error("AccessDeniedException", "Access denied")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError, match="Access denied"):
            await manager.generate_keypair("agent-001")


# ---------------------------------------------------------------------------
# sign Tests
# ---------------------------------------------------------------------------


class TestAWSKMSSign:
    """Test AWSKMSKeyManager.sign()."""

    @pytest.mark.asyncio
    async def test_sign_calls_kms_sign_with_correct_params(self):
        """KMS sign called with correct ARN, message, and algorithm."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        await manager.sign("test payload", "agent-001")

        mock_client.sign.assert_called_once()
        call_kwargs = mock_client.sign.call_args[1]
        expected_arn = "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123"
        assert call_kwargs["KeyId"] == expected_arn
        assert call_kwargs["MessageType"] == "RAW"
        assert call_kwargs["SigningAlgorithm"] == "ECDSA_SHA_256"

    @pytest.mark.asyncio
    async def test_sign_string_payload_encoded_as_utf8(self):
        """String payloads are encoded to UTF-8 bytes."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        await manager.sign("hello world", "agent-001")

        call_kwargs = mock_client.sign.call_args[1]
        assert call_kwargs["Message"] == b"hello world"

    @pytest.mark.asyncio
    async def test_sign_dict_payload_uses_serialize_for_signing(self):
        """Dict payloads are serialized deterministically then encoded."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        payload = {"action": "test", "agent": "001"}
        await manager.sign(payload, "agent-001")

        call_kwargs = mock_client.sign.call_args[1]
        # serialize_for_signing produces deterministic JSON
        from eatp.crypto import serialize_for_signing

        expected_bytes = serialize_for_signing(payload).encode("utf-8")
        assert call_kwargs["Message"] == expected_bytes

    @pytest.mark.asyncio
    async def test_sign_returns_base64_encoded_signature(self):
        """Returned signature is base64-encoded."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        signature = await manager.sign("test", "agent-001")

        expected = base64.b64encode(b"fake-ecdsa-signature-bytes").decode("utf-8")
        assert signature == expected

    @pytest.mark.asyncio
    async def test_sign_unknown_key_id_raises_error(self):
        """Signing with unknown key_id raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError, match="not found"):
            await manager.sign("test", "nonexistent-key")

    @pytest.mark.asyncio
    async def test_sign_revoked_key_raises_error(self):
        """Signing with a revoked key raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")
        await manager.revoke_key("agent-001")

        with pytest.raises(KeyManagerError, match="revoked"):
            await manager.sign("test", "agent-001")

    @pytest.mark.asyncio
    async def test_sign_kms_error_raises_key_manager_error(self):
        """KMS ClientError during sign is wrapped in KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.sign.side_effect = _make_client_error("DisabledException", "Key is disabled")

        with pytest.raises(KeyManagerError, match="disabled"):
            await manager.sign("test", "agent-001")


# ---------------------------------------------------------------------------
# verify Tests
# ---------------------------------------------------------------------------


class TestAWSKMSVerify:
    """Test AWSKMSKeyManager.verify()."""

    @pytest.mark.asyncio
    async def test_verify_valid_signature_returns_true(self):
        """Valid signature returns True."""
        mock_client = _make_mock_kms_client()
        mock_client.verify.return_value = {
            "SignatureValid": True,
            "SigningAlgorithm": "ECDSA_SHA_256",
        }
        manager = AWSKMSKeyManager(kms_client=mock_client)
        _arn, pub_key = await manager.generate_keypair("agent-001")

        sig = base64.b64encode(b"fake-sig").decode("utf-8")
        result = await manager.verify("test payload", sig, pub_key)

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_invalid_signature_returns_false(self):
        """Invalid signature returns False."""
        mock_client = _make_mock_kms_client()
        mock_client.verify.return_value = {
            "SignatureValid": False,
            "SigningAlgorithm": "ECDSA_SHA_256",
        }
        manager = AWSKMSKeyManager(kms_client=mock_client)
        _arn, pub_key = await manager.generate_keypair("agent-001")

        sig = base64.b64encode(b"bad-sig").decode("utf-8")
        result = await manager.verify("test payload", sig, pub_key)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_calls_kms_verify_with_correct_params(self):
        """KMS verify called with proper algorithm and message type."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        _arn, pub_key = await manager.generate_keypair("agent-001")

        sig_bytes = b"test-signature"
        sig = base64.b64encode(sig_bytes).decode("utf-8")
        await manager.verify("payload text", sig, pub_key)

        mock_client.verify.assert_called_once()
        call_kwargs = mock_client.verify.call_args[1]
        assert call_kwargs["Message"] == b"payload text"
        assert call_kwargs["MessageType"] == "RAW"
        assert call_kwargs["SigningAlgorithm"] == "ECDSA_SHA_256"
        assert call_kwargs["Signature"] == sig_bytes

    @pytest.mark.asyncio
    async def test_verify_kms_error_raises_key_manager_error(self):
        """KMS ClientError during verify is wrapped in KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        _arn, pub_key = await manager.generate_keypair("agent-001")

        mock_client.verify.side_effect = _make_client_error("KMSInternalException", "KMS internal error")

        sig = base64.b64encode(b"sig").decode("utf-8")
        with pytest.raises(KeyManagerError, match="KMS"):
            await manager.verify("test", sig, pub_key)


# ---------------------------------------------------------------------------
# rotate_key Tests
# ---------------------------------------------------------------------------


class TestAWSKMSRotateKey:
    """Test AWSKMSKeyManager.rotate_key()."""

    @pytest.mark.asyncio
    async def test_rotate_key_creates_new_kms_key(self):
        """Rotation creates a new KMS key via create_key."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        # Set up different ARN for second create_key call
        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-new-key-456",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }
        mock_client.get_public_key.return_value = {
            "PublicKey": b"new-public-key-bytes",
            "KeySpec": "ECC_NIST_P256",
        }

        new_arn, new_pub = await manager.rotate_key("agent-001")

        assert new_arn == "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456"
        assert new_pub == base64.b64encode(b"new-public-key-bytes").decode("utf-8")

    @pytest.mark.asyncio
    async def test_rotate_key_schedules_old_key_deletion(self):
        """Old key is scheduled for deletion during rotation."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        old_arn = manager._key_arns["agent-001"]

        # Set up different response for rotation
        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-new-key-456",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }

        await manager.rotate_key("agent-001")

        mock_client.schedule_key_deletion.assert_called_once_with(
            KeyId=old_arn,
            PendingWindowInDays=7,
        )

    @pytest.mark.asyncio
    async def test_rotate_key_updates_arn_mapping(self):
        """After rotation, key_id maps to the new ARN."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-new-key-456",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }

        await manager.rotate_key("agent-001")

        assert manager._key_arns["agent-001"] == "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456"

    @pytest.mark.asyncio
    async def test_rotate_key_updates_metadata_with_rotation_info(self):
        """Metadata after rotation records rotated_from."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-new-key-456",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }

        await manager.rotate_key("agent-001")

        meta = manager._metadata["agent-001"]
        assert meta.rotated_from is not None

    @pytest.mark.asyncio
    async def test_rotate_key_nonexistent_raises_error(self):
        """Rotating a nonexistent key raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError, match="not found"):
            await manager.rotate_key("nonexistent")

    @pytest.mark.asyncio
    async def test_rotate_key_uses_configured_pending_deletion_days(self):
        """Rotation uses the configured pending_deletion_days."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client, pending_deletion_days=30)
        await manager.generate_keypair("agent-001")

        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-new-key-456",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-new-key-456",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }

        await manager.rotate_key("agent-001")

        mock_client.schedule_key_deletion.assert_called_once_with(
            KeyId="arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123",
            PendingWindowInDays=30,
        )


# ---------------------------------------------------------------------------
# revoke_key Tests
# ---------------------------------------------------------------------------


class TestAWSKMSRevokeKey:
    """Test AWSKMSKeyManager.revoke_key()."""

    @pytest.mark.asyncio
    async def test_revoke_key_schedules_deletion(self):
        """revoke_key calls schedule_key_deletion with correct ARN."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        await manager.revoke_key("agent-001")

        expected_arn = "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123"
        mock_client.schedule_key_deletion.assert_called_once_with(
            KeyId=expected_arn,
            PendingWindowInDays=7,
        )

    @pytest.mark.asyncio
    async def test_revoke_key_marks_metadata_as_revoked(self):
        """Metadata is updated to reflect revocation."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        await manager.revoke_key("agent-001")

        meta = manager._metadata["agent-001"]
        assert meta.is_revoked is True
        assert meta.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_key_nonexistent_raises_error(self):
        """Revoking nonexistent key raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError, match="not found"):
            await manager.revoke_key("nonexistent")

    @pytest.mark.asyncio
    async def test_revoke_key_kms_error_raises_key_manager_error(self):
        """KMS error during revocation is wrapped in KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.schedule_key_deletion.side_effect = _make_client_error("NotFoundException", "Key not found in KMS")

        with pytest.raises(KeyManagerError, match="not found"):
            await manager.revoke_key("agent-001")

    @pytest.mark.asyncio
    async def test_revoke_key_uses_configured_pending_days(self):
        """Custom pending_deletion_days is used in schedule_key_deletion."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client, pending_deletion_days=14)
        await manager.generate_keypair("agent-001")

        await manager.revoke_key("agent-001")

        call_kwargs = mock_client.schedule_key_deletion.call_args[1]
        assert call_kwargs["PendingWindowInDays"] == 14


# ---------------------------------------------------------------------------
# get_key_metadata Tests
# ---------------------------------------------------------------------------


class TestAWSKMSGetKeyMetadata:
    """Test AWSKMSKeyManager.get_key_metadata()."""

    @pytest.mark.asyncio
    async def test_get_metadata_for_existing_key(self):
        """Returns KeyMetadata for a known key."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        meta = await manager.get_key_metadata("agent-001")

        assert meta is not None
        assert meta.key_id == "agent-001"
        assert meta.algorithm == "ECDSA_P256"
        assert meta.is_hardware_backed is True

    @pytest.mark.asyncio
    async def test_get_metadata_for_nonexistent_key_returns_none(self):
        """Returns None for unknown key_id."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        meta = await manager.get_key_metadata("nonexistent")

        assert meta is None

    @pytest.mark.asyncio
    async def test_get_metadata_calls_describe_key(self):
        """describe_key is called to refresh metadata from KMS."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        await manager.get_key_metadata("agent-001")

        expected_arn = "arn:aws:kms:us-east-1:123456789012:key/mrk-test-key-id-123"
        mock_client.describe_key.assert_called_with(KeyId=expected_arn)


# ---------------------------------------------------------------------------
# list_keys Tests
# ---------------------------------------------------------------------------


class TestAWSKMSListKeys:
    """Test AWSKMSKeyManager.list_keys()."""

    @pytest.mark.asyncio
    async def test_list_keys_returns_all_managed_keys(self):
        """list_keys returns metadata for all locally tracked keys."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        # Setup second key
        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-key-2",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-key-2",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }
        await manager.generate_keypair("agent-002")

        keys = await manager.list_keys(active_only=False)

        assert len(keys) == 2
        key_ids = {k.key_id for k in keys}
        assert key_ids == {"agent-001", "agent-002"}

    @pytest.mark.asyncio
    async def test_list_keys_active_only_excludes_revoked(self):
        """active_only=True excludes revoked keys."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.create_key.return_value = {
            "KeyMetadata": {
                "KeyId": "mrk-key-2",
                "Arn": "arn:aws:kms:us-east-1:123456789012:key/mrk-key-2",
                "KeyState": "Enabled",
                "KeyUsage": "SIGN_VERIFY",
                "KeySpec": "ECC_NIST_P256",
                "CreationDate": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        }
        await manager.generate_keypair("agent-002")
        await manager.revoke_key("agent-001")

        keys = await manager.list_keys(active_only=True)

        assert len(keys) == 1
        assert keys[0].key_id == "agent-002"

    @pytest.mark.asyncio
    async def test_list_keys_empty_when_no_keys(self):
        """Returns empty list when no keys managed."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        keys = await manager.list_keys()

        assert keys == []


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestAWSKMSErrorHandling:
    """Test error mapping from KMS ClientError to KeyManagerError."""

    @pytest.mark.asyncio
    async def test_access_denied_error_message(self):
        """AccessDeniedException produces clear error message."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = _make_client_error("AccessDeniedException", "User is not authorized")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError, match="[Aa]ccess denied"):
            await manager.generate_keypair("agent-001")

    @pytest.mark.asyncio
    async def test_not_found_error_message(self):
        """NotFoundException produces clear error message."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.sign.side_effect = _make_client_error("NotFoundException", "Key ARN not found")

        with pytest.raises(KeyManagerError, match="[Nn]ot found"):
            await manager.sign("test", "agent-001")

    @pytest.mark.asyncio
    async def test_disabled_key_error_message(self):
        """DisabledException produces clear error message."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        mock_client.sign.side_effect = _make_client_error("DisabledException", "Key is disabled")

        with pytest.raises(KeyManagerError, match="disabled"):
            await manager.sign("test", "agent-001")

    @pytest.mark.asyncio
    async def test_kms_internal_error_message(self):
        """KMSInternalException produces clear error message."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = _make_client_error("KMSInternalException", "Internal service error")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError, match="[Ss]ervice error"):
            await manager.generate_keypair("agent-001")

    @pytest.mark.asyncio
    async def test_fail_closed_no_fallback(self):
        """When KMS is unreachable, raises error -- never falls back to in-memory."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = _make_client_error("KMSInternalException", "Service unavailable")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError):
            await manager.generate_keypair("agent-001")

        # No keys should have been created locally
        assert "agent-001" not in manager._key_arns
        assert "agent-001" not in manager._metadata


# ---------------------------------------------------------------------------
# Algorithm Documentation Tests
# ---------------------------------------------------------------------------


class TestAWSKMSAlgorithm:
    """Verify ECDSA P-256 algorithm is used, not Ed25519."""

    def test_class_docstring_documents_algorithm_mismatch(self):
        """Class docstring mentions ECDSA P-256 vs Ed25519 difference."""
        docstring = AWSKMSKeyManager.__doc__
        assert "ECDSA" in docstring or "P-256" in docstring or "ECC_NIST_P256" in docstring

    @pytest.mark.asyncio
    async def test_metadata_uses_ecdsa_p256_algorithm(self):
        """KeyMetadata algorithm is ECDSA_P256, not Ed25519."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)
        await manager.generate_keypair("agent-001")

        meta = manager._metadata["agent-001"]
        assert meta.algorithm == "ECDSA_P256"
        assert meta.algorithm != "Ed25519"
