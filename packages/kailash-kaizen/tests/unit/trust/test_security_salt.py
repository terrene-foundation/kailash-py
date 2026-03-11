"""
Unit tests for CARE-001: Fix Static Salt in SecureKeyStorage.

Tests that SecureKeyStorage no longer uses a hardcoded static salt.
"""

import base64
import inspect
import os

import pytest

try:
    from cryptography.fernet import Fernet

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not CRYPTOGRAPHY_AVAILABLE, reason="cryptography not installed"
)


@pytest.fixture
def master_key_env(monkeypatch):
    """Set up master key environment variable."""
    monkeypatch.setenv("KAIZEN_TRUST_ENCRYPTION_KEY", "test-master-key-for-unit-tests")
    return "KAIZEN_TRUST_ENCRYPTION_KEY"


class TestSecureKeyStorageSalt:
    """Tests that SecureKeyStorage uses per-instance salt."""

    def test_no_static_salt_in_source(self):
        """The static salt string must not appear in security.py."""
        from kaizen.trust.security import SecureKeyStorage

        source = inspect.getsource(SecureKeyStorage)
        assert (
            "kaizen-trust-security-salt" not in source
        ), "Static salt b'kaizen-trust-security-salt' still present in SecureKeyStorage"

    def test_different_instances_get_different_salts(self, master_key_env):
        """Two instances without explicit salt should get different salts."""
        from kaizen.trust.security import SecureKeyStorage

        storage1 = SecureKeyStorage(master_key_env)
        storage2 = SecureKeyStorage(master_key_env)

        assert storage1._salt != storage2._salt

    def test_explicit_salt_is_used(self, master_key_env):
        """When salt is provided, it should be used."""
        from kaizen.trust.security import SecureKeyStorage

        explicit_salt = os.urandom(32)
        storage = SecureKeyStorage(master_key_env, salt=explicit_salt)

        assert storage._salt == explicit_salt

    def test_salt_from_env_variable(self, master_key_env, monkeypatch):
        """Salt from environment variable is used when available."""
        from kaizen.trust.security import SecureKeyStorage

        salt = os.urandom(32)
        salt_b64 = base64.b64encode(salt).decode()
        monkeypatch.setenv(f"{master_key_env}_SALT", salt_b64)

        storage = SecureKeyStorage(master_key_env)
        # Should use the env salt, encryption should work
        storage.store_key("test-key", b"test-value")
        retrieved = storage.retrieve_key("test-key")
        assert retrieved == b"test-value"

    def test_store_and_retrieve_with_random_salt(self, master_key_env):
        """Store and retrieve should work with per-instance random salt."""
        from kaizen.trust.security import SecureKeyStorage

        storage = SecureKeyStorage(master_key_env)
        storage.store_key("key-001", b"my-private-key-data")
        retrieved = storage.retrieve_key("key-001")

        assert retrieved == b"my-private-key-data"

    def test_same_salt_produces_same_encryption(self, master_key_env):
        """Same salt should produce same Fernet key (deterministic)."""
        from kaizen.trust.security import SecureKeyStorage

        salt = os.urandom(32)
        storage1 = SecureKeyStorage(master_key_env, salt=salt)
        storage2 = SecureKeyStorage(master_key_env, salt=salt)

        # Both should encrypt/decrypt the same way
        storage1.store_key("test", b"secret-data")
        # Retrieve the encrypted bytes and try decrypting with other instance
        encrypted = storage1._keys["test"]
        decrypted = storage2._fernet.decrypt(encrypted)
        assert decrypted == b"secret-data"
