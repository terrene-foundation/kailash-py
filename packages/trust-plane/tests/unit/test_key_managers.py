# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for key manager exception wrapping and import behavior.

Tier 1 (Unit): Tests ImportError behavior for missing cloud SDKs and
exception wrapping for provider-specific errors. These tests use mocks
to simulate cloud provider behavior without real credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAwsKmsKeyManagerImportError:
    """Test that AwsKmsKeyManager raises ImportError without boto3."""

    def test_init_raises_import_error_without_boto3(self) -> None:
        """AwsKmsKeyManager must raise ImportError if boto3 is not installed."""
        from trustplane.key_managers import aws_kms as aws_kms_mod

        # Simulate boto3 not being available by patching the availability flag
        with patch.object(aws_kms_mod, "_BOTO3_AVAILABLE", False):
            from trustplane.key_managers.aws_kms import AwsKmsKeyManager

            with pytest.raises(ImportError, match="pip install trust-plane\\[aws\\]"):
                AwsKmsKeyManager(
                    key_id="arn:aws:kms:us-east-1:123456789012:key/test-key"
                )

    def test_algorithm_returns_ecdsa_p256(self) -> None:
        """AwsKmsKeyManager.algorithm() must return 'ecdsa-p256'."""
        from trustplane.key_managers.aws_kms import AwsKmsKeyManager

        assert AwsKmsKeyManager.ALGORITHM == "ecdsa-p256"


class TestAzureKeyVaultKeyManagerImportError:
    """Test that AzureKeyVaultKeyManager raises ImportError without azure libs."""

    def test_init_raises_import_error_without_azure(self) -> None:
        """AzureKeyVaultKeyManager must raise ImportError if azure-keyvault-keys is not installed."""
        from trustplane.key_managers import azure_keyvault as azure_mod

        # Simulate azure libs not being available by patching the availability flag
        with patch.object(azure_mod, "_AZURE_AVAILABLE", False):
            from trustplane.key_managers.azure_keyvault import AzureKeyVaultKeyManager

            with pytest.raises(ImportError, match="pip install trust-plane\\[azure\\]"):
                AzureKeyVaultKeyManager(
                    vault_url="https://my-vault.vault.azure.net",
                    key_name="test-key",
                )

    def test_algorithm_returns_ecdsa_p256(self) -> None:
        """AzureKeyVaultKeyManager.algorithm() must return 'ecdsa-p256'."""
        from trustplane.key_managers.azure_keyvault import AzureKeyVaultKeyManager

        assert AzureKeyVaultKeyManager.ALGORITHM == "ecdsa-p256"


class TestVaultKeyManagerImportError:
    """Test that VaultKeyManager raises ImportError without hvac."""

    def test_init_raises_import_error_without_hvac(self) -> None:
        """VaultKeyManager must raise ImportError if hvac is not installed."""
        from trustplane.key_managers import vault as vault_mod

        # Simulate hvac not being available by patching the availability flag
        with patch.object(vault_mod, "_HVAC_AVAILABLE", False):
            from trustplane.key_managers.vault import VaultKeyManager

            with pytest.raises(ImportError, match="pip install trust-plane\\[vault\\]"):
                VaultKeyManager(
                    vault_addr="https://vault.example.com:8200",
                    key_name="test-key",
                )

    def test_algorithm_returns_ecdsa_p256(self) -> None:
        """VaultKeyManager.algorithm() must return 'ecdsa-p256'."""
        from trustplane.key_managers.vault import VaultKeyManager

        assert VaultKeyManager.ALGORITHM == "ecdsa-p256"

    def test_default_mount_point(self) -> None:
        """VaultKeyManager default mount_point must be 'transit'."""
        from trustplane.key_managers.vault import VaultKeyManager

        assert VaultKeyManager.DEFAULT_MOUNT_POINT == "transit"


class TestAwsKmsExceptionWrapping:
    """Tests for AWS KMS exception wrapping (TODO-43)."""

    def test_sign_wraps_botocore_error(self) -> None:
        """sign() must wrap BotoCoreError in SigningError."""
        from trustplane.exceptions import SigningError
        from trustplane.key_managers.aws_kms import AwsKmsKeyManager

        manager = AwsKmsKeyManager.__new__(AwsKmsKeyManager)
        manager._key_id = "arn:aws:kms:us-east-1:123:key/test"
        manager._client = MagicMock()
        manager._public_key_cache = None

        # Simulate botocore raising an error
        from botocore.exceptions import BotoCoreError

        manager._client.sign.side_effect = BotoCoreError()

        with pytest.raises(SigningError, match="aws_kms") as exc_info:
            manager.sign(b"test data")
        assert exc_info.value.provider == "aws_kms"
        assert isinstance(exc_info.value.__cause__, BotoCoreError)

    def test_get_public_key_wraps_client_error(self) -> None:
        """get_public_key() must wrap ClientError in KeyManagerError."""
        from trustplane.exceptions import KeyManagerError
        from trustplane.key_managers.aws_kms import AwsKmsKeyManager

        manager = AwsKmsKeyManager.__new__(AwsKmsKeyManager)
        manager._key_id = "arn:aws:kms:us-east-1:123:key/test"
        manager._client = MagicMock()
        manager._public_key_cache = None

        from botocore.exceptions import ClientError

        manager._client.get_public_key.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "GetPublicKey",
        )

        with pytest.raises(KeyManagerError, match="aws_kms"):
            manager.get_public_key()

    def test_get_public_key_wraps_not_found_as_key_not_found(self) -> None:
        """get_public_key() must raise KeyNotFoundError for NotFoundException."""
        from trustplane.exceptions import KeyNotFoundError
        from trustplane.key_managers.aws_kms import AwsKmsKeyManager

        manager = AwsKmsKeyManager.__new__(AwsKmsKeyManager)
        manager._key_id = "arn:aws:kms:us-east-1:123:key/test"
        manager._client = MagicMock()
        manager._public_key_cache = None

        from botocore.exceptions import ClientError

        manager._client.get_public_key.side_effect = ClientError(
            {"Error": {"Code": "NotFoundException", "Message": "key not found"}},
            "GetPublicKey",
        )

        with pytest.raises(KeyNotFoundError, match="aws_kms"):
            manager.get_public_key()


class TestAzureKeyVaultExceptionWrapping:
    """Tests for Azure Key Vault exception wrapping (TODO-43)."""

    def test_sign_wraps_azure_error(self) -> None:
        """sign() must wrap Azure errors in SigningError."""
        from trustplane.exceptions import SigningError
        from trustplane.key_managers.azure_keyvault import AzureKeyVaultKeyManager

        manager = AzureKeyVaultKeyManager.__new__(AzureKeyVaultKeyManager)
        manager._key_name = "test-key"
        manager._crypto_client = MagicMock()
        manager._public_key_cache = None

        manager._crypto_client.sign.side_effect = RuntimeError("Azure SDK error")

        with pytest.raises(SigningError, match="azure_keyvault") as exc_info:
            manager.sign(b"test data")
        assert exc_info.value.provider == "azure_keyvault"

    def test_get_public_key_wraps_azure_error(self) -> None:
        """get_public_key() must wrap Azure errors in KeyManagerError."""
        from trustplane.exceptions import KeyManagerError
        from trustplane.key_managers.azure_keyvault import AzureKeyVaultKeyManager

        manager = AzureKeyVaultKeyManager.__new__(AzureKeyVaultKeyManager)
        manager._key_name = "test-key"
        manager._key_client = MagicMock()
        manager._public_key_cache = None

        manager._key_client.get_key.side_effect = RuntimeError("Azure API error")

        with pytest.raises(KeyManagerError, match="azure_keyvault"):
            manager.get_public_key()


class TestVaultExceptionWrapping:
    """Tests for HashiCorp Vault exception wrapping (TODO-43)."""

    def test_sign_wraps_vault_error(self) -> None:
        """sign() must wrap Vault errors in SigningError."""
        from trustplane.exceptions import SigningError
        from trustplane.key_managers.vault import VaultKeyManager

        manager = VaultKeyManager.__new__(VaultKeyManager)
        manager._key_name = "test-key"
        manager._mount_point = "transit"
        manager._client = MagicMock()
        manager._public_key_cache = None

        manager._client.secrets.transit.sign_data.side_effect = RuntimeError(
            "Vault error"
        )

        with pytest.raises(SigningError, match="hashicorp_vault") as exc_info:
            manager.sign(b"test data")
        assert exc_info.value.provider == "hashicorp_vault"

    def test_get_public_key_wraps_vault_error(self) -> None:
        """get_public_key() must wrap Vault errors in KeyNotFoundError."""
        from trustplane.exceptions import KeyNotFoundError
        from trustplane.key_managers.vault import VaultKeyManager

        manager = VaultKeyManager.__new__(VaultKeyManager)
        manager._key_name = "test-key"
        manager._mount_point = "transit"
        manager._client = MagicMock()
        manager._public_key_cache = None

        manager._client.secrets.transit.read_key.side_effect = RuntimeError(
            "Vault unreachable"
        )

        with pytest.raises(KeyNotFoundError, match="hashicorp_vault"):
            manager.get_public_key()
