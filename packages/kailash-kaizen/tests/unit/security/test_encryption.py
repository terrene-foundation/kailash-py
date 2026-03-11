"""Tier 1 unit tests for data encryption system."""

import pytest
from kaizen.security.encryption import EncryptionProvider


class TestEncryptionProvider:
    """Test suite for EncryptionProvider (AES-256-GCM)."""

    def test_encrypt_decrypt_string(self):
        """Test 3.1a: Encrypt and decrypt string data."""
        provider = EncryptionProvider()

        # Encrypt sensitive string
        original = "sensitive_api_key_12345"
        encrypted = provider.encrypt(original)

        # Verify encrypted data is different
        assert encrypted != original
        assert isinstance(encrypted, bytes)

        # Decrypt and verify
        decrypted = provider.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_decrypt_dict(self):
        """Test 3.1b: Encrypt and decrypt dictionary data."""
        provider = EncryptionProvider()

        # Encrypt sensitive dictionary
        original = {
            "api_key": "sk-12345",
            "user_credentials": {"username": "admin", "password": "secret"},
        }
        encrypted = provider.encrypt(original)

        # Verify encrypted
        assert isinstance(encrypted, bytes)

        # Decrypt and verify
        decrypted = provider.decrypt(encrypted)
        assert decrypted == original
        assert decrypted["api_key"] == "sk-12345"
        assert decrypted["user_credentials"]["password"] == "secret"

    def test_tampering_detection(self):
        """Test 3.1c: Detect data tampering (integrity check)."""
        provider = EncryptionProvider()

        # Encrypt data
        original = "important_data"
        encrypted = provider.encrypt(original)

        # Tamper with encrypted data
        tampered = encrypted[:-1] + b"X"

        # Attempt to decrypt tampered data should raise error
        with pytest.raises(Exception) as exc_info:
            provider.decrypt(tampered)

        # Verify it's a decryption/integrity error
        # cryptography library raises InvalidTag for tampering
        assert (
            "InvalidTag" in str(type(exc_info.value).__name__)
            or "decrypt" in str(exc_info.value).lower()
            or "tag" in str(exc_info.value).lower()
        )

    def test_key_generation(self):
        """Test 3.1d: Secure key generation."""
        # Generate two providers with different keys
        provider1 = EncryptionProvider()
        provider2 = EncryptionProvider()

        # Encrypt with provider1
        original = "test_data"
        encrypted = provider1.encrypt(original)

        # Decrypt with provider1 should work
        assert provider1.decrypt(encrypted) == original

        # Decrypt with provider2 should fail (different key)
        with pytest.raises(Exception):
            provider2.decrypt(encrypted)

    def test_multiple_encryptions_different_outputs(self):
        """Test 3.1e: Multiple encryptions produce different ciphertexts (nonce randomness)."""
        provider = EncryptionProvider()

        original = "same_data"

        # Encrypt same data twice
        encrypted1 = provider.encrypt(original)
        encrypted2 = provider.encrypt(original)

        # Ciphertexts should be different (due to random nonce)
        assert encrypted1 != encrypted2

        # But both should decrypt to same original
        assert provider.decrypt(encrypted1) == original
        assert provider.decrypt(encrypted2) == original

    def test_key_derivation_from_password(self):
        """Test 3.2a: Derive encryption key from password."""
        # Derive key from password
        provider = EncryptionProvider.from_password("strong_password_123")

        # Should be able to encrypt/decrypt
        original = "sensitive_data"
        encrypted = provider.encrypt(original)
        decrypted = provider.decrypt(encrypted)

        assert decrypted == original

        # Same password should derive same key
        provider2 = EncryptionProvider.from_password(
            "strong_password_123", salt=provider.get_salt()
        )
        assert provider2.decrypt(encrypted) == original

    def test_key_rotation(self):
        """Test 3.2b: Rotate encryption keys."""
        from kaizen.security.encryption import KeyManager

        manager = KeyManager()

        # Encrypt with key version 1
        original = {"secret": "data"}
        encrypted_v1 = manager.encrypt(original, key_version=1)

        # Rotate to key version 2
        manager.rotate_key(new_version=2)

        # Can still decrypt old data with version 1
        decrypted = manager.decrypt(encrypted_v1, key_version=1)
        assert decrypted == original

        # New encryption uses version 2
        encrypted_v2 = manager.encrypt(original, key_version=2)

        # Both versions should work
        assert manager.decrypt(encrypted_v1, key_version=1) == original
        assert manager.decrypt(encrypted_v2, key_version=2) == original

    def test_key_metadata(self):
        """Test 3.2c: Track key metadata (creation time, usage count)."""
        from kaizen.security.encryption import KeyManager

        manager = KeyManager()

        # Get metadata for current key
        metadata = manager.get_key_metadata(version=1)

        assert "created_at" in metadata
        assert "version" in metadata
        assert metadata["version"] == 1

        # Encrypt data (should increment usage)
        data = "test"
        manager.encrypt(data, key_version=1)
        manager.encrypt(data, key_version=1)

        # Check usage count
        updated_metadata = manager.get_key_metadata(version=1)
        assert "usage_count" in updated_metadata
        assert updated_metadata["usage_count"] >= 2

    def test_re_encrypt_with_new_key(self):
        """Test 3.2d: Re-encrypt data with new key version."""
        from kaizen.security.encryption import KeyManager

        manager = KeyManager()

        # Encrypt with version 1
        original = {"confidential": "information"}
        encrypted_v1 = manager.encrypt(original, key_version=1)

        # Rotate to version 2
        manager.rotate_key(new_version=2)

        # Re-encrypt old data with new key
        encrypted_v2 = manager.re_encrypt(encrypted_v1, old_version=1, new_version=2)

        # Should decrypt to same data
        decrypted = manager.decrypt(encrypted_v2, key_version=2)
        assert decrypted == original

        # Old version should still work for old data
        assert manager.decrypt(encrypted_v1, key_version=1) == original

    def test_field_level_encryption(self):
        """Test 3.3a: Encrypt specific fields in dictionary."""
        from kaizen.security.encryption import FieldEncryptor

        encryptor = FieldEncryptor(sensitive_fields=["api_key", "password"])

        # Data with sensitive fields
        data = {
            "username": "john_doe",
            "email": "john@example.com",
            "api_key": "sk-secret123",
            "password": "my_password",
            "role": "admin",
        }

        # Encrypt sensitive fields
        encrypted_data = encryptor.encrypt_fields(data)

        # Verify non-sensitive fields unchanged
        assert encrypted_data["username"] == "john_doe"
        assert encrypted_data["email"] == "john@example.com"
        assert encrypted_data["role"] == "admin"

        # Verify sensitive fields encrypted
        assert encrypted_data["api_key"] != "sk-secret123"
        assert encrypted_data["password"] != "my_password"
        assert isinstance(encrypted_data["api_key"], str)  # Base64 encoded

        # Decrypt sensitive fields
        decrypted_data = encryptor.decrypt_fields(encrypted_data)

        # Verify complete data restored
        assert decrypted_data == data

    def test_nested_field_encryption(self):
        """Test 3.3b: Encrypt fields in nested dictionaries."""
        from kaizen.security.encryption import FieldEncryptor

        encryptor = FieldEncryptor(
            sensitive_fields=["credentials.password", "api.secret_key"]
        )

        data = {
            "user": "alice",
            "credentials": {"username": "alice123", "password": "secret_pass"},
            "api": {"endpoint": "https://api.example.com", "secret_key": "sk-12345"},
        }

        encrypted_data = encryptor.encrypt_fields(data)

        # Non-sensitive nested fields unchanged
        assert encrypted_data["credentials"]["username"] == "alice123"
        assert encrypted_data["api"]["endpoint"] == "https://api.example.com"

        # Sensitive nested fields encrypted
        assert encrypted_data["credentials"]["password"] != "secret_pass"
        assert encrypted_data["api"]["secret_key"] != "sk-12345"

        # Decrypt
        decrypted_data = encryptor.decrypt_fields(encrypted_data)
        assert decrypted_data == data

    def test_data_masking(self):
        """Test 3.3c: Mask sensitive data for display."""
        from kaizen.security.encryption import FieldEncryptor

        encryptor = FieldEncryptor(sensitive_fields=["credit_card", "ssn"])

        data = {
            "name": "Bob Smith",
            "credit_card": "4532-1234-5678-9012",
            "ssn": "123-45-6789",
        }

        # Mask sensitive fields
        masked_data = encryptor.mask_fields(data)

        # Non-sensitive unchanged
        assert masked_data["name"] == "Bob Smith"

        # Sensitive masked
        assert masked_data["credit_card"] == "****-****-****-9012"  # Last 4 digits
        assert masked_data["ssn"] == "***-**-6789"  # Last 4 digits

        # Original data unchanged
        assert data["credit_card"] == "4532-1234-5678-9012"

    def test_automatic_type_preservation(self):
        """Test 3.3d: Preserve data types during encryption."""
        from kaizen.security.encryption import FieldEncryptor

        encryptor = FieldEncryptor(
            sensitive_fields=["secret_number", "secret_bool", "secret_list"]
        )

        data = {
            "secret_number": 42,
            "secret_bool": True,
            "secret_list": [1, 2, 3],
            "public": "visible",
        }

        encrypted_data = encryptor.encrypt_fields(data)
        decrypted_data = encryptor.decrypt_fields(encrypted_data)

        # Verify types preserved
        assert decrypted_data["secret_number"] == 42
        assert isinstance(decrypted_data["secret_number"], int)

        assert decrypted_data["secret_bool"] is True
        assert isinstance(decrypted_data["secret_bool"], bool)

        assert decrypted_data["secret_list"] == [1, 2, 3]
        assert isinstance(decrypted_data["secret_list"], list)
