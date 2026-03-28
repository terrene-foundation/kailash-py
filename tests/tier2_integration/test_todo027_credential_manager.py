"""Unit tests for TODO-027: Credential Manager real backend implementations."""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from kailash.nodes.security.credential_manager import CredentialManagerNode


class TestVaultBackend:
    def test_vault_raises_import_error_without_hvac(self):
        """Should raise ImportError with install hint when hvac is missing."""
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["vault"],
        )

        with patch.dict(
            os.environ, {"VAULT_ADDR": "http://vault:8200", "VAULT_TOKEN": "token"}
        ):
            with patch(
                "builtins.__import__", side_effect=ImportError("No module named 'hvac'")
            ):
                with pytest.raises(ImportError, match="hvac"):
                    node.run()

    @patch.dict(
        os.environ, {"VAULT_ADDR": "http://vault:8200", "VAULT_TOKEN": "s.test"}
    )
    def test_vault_authentication_failure(self):
        """Returns None when Vault auth fails."""
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["vault"],
            validate_on_fetch=False,
        )

        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False

        with patch("hvac.Client", return_value=mock_client):
            # Should fall through to ValueError since vault returns None
            with pytest.raises(ValueError, match="not found"):
                node.run()

    @patch.dict(
        os.environ, {"VAULT_ADDR": "http://vault:8200", "VAULT_TOKEN": "s.test"}
    )
    def test_vault_kv_v2_success(self):
        """Successfully reads from Vault KV v2."""
        node = CredentialManagerNode(
            credential_name="my_secret",
            credential_type="custom",
            credential_sources=["vault"],
            validate_on_fetch=False,
        )

        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"api_key": "real-key-12345678901234567890"}}
        }

        with patch("hvac.Client", return_value=mock_client):
            result = node.run()

        assert result["source"] == "vault"
        assert result["credentials"]["api_key"] == "real-key-12345678901234567890"

    @patch.dict(os.environ, {}, clear=True)
    def test_vault_no_addr(self):
        """Returns None when VAULT_ADDR is not set."""
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["vault"],
        )

        mock_hvac = MagicMock()
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            # _fetch_from_vault will return None -> ValueError
            with pytest.raises(ValueError, match="not found"):
                node.run()


class TestAWSSecretsBackend:
    def test_aws_raises_import_error_without_boto3(self):
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["aws_secrets"],
        )

        with patch(
            "builtins.__import__", side_effect=ImportError("No module named 'boto3'")
        ):
            with pytest.raises(ImportError, match="boto3"):
                node.run()

    def test_aws_secrets_json_secret(self):
        """Successfully reads a JSON secret from AWS."""
        node = CredentialManagerNode(
            credential_name="prod/db",
            credential_type="database",
            credential_sources=["aws_secrets"],
            validate_on_fetch=False,
        )

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(
                {
                    "host": "db.prod.internal",
                    "port": "5432",
                    "username": "admin",
                    "password": "supersecret123456",
                }
            )
        }

        with patch("boto3.client", return_value=mock_client):
            result = node.run()

        assert result["source"] == "aws_secrets"
        assert result["credentials"]["host"] == "db.prod.internal"

    def test_aws_secrets_plain_string(self):
        """Handles plain string secrets."""
        node = CredentialManagerNode(
            credential_name="api-key",
            credential_sources=["aws_secrets"],
            validate_on_fetch=False,
        )

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": "plain-api-key-value"
        }

        with patch("boto3.client", return_value=mock_client):
            result = node.run()

        assert result["credentials"]["value"] == "plain-api-key-value"


class TestAzureKeyVaultBackend:
    def test_azure_raises_import_error(self):
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["azure_keyvault"],
        )

        with patch.dict(os.environ, {"AZURE_VAULT_URL": "https://vault.azure.net"}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                with pytest.raises(ImportError, match="azure"):
                    node.run()

    @patch.dict(os.environ, {"AZURE_VAULT_URL": "https://myvault.vault.azure.net"})
    def test_azure_json_secret(self):
        """Reads a JSON secret from Azure Key Vault."""
        import sys

        node = CredentialManagerNode(
            credential_name="my_app_config",
            credential_sources=["azure_keyvault"],
            validate_on_fetch=False,
        )

        mock_secret = MagicMock()
        mock_secret.value = json.dumps({"client_id": "abc", "client_secret": "xyz"})

        mock_client_cls = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.get_secret.return_value = mock_secret
        mock_client_cls.return_value = mock_client_instance

        mock_credential_cls = MagicMock()

        # Create mock azure modules in sys.modules so imports resolve
        mock_azure = MagicMock()
        mock_azure.identity.DefaultAzureCredential = mock_credential_cls
        mock_azure.keyvault.secrets.SecretClient = mock_client_cls

        with patch.dict(
            sys.modules,
            {
                "azure": mock_azure,
                "azure.identity": mock_azure.identity,
                "azure.keyvault": mock_azure.keyvault,
                "azure.keyvault.secrets": mock_azure.keyvault.secrets,
            },
        ):
            result = node.run()

        assert result["source"] == "azure_keyvault"
        assert result["credentials"]["client_id"] == "abc"
        # Azure replaces underscores with hyphens
        mock_client_instance.get_secret.assert_called_once_with("my-app-config")


class TestCaching:
    def test_cache_ttl(self):
        """Credentials should be cached and served from cache."""
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["env"],
            credential_type="api_key",
            cache_duration_seconds=300,
            validate_on_fetch=False,
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "key12345678901234567890"}):
            result1 = node.run()
            assert result1["source"] == "env"
            assert result1["metadata"].get("from_cache") is None

        # Second call should come from cache even without env var
        with patch.dict(os.environ, {}, clear=True):
            result2 = node.run()
            assert result2["metadata"]["from_cache"] is True
            assert result2["credentials"]["api_key"] == "key12345678901234567890"

    def test_no_cache(self):
        """With cache disabled, always fetches fresh."""
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["env"],
            credential_type="api_key",
            cache_duration_seconds=None,
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "key12345678901234567890"}):
            result = node.run()
            assert result["source"] == "env"


class TestMasking:
    def test_partial_masking(self):
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["env"],
            credential_type="api_key",
            validate_on_fetch=False,
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "abcdefghijklmnop"}):
            result = node.run()

        masked = result["masked_display"]["api_key"]
        # Should show first 4 and last 4 chars with * in between
        assert masked.startswith("abcd")
        assert masked.endswith("mnop")
        assert "*" in masked


class TestGracefulDegradation:
    def test_env_fallback(self):
        """Falls back to env when vault is not configured."""
        node = CredentialManagerNode(
            credential_name="test",
            credential_sources=["vault", "env"],
            credential_type="api_key",
            validate_on_fetch=False,
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "env-key-12345678901234567890"}):
            # vault will fail because VAULT_ADDR is not set
            result = node.run()
            assert result["source"] == "env"

    def test_all_sources_fail(self):
        """Raises ValueError when no source has the credential."""
        node = CredentialManagerNode(
            credential_name="nonexistent",
            credential_sources=["env", "file"],
        )

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="not found"):
                node.run()
