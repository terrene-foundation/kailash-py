"""
Encryption utilities for checkpoint security.

Provides AES-256-GCM encryption for checkpoint data at rest.
"""

import base64
import hashlib
import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.warning(
        "cryptography library not available. " "Install with: pip install cryptography"
    )


class EncryptionError(Exception):
    """Raised when encryption/decryption fails."""

    pass


class CheckpointEncryptor:
    """
    AES-256-GCM encryption for checkpoint data.

    Features:
    - AES-256-GCM authenticated encryption
    - Random nonce per encryption
    - Key derivation from passphrase (PBKDF2-HMAC-SHA256)
    - Authenticated encryption with additional data (AEAD)

    Security:
    - PCI DSS Requirement 3: Protect stored data
    - HIPAA § 164.312(a)(2)(iv): Encryption
    - GDPR Article 32: Security of processing
    """

    def __init__(
        self,
        encryption_key: str | bytes | None = None,
        key_env_var: str = "KAIZEN_ENCRYPTION_KEY",
        algorithm: Literal["aes-256-gcm"] = "aes-256-gcm",
    ):
        """
        Initialize checkpoint encryptor.

        Args:
            encryption_key: Encryption key (32 bytes for AES-256) or passphrase
            key_env_var: Environment variable name for key (default: KAIZEN_ENCRYPTION_KEY)
            algorithm: Encryption algorithm (only aes-256-gcm supported)

        Raises:
            EncryptionError: If cryptography library not available or invalid key
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise EncryptionError(
                "cryptography library required for encryption. "
                "Install with: pip install cryptography"
            )

        if algorithm != "aes-256-gcm":
            raise EncryptionError(f"Unsupported algorithm: {algorithm}")

        self.algorithm = algorithm

        # Get encryption key
        if encryption_key is None:
            # Try environment variable
            encryption_key = os.getenv(key_env_var)
            if not encryption_key:
                raise EncryptionError(
                    f"No encryption key provided. "
                    f"Set {key_env_var} environment variable or pass encryption_key parameter."
                )

        # Derive 32-byte key from passphrase if needed
        if isinstance(encryption_key, str):
            self.key = self._derive_key(encryption_key)
        elif isinstance(encryption_key, bytes) and len(encryption_key) == 32:
            self.key = encryption_key
        else:
            raise EncryptionError(
                "encryption_key must be a string (passphrase) or 32-byte key"
            )

        # Create AES-GCM cipher
        self.cipher = AESGCM(self.key)

        logger.info(f"Checkpoint encryption initialized (algorithm={self.algorithm})")

    def _derive_key(self, passphrase: str, salt: bytes | None = None) -> bytes:
        """
        Derive 32-byte key from passphrase using PBKDF2-HMAC-SHA256.

        Args:
            passphrase: User-provided passphrase
            salt: Optional salt (default: fixed salt for deterministic keys)

        Returns:
            32-byte encryption key
        """
        if salt is None:
            # Use fixed salt for deterministic key derivation
            # In production, consider using per-checkpoint salts stored alongside encrypted data
            salt = b"kaizen_checkpoint_encryption_salt_v1"

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits
            salt=salt,
            iterations=600000,  # OWASP recommended minimum
        )

        key = kdf.derive(passphrase.encode("utf-8"))
        return key

    def encrypt(self, plaintext: bytes, associated_data: bytes | None = None) -> bytes:
        """
        Encrypt plaintext with AES-256-GCM.

        Uses random nonce per encryption for security.

        Args:
            plaintext: Data to encrypt
            associated_data: Optional authenticated data (not encrypted but authenticated)

        Returns:
            Encrypted data (format: nonce + ciphertext + tag)

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Generate random 96-bit nonce (12 bytes) - recommended for AES-GCM
            nonce = os.urandom(12)

            # Encrypt with authenticated encryption
            ciphertext = self.cipher.encrypt(nonce, plaintext, associated_data)

            # Return: nonce (12 bytes) + ciphertext + tag (16 bytes, appended by GCM)
            encrypted = nonce + ciphertext

            logger.debug(
                f"Encrypted {len(plaintext)} bytes → {len(encrypted)} bytes "
                f"(overhead: {len(encrypted) - len(plaintext)} bytes)"
            )

            return encrypted

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Encryption failed: {e}")

    def decrypt(self, encrypted: bytes, associated_data: bytes | None = None) -> bytes:
        """
        Decrypt ciphertext encrypted with AES-256-GCM.

        Args:
            encrypted: Encrypted data (format: nonce + ciphertext + tag)
            associated_data: Optional authenticated data (must match encryption)

        Returns:
            Decrypted plaintext

        Raises:
            EncryptionError: If decryption fails (wrong key, tampered data, etc.)
        """
        try:
            # Extract nonce (first 12 bytes)
            if len(encrypted) < 12:
                raise EncryptionError("Invalid encrypted data: too short")

            nonce = encrypted[:12]
            ciphertext = encrypted[12:]

            # Decrypt and verify authentication tag
            plaintext = self.cipher.decrypt(nonce, ciphertext, associated_data)

            logger.debug(f"Decrypted {len(encrypted)} bytes → {len(plaintext)} bytes")

            return plaintext

        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Decryption failed: {e}")

    def encrypt_string(self, plaintext: str, associated_data: str | None = None) -> str:
        """
        Encrypt string and return base64-encoded ciphertext.

        Convenience method for string encryption.

        Args:
            plaintext: String to encrypt
            associated_data: Optional authenticated data

        Returns:
            Base64-encoded encrypted data
        """
        plaintext_bytes = plaintext.encode("utf-8")
        associated_bytes = associated_data.encode("utf-8") if associated_data else None

        encrypted = self.encrypt(plaintext_bytes, associated_bytes)
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt_string(
        self, encrypted_b64: str, associated_data: str | None = None
    ) -> str:
        """
        Decrypt base64-encoded ciphertext to string.

        Convenience method for string decryption.

        Args:
            encrypted_b64: Base64-encoded encrypted data
            associated_data: Optional authenticated data (must match encryption)

        Returns:
            Decrypted string
        """
        encrypted = base64.b64decode(encrypted_b64.encode("ascii"))
        associated_bytes = associated_data.encode("utf-8") if associated_data else None

        plaintext_bytes = self.decrypt(encrypted, associated_bytes)
        return plaintext_bytes.decode("utf-8")


class KeyManager:
    """
    Secure key management for checkpoint encryption.

    Supports multiple key sources:
    - Environment variables
    - Key files
    - Hardware Security Modules (HSM) - future
    - Cloud KMS (AWS KMS, Azure Key Vault, GCP KMS) - future
    """

    @staticmethod
    def generate_key() -> bytes:
        """
        Generate cryptographically secure 32-byte key.

        Returns:
            32-byte random key suitable for AES-256
        """
        return os.urandom(32)

    @staticmethod
    def key_to_base64(key: bytes) -> str:
        """
        Encode key as base64 string.

        Args:
            key: Binary key

        Returns:
            Base64-encoded key
        """
        return base64.b64encode(key).decode("ascii")

    @staticmethod
    def key_from_base64(key_b64: str) -> bytes:
        """
        Decode base64-encoded key.

        Args:
            key_b64: Base64-encoded key

        Returns:
            Binary key
        """
        return base64.b64decode(key_b64.encode("ascii"))

    @staticmethod
    def save_key_to_file(key: bytes, file_path: str, overwrite: bool = False) -> None:
        """
        Save encryption key to file (base64-encoded).

        WARNING: Protect this file with appropriate permissions (chmod 600).

        Args:
            key: Encryption key
            file_path: Path to save key
            overwrite: Whether to overwrite existing file

        Raises:
            FileExistsError: If file exists and overwrite=False
            IOError: If write fails
        """
        import os
        from pathlib import Path

        path = Path(file_path)

        if path.exists() and not overwrite:
            raise FileExistsError(
                f"Key file already exists: {file_path}. "
                "Set overwrite=True to replace."
            )

        try:
            # Create parent directory if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write key (base64-encoded)
            key_b64 = KeyManager.key_to_base64(key)
            path.write_text(key_b64)

            # Set restrictive permissions (owner read/write only)
            if os.name != "nt":  # Unix-like systems
                os.chmod(file_path, 0o600)

            logger.info(f"Encryption key saved to: {file_path}")

        except Exception as e:
            logger.error(f"Failed to save key to {file_path}: {e}")
            raise IOError(f"Failed to save key: {e}")

    @staticmethod
    def load_key_from_file(file_path: str) -> bytes:
        """
        Load encryption key from file.

        Args:
            file_path: Path to key file

        Returns:
            Encryption key

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If invalid key format
        """
        from pathlib import Path

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Key file not found: {file_path}")

        try:
            key_b64 = path.read_text().strip()
            key = KeyManager.key_from_base64(key_b64)

            if len(key) != 32:
                raise ValueError(f"Invalid key size: {len(key)} bytes (expected 32)")

            logger.info(f"Encryption key loaded from: {file_path}")
            return key

        except Exception as e:
            logger.error(f"Failed to load key from {file_path}: {e}")
            raise ValueError(f"Invalid key file: {e}")

    @staticmethod
    def derive_key_from_password(
        password: str, salt: bytes | None = None, iterations: int = 600000
    ) -> bytes:
        """
        Derive encryption key from password using PBKDF2-HMAC-SHA256.

        Args:
            password: User password
            salt: Optional salt (generates random if None)
            iterations: Number of iterations (default: 600000 per OWASP)

        Returns:
            32-byte encryption key
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations
        )

        key = kdf.derive(password.encode("utf-8"))
        return key

    @staticmethod
    def hash_key_for_verification(key: bytes) -> str:
        """
        Generate SHA-256 hash of key for verification (not secure storage).

        Useful for checking if the correct key is being used without exposing the key.

        Args:
            key: Encryption key

        Returns:
            SHA-256 hash (hex string)
        """
        return hashlib.sha256(key).hexdigest()


# Convenience functions
def encrypt_checkpoint(
    checkpoint_data: str, encryption_key: str | bytes | None = None
) -> str:
    """
    Encrypt checkpoint JSON data.

    Args:
        checkpoint_data: JSON string of checkpoint
        encryption_key: Encryption key or passphrase

    Returns:
        Base64-encoded encrypted data
    """
    encryptor = CheckpointEncryptor(encryption_key=encryption_key)
    return encryptor.encrypt_string(checkpoint_data)


def decrypt_checkpoint(
    encrypted_data: str, encryption_key: str | bytes | None = None
) -> str:
    """
    Decrypt checkpoint JSON data.

    Args:
        encrypted_data: Base64-encoded encrypted checkpoint
        encryption_key: Encryption key or passphrase

    Returns:
        Decrypted JSON string
    """
    encryptor = CheckpointEncryptor(encryption_key=encryption_key)
    return encryptor.decrypt_string(encrypted_data)


__all__ = [
    "CheckpointEncryptor",
    "KeyManager",
    "EncryptionError",
    "encrypt_checkpoint",
    "decrypt_checkpoint",
]
