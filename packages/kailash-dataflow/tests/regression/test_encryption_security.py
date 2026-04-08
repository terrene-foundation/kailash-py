"""Regression: DataFlow 2.0 — fake encrypt_tenant_data replaced with Fernet.

Prior to 2.0, encrypt_tenant_data returned f"encrypted_{key}_{data}" with a
hardcoded "tenant_specific_key" constant. This test verifies:
1. Encryption produces real ciphertext (not a prefixed plaintext)
2. Decryption recovers the original data
3. Missing encryption key raises, does NOT fall back to hardcoded
4. Different keys produce different ciphertext
"""

import pytest


@pytest.mark.regression
class TestEncryptTenantDataFernet:
    """Verify tenant data encryption uses real Fernet, not fake string concat."""

    def _make_manager(self):
        """Create a TenantSecurityManager for testing."""
        from dataflow.core.multi_tenancy import TenantSecurityManager

        return TenantSecurityManager()

    def test_encryption_produces_real_ciphertext(self, monkeypatch):
        """Ciphertext must NOT be the old f'encrypted_{key}_{data}' pattern."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setenv("DATAFLOW_TENANT_ENCRYPTION_KEY", key)

        manager = self._make_manager()
        plaintext = "sensitive-tenant-data"
        ciphertext = manager.encrypt_tenant_data("tenant1", plaintext)

        # Must NOT be the old fake pattern
        assert not ciphertext.startswith("encrypted_")
        assert "tenant_specific_key" not in ciphertext
        # Must be different from plaintext
        assert ciphertext != plaintext
        # Must be valid Fernet token (base64 URL-safe)
        assert len(ciphertext) > len(plaintext)

    def test_decryption_recovers_original(self, monkeypatch):
        """Round-trip: encrypt then decrypt must recover original data."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setenv("DATAFLOW_TENANT_ENCRYPTION_KEY", key)

        manager = self._make_manager()
        plaintext = "hello world 12345 !@#$%"
        ciphertext = manager.encrypt_tenant_data("tenant1", plaintext)

        # Decrypt with the same key
        fernet = Fernet(key.encode())
        decrypted = fernet.decrypt(ciphertext.encode()).decode("utf-8")
        assert decrypted == plaintext

    def test_missing_key_raises(self, monkeypatch):
        """Missing encryption key must raise, NOT fall back to hardcoded."""
        monkeypatch.delenv("DATAFLOW_TENANT_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("DATAFLOW_TENANT_KEY_TENANT1", raising=False)

        manager = self._make_manager()
        with pytest.raises(RuntimeError, match="No encryption key configured"):
            manager.encrypt_tenant_data("tenant1", "data")

    def test_per_tenant_key_takes_priority(self, monkeypatch):
        """Per-tenant key (DATAFLOW_TENANT_KEY_X) overrides shared key."""
        from cryptography.fernet import Fernet

        shared_key = Fernet.generate_key().decode()
        tenant_key = Fernet.generate_key().decode()
        monkeypatch.setenv("DATAFLOW_TENANT_ENCRYPTION_KEY", shared_key)
        monkeypatch.setenv("DATAFLOW_TENANT_KEY_TENANT1", tenant_key)

        manager = self._make_manager()
        ciphertext = manager.encrypt_tenant_data("tenant1", "data")

        # Must decrypt with the per-tenant key, NOT the shared key
        fernet_tenant = Fernet(tenant_key.encode())
        decrypted = fernet_tenant.decrypt(ciphertext.encode()).decode("utf-8")
        assert decrypted == "data"

        # Must NOT decrypt with the shared key
        fernet_shared = Fernet(shared_key.encode())
        with pytest.raises(Exception):
            fernet_shared.decrypt(ciphertext.encode())
