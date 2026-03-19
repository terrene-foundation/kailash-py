# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for KMS fail-closed behavior when KMS is unreachable (S1).

S1: When the KMS endpoint is unreachable (ConnectionError, EndpointConnectionError,
    ConnectTimeoutError), the key manager must raise KeyManagerError -- never
    silently return None, fall back to in-memory keys, or swallow the error.

This is the fail-closed principle: unknown/error states -> deny, NEVER silently permit.

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from eatp.key_manager import AWSKMSKeyManager, KeyManagerError


def _make_mock_kms_client():
    """Create a minimal mock boto3 KMS client."""
    return MagicMock()


# ---------------------------------------------------------------------------
# S1: KMS unreachable raises KeyManagerError (fail-closed)
# ---------------------------------------------------------------------------


class TestKMSUnreachableFailClosed:
    """S1: All KMS operations must raise KeyManagerError on connection failure."""

    @pytest.mark.asyncio
    async def test_generate_keypair_connection_error_raises_key_manager_error(self):
        """ConnectionError on generate_keypair raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = ConnectionError("Could not connect to KMS endpoint")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError) as exc_info:
            await manager.generate_keypair("agent-001")

        assert "agent-001" not in manager._key_arns
        assert "agent-001" not in manager._metadata
        # Error should contain useful context
        assert exc_info.value.details is not None

    @pytest.mark.asyncio
    async def test_generate_keypair_connection_error_does_not_return_none(self):
        """ConnectionError must not result in a None return (silent failure)."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = ConnectionError("KMS endpoint unreachable")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        # Must raise, not return None
        with pytest.raises(KeyManagerError):
            result = await manager.generate_keypair("agent-001")

    @pytest.mark.asyncio
    async def test_sign_connection_error_raises_key_manager_error(self):
        """ConnectionError on sign raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        # Manually set up key state (as if previously generated successfully)
        manager._key_arns["agent-001"] = "arn:aws:kms:us-east-1:123456789012:key/test"
        from eatp.key_manager import KeyMetadata

        manager._metadata["agent-001"] = KeyMetadata(
            key_id="agent-001",
            algorithm="ECDSA_P256",
            is_hardware_backed=True,
        )

        mock_client.sign.side_effect = ConnectionError("KMS endpoint unreachable")

        with pytest.raises(KeyManagerError):
            await manager.sign("test payload", "agent-001")

    @pytest.mark.asyncio
    async def test_verify_connection_error_raises_key_manager_error(self):
        """ConnectionError on verify raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        # Set up key state
        manager._key_arns["agent-001"] = "arn:aws:kms:us-east-1:123456789012:key/test"
        manager._public_keys["agent-001"] = "dGVzdC1wdWJsaWMta2V5"

        mock_client.verify.side_effect = ConnectionError("KMS endpoint unreachable")

        import base64

        sig = base64.b64encode(b"fake-sig").decode("utf-8")
        pub = "dGVzdC1wdWJsaWMta2V5"

        with pytest.raises(KeyManagerError):
            await manager.verify("test payload", sig, pub)

    @pytest.mark.asyncio
    async def test_revoke_key_connection_error_raises_key_manager_error(self):
        """ConnectionError on revoke_key raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        manager = AWSKMSKeyManager(kms_client=mock_client)

        # Set up key state
        manager._key_arns["agent-001"] = "arn:aws:kms:us-east-1:123456789012:key/test"
        from eatp.key_manager import KeyMetadata

        manager._metadata["agent-001"] = KeyMetadata(
            key_id="agent-001",
            algorithm="ECDSA_P256",
            is_hardware_backed=True,
        )

        mock_client.schedule_key_deletion.side_effect = ConnectionError("KMS endpoint unreachable")

        with pytest.raises(KeyManagerError):
            await manager.revoke_key("agent-001")

    @pytest.mark.asyncio
    async def test_oss_error_on_generate_raises_key_manager_error(self):
        """OSError (network-level) on generate_keypair raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = OSError("Network is unreachable")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError):
            await manager.generate_keypair("agent-001")

        # Must not leave partial state
        assert "agent-001" not in manager._key_arns
        assert "agent-001" not in manager._metadata

    @pytest.mark.asyncio
    async def test_timeout_error_on_generate_raises_key_manager_error(self):
        """TimeoutError on generate_keypair raises KeyManagerError."""
        mock_client = _make_mock_kms_client()
        mock_client.create_key.side_effect = TimeoutError("Connection to KMS timed out")
        manager = AWSKMSKeyManager(kms_client=mock_client)

        with pytest.raises(KeyManagerError):
            await manager.generate_keypair("agent-001")

        assert "agent-001" not in manager._key_arns
