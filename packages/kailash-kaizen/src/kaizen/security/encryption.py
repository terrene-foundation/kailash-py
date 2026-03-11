"""Data encryption and decryption for Kaizen AI framework."""

import json
import os
from datetime import datetime, timezone
from typing import Any, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionProvider:
    """AES-256-GCM encryption provider for sensitive data."""

    def __init__(self, key: bytes = None, salt: bytes = None):
        """
        Initialize encryption provider.

        Args:
            key: 32-byte encryption key (if None, generates random key)
            salt: Salt used for key derivation (optional, for password-based keys)
        """
        if key is None:
            # Generate random 256-bit key
            key = AESGCM.generate_key(bit_length=256)

        self.key = key
        self.salt = salt  # Store salt for password-derived keys
        self.cipher = AESGCM(key)

    @classmethod
    def from_password(cls, password: str, salt: bytes = None):
        """
        Create encryption provider from password using PBKDF2.

        Args:
            password: Password to derive key from
            salt: Salt for key derivation (if None, generates random salt)

        Returns:
            EncryptionProvider instance with derived key
        """
        if salt is None:
            salt = os.urandom(16)  # 128-bit salt

        # Derive 256-bit key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits
            salt=salt,
            iterations=480000,  # OWASP recommended (2023)
        )
        key = kdf.derive(password.encode("utf-8"))

        return cls(key=key, salt=salt)

    def get_salt(self) -> bytes:
        """Get salt used for key derivation."""
        return self.salt

    def encrypt(self, data: Union[str, dict, Any]) -> bytes:
        """
        Encrypt data using AES-256-GCM.

        Args:
            data: Data to encrypt (string, dict, or JSON-serializable object)

        Returns:
            Encrypted data as bytes (includes nonce + ciphertext + tag)
        """
        # Convert data to bytes
        if isinstance(data, str):
            plaintext = data.encode("utf-8")
        else:
            # Serialize dict/object to JSON
            plaintext = json.dumps(data).encode("utf-8")

        # Generate random nonce (12 bytes for GCM)
        nonce = os.urandom(12)

        # Encrypt with authenticated encryption
        ciphertext = self.cipher.encrypt(nonce, plaintext, None)

        # Return nonce + ciphertext (nonce needed for decryption)
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> Union[str, dict, Any]:
        """
        Decrypt data using AES-256-GCM.

        Args:
            encrypted_data: Encrypted data (nonce + ciphertext + tag)

        Returns:
            Decrypted original data (string or dict)

        Raises:
            Exception: If decryption fails or data is tampered
        """
        # Extract nonce (first 12 bytes)
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        # Decrypt (will raise exception if tampered)
        plaintext = self.cipher.decrypt(nonce, ciphertext, None)

        # Try to parse as JSON first (for dicts)
        try:
            return json.loads(plaintext.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            # Return as string
            return plaintext.decode("utf-8")


class KeyManager:
    """Manages multiple encryption key versions and rotation."""

    def __init__(self):
        """Initialize key manager."""
        self.keys = {}  # version -> EncryptionProvider
        self.metadata = {}  # version -> metadata dict
        self.current_version = 1

        # Create initial key version 1
        self._create_key_version(version=1)

    def _create_key_version(self, version: int):
        """Create a new key version."""
        provider = EncryptionProvider()
        self.keys[version] = provider
        self.metadata[version] = {
            "version": version,
            "created_at": datetime.now(timezone.utc),
            "usage_count": 0,
        }

    def rotate_key(self, new_version: int):
        """
        Rotate to a new key version.

        Args:
            new_version: New key version number
        """
        self._create_key_version(version=new_version)
        self.current_version = new_version

    def encrypt(self, data, key_version: int = None):
        """
        Encrypt data with specific key version.

        Args:
            data: Data to encrypt
            key_version: Key version to use (default: current version)

        Returns:
            Encrypted data with version prefix
        """
        if key_version is None:
            key_version = self.current_version

        if key_version not in self.keys:
            raise ValueError(f"Key version {key_version} not found")

        # Encrypt with versioned key
        encrypted = self.keys[key_version].encrypt(data)

        # Increment usage count
        self.metadata[key_version]["usage_count"] += 1

        # Prepend version number (1 byte)
        return bytes([key_version]) + encrypted

    def decrypt(self, encrypted_data: bytes, key_version: int = None):
        """
        Decrypt data with specific key version.

        Args:
            encrypted_data: Encrypted data with version prefix
            key_version: Key version to use (if None, reads from prefix)

        Returns:
            Decrypted data
        """
        if key_version is None:
            # Extract version from first byte
            key_version = encrypted_data[0]
            encrypted_data = encrypted_data[1:]
        else:
            # Remove version prefix
            encrypted_data = encrypted_data[1:]

        if key_version not in self.keys:
            raise ValueError(f"Key version {key_version} not found")

        return self.keys[key_version].decrypt(encrypted_data)

    def get_key_metadata(self, version: int):
        """
        Get metadata for a key version.

        Args:
            version: Key version number

        Returns:
            Metadata dictionary
        """
        if version not in self.metadata:
            raise ValueError(f"Key version {version} not found")

        return self.metadata[version].copy()

    def re_encrypt(self, encrypted_data: bytes, old_version: int, new_version: int):
        """
        Re-encrypt data from old key version to new version.

        Args:
            encrypted_data: Data encrypted with old version
            old_version: Old key version
            new_version: New key version

        Returns:
            Data re-encrypted with new version
        """
        # Decrypt with old key
        decrypted = self.decrypt(encrypted_data, key_version=old_version)

        # Encrypt with new key
        return self.encrypt(decrypted, key_version=new_version)


class FieldEncryptor:
    """Field-level encryption for selective data protection."""

    def __init__(self, sensitive_fields: list = None, key: bytes = None):
        """
        Initialize field encryptor.

        Args:
            sensitive_fields: List of field paths to encrypt (supports dot notation)
            key: Encryption key (if None, generates random key)
        """
        self.sensitive_fields = sensitive_fields or []
        self.provider = EncryptionProvider(key=key)

    def _is_sensitive_field(self, field_path: str) -> bool:
        """Check if field path should be encrypted."""
        return field_path in self.sensitive_fields

    def _get_nested_value(self, data: dict, path: str):
        """Get value from nested dict using dot notation."""
        keys = path.split(".")
        value = data
        for key in keys:
            value = value.get(key)
            if value is None:
                return None
        return value

    def _set_nested_value(self, data: dict, path: str, value):
        """Set value in nested dict using dot notation."""
        keys = path.split(".")
        current = data
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value

    def encrypt_fields(self, data: dict) -> dict:
        """
        Encrypt sensitive fields in dictionary.

        Args:
            data: Dictionary with sensitive fields

        Returns:
            Dictionary with sensitive fields encrypted (base64 encoded)
        """
        import base64
        import copy

        result = copy.deepcopy(data)

        for field_path in self.sensitive_fields:
            # Handle nested fields (dot notation)
            if "." in field_path:
                value = self._get_nested_value(result, field_path)
                if value is not None:
                    encrypted = self.provider.encrypt(value)
                    encoded = base64.b64encode(encrypted).decode("utf-8")
                    self._set_nested_value(result, field_path, f"encrypted:{encoded}")
            else:
                # Handle top-level fields
                if field_path in result:
                    value = result[field_path]
                    encrypted = self.provider.encrypt(value)
                    # Base64 encode for string representation
                    encoded = base64.b64encode(encrypted).decode("utf-8")
                    result[field_path] = f"encrypted:{encoded}"

        return result

    def decrypt_fields(self, data: dict) -> dict:
        """
        Decrypt sensitive fields in dictionary.

        Args:
            data: Dictionary with encrypted fields

        Returns:
            Dictionary with sensitive fields decrypted
        """
        import base64
        import copy

        result = copy.deepcopy(data)

        for field_path in self.sensitive_fields:
            # Handle nested fields
            if "." in field_path:
                value = self._get_nested_value(result, field_path)
                if value and isinstance(value, str) and value.startswith("encrypted:"):
                    encoded = value.replace("encrypted:", "")
                    encrypted = base64.b64decode(encoded)
                    decrypted = self.provider.decrypt(encrypted)
                    self._set_nested_value(result, field_path, decrypted)
            else:
                # Handle top-level fields
                if field_path in result:
                    value = result[field_path]
                    if isinstance(value, str) and value.startswith("encrypted:"):
                        encoded = value.replace("encrypted:", "")
                        encrypted = base64.b64decode(encoded)
                        decrypted = self.provider.decrypt(encrypted)
                        result[field_path] = decrypted

        return result

    def mask_fields(self, data: dict, mask_char: str = "*") -> dict:
        """
        Mask sensitive fields for display.

        Args:
            data: Dictionary with sensitive fields
            mask_char: Character to use for masking

        Returns:
            Dictionary with sensitive fields masked
        """
        import copy

        result = copy.deepcopy(data)

        for field_path in self.sensitive_fields:
            if "." not in field_path and field_path in result:
                value = str(result[field_path])

                # Preserve separators (-, spaces) and mask each part
                if "-" in value:
                    parts = value.split("-")
                    masked_parts = []
                    for part in parts:
                        # Mask all characters in part except last 4 of entire value
                        masked_parts.append(mask_char * len(part))
                    # Restore last 4 digits from original value
                    masked_str = "-".join(masked_parts)
                    if len(value) > 4:
                        result[field_path] = masked_str[:-4] + value[-4:]
                    else:
                        result[field_path] = mask_char * len(value)
                else:
                    # No separators - simple masking
                    if len(value) > 4:
                        result[field_path] = mask_char * (len(value) - 4) + value[-4:]
                    else:
                        result[field_path] = mask_char * len(value)

        return result
