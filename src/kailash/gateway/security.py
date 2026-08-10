"""Security and secret management for gateway.

This module provides credential management with multiple backend options for
storing secrets. Only :class:`FileSecretBackend` encrypts what it stores;
:class:`EnvironmentSecretBackend` holds values in the process environment and
:class:`SecretManager`'s own Fernet layer is applied by the caller, so read the
backend you actually construct before assuming a secret is protected at rest.
"""

import asyncio
import base64
import binascii
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..trust._locking import safe_read_json, validate_id
from ..utils.file_permissions import (
    OWNER_ONLY_MODE,
    restrict_dir_to_owner,
    restrict_to_owner,
)

logger = logging.getLogger(__name__)


class SecretNotFoundError(Exception):
    """Raised when secret is not found."""

    pass


class SecretEncryptionError(Exception):
    """Raised when a secret cannot be encrypted, decrypted, or keyed.

    Deliberately NOT a subclass of :class:`SecretNotFoundError`: a caller that
    treats "missing" as "fall back to a default" must not silently take that
    branch when the real answer is "present, but I could not decrypt it".
    """

    pass


class LegacyPlaintextSecretError(SecretEncryptionError):
    """Raised when a secret file predates envelope encryption.

    Read as a MIGRATION instruction, not a transient failure: versions of
    :class:`FileSecretBackend` up to and including kailash 2.58 wrote secrets
    in cleartext. Those files are readable by anyone with filesystem access and
    are treated as compromised; re-store the secret rather than reading it.

    There is deliberately no plaintext fallback. A fallback would let anyone
    who can write into the secrets directory replace an envelope with a
    plaintext file of their choosing and have it honoured — a downgrade oracle
    that removes the protection this class exists to provide.
    """

    pass


class SecretBackend(ABC):
    """Abstract backend for secret storage."""

    @abstractmethod
    async def get_secret(self, reference: str) -> Union[str, Dict[str, Any]]:
        """Get secret by reference."""
        pass

    @abstractmethod
    async def store_secret(
        self, reference: str, secret: Union[str, Dict[str, Any]]
    ) -> None:
        """Store a secret."""
        pass

    @abstractmethod
    async def delete_secret(self, reference: str) -> None:
        """Delete a secret."""
        pass


class SecretManager:
    """Manages secrets for resource credentials."""

    def __init__(
        self,
        backend: Optional[SecretBackend] = None,
        encryption_key: Optional[str] = None,
        cache_ttl: int = 300,  # 5 minutes
    ):
        self.backend = backend or EnvironmentSecretBackend()
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._ttl = timedelta(seconds=cache_ttl)
        self._lock = asyncio.Lock()

        # Set up encryption
        if encryption_key:
            self._cipher = Fernet(encryption_key.encode())
        else:
            # Generate key from environment or use default
            key = os.environ.get("KAILASH_ENCRYPTION_KEY")
            if not key:
                # Warning: This is not secure for production!
                logger.warning(
                    "Using default encryption key - not secure for production!"
                )
                # Generate a proper Fernet key
                key = Fernet.generate_key()
            elif isinstance(key, str):
                key = key.encode()
            self._cipher = Fernet(key)

    async def get_secret(self, reference: str) -> Union[str, Dict[str, Any]]:
        """Get secret by reference."""
        async with self._lock:
            # Check cache
            if reference in self._cache:
                value, timestamp = self._cache[reference]
                if datetime.now(UTC) - timestamp < self._ttl:
                    return value
                else:
                    # Expired, remove from cache
                    del self._cache[reference]

        # Fetch from backend
        encrypted_secret = await self.backend.get_secret(reference)

        # Decrypt if needed
        if isinstance(encrypted_secret, str) and encrypted_secret.startswith(
            "encrypted:"
        ):
            decrypted = self._cipher.decrypt(encrypted_secret[10:].encode()).decode()
            secret = json.loads(decrypted)
        elif isinstance(encrypted_secret, dict) and "value" in encrypted_secret:
            # Handle case where backend returns {"value": "encrypted:..."}
            value = encrypted_secret["value"]
            if isinstance(value, str) and value.startswith("encrypted:"):
                decrypted = self._cipher.decrypt(value[10:].encode()).decode()
                secret = json.loads(decrypted)
            else:
                secret = encrypted_secret
        else:
            secret = encrypted_secret

        # Cache it
        async with self._lock:
            self._cache[reference] = (secret, datetime.now(UTC))

        return secret

    async def store_secret(
        self, reference: str, secret: Dict[str, Any], encrypt: bool = True
    ) -> None:
        """Store a secret."""
        if encrypt:
            # Encrypt the secret
            secret_json = json.dumps(secret)
            encrypted = self._cipher.encrypt(secret_json.encode())
            encrypted_value = f"encrypted:{encrypted.decode()}"
            await self.backend.store_secret(reference, encrypted_value)
        else:
            await self.backend.store_secret(reference, secret)

        # Clear from cache
        async with self._lock:
            if reference in self._cache:
                del self._cache[reference]

    async def delete_secret(self, reference: str) -> None:
        """Delete a secret."""
        await self.backend.delete_secret(reference)

        # Clear from cache
        async with self._lock:
            if reference in self._cache:
                del self._cache[reference]

    async def clear_cache(self):
        """Clear the secret cache."""
        async with self._lock:
            self._cache.clear()


class EnvironmentSecretBackend(SecretBackend):
    """Secret backend using environment variables."""

    def __init__(self, prefix: str = "KAILASH_SECRET_"):
        self.prefix = prefix

    async def get_secret(self, reference: str) -> Union[str, Dict[str, Any]]:
        """Get secret from environment."""
        # Convert reference to env var name
        env_var = f"{self.prefix}{reference.upper()}"

        value = os.environ.get(env_var)
        if not value:
            raise SecretNotFoundError(f"Secret {reference} not found")

        # Try to parse as JSON
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Return as simple key-value
            return {"value": value}

    async def store_secret(self, reference: str, secret: Any) -> None:
        """Store secret in environment (not recommended for production)."""
        env_var = f"{self.prefix}{reference.upper()}"

        if isinstance(secret, dict):
            os.environ[env_var] = json.dumps(secret)
        else:
            os.environ[env_var] = str(secret)

    async def delete_secret(self, reference: str) -> None:
        """Delete secret from environment."""
        env_var = f"{self.prefix}{reference.upper()}"
        if env_var in os.environ:
            del os.environ[env_var]


#: Envelope format version written by :class:`FileSecretBackend`.
SECRET_ENVELOPE_VERSION = 1

#: KDF identifier recorded in — and required by — the envelope.
SECRET_ENVELOPE_KDF = "pbkdf2-sha256"

#: PBKDF2 iteration count used for new envelopes. Matches
#: ``kailash.trust.security.SecureKeyStorage``.
SECRET_KDF_ITERATIONS = 100_000

#: Floor accepted when READING an envelope. The iteration count is read back
#: from the file, and anyone able to write into the secrets directory could
#: otherwise hand us ``iterations: 1`` and turn every subsequent read into a
#: cheap oracle for brute-forcing the master key.
_MIN_KDF_ITERATIONS = 100_000

#: Ceiling accepted when reading, so the same writer cannot turn a read into an
#: unbounded CPU burn.
_MAX_KDF_ITERATIONS = 10_000_000

#: Salt length in bytes. Fresh per stored secret, persisted in the envelope.
_SALT_BYTES = 32


class FileSecretBackend(SecretBackend):
    """Secret backend that encrypts each secret at rest in its own file.

    Every secret is stored as a JSON envelope::

        {"v": 1, "kdf": "pbkdf2-sha256", "iterations": 100000,
         "salt": "<base64>", "ciphertext": "<Fernet token>"}

    The salt is generated fresh for every ``store_secret`` call and persisted
    alongside the ciphertext, so the store survives a process restart and no
    two files share a derived key. The master key itself is never written.

    Args:
        secrets_dir: Directory holding one file per secret. Created ``0o700``.
        master_key: The passphrase to derive from. Prefer the environment
            variable; pass this only when the key comes from another vault.
        master_key_source: Name of the environment variable read when
            ``master_key`` is not given. Defaults to
            ``KAILASH_SECRETS_MASTER_KEY``.

    Raises:
        SecretEncryptionError: If no master key is available. This is
            deliberate and fails CLOSED at construction — a backend that
            quietly generated its own key would either write secrets nobody can
            recover after a restart, or write them under a key with no secrecy
            at all.

    Note:
        Files written by kailash <= 2.58 are cleartext and are NOT readable
        here; reading one raises :class:`LegacyPlaintextSecretError`. Treat
        those secrets as disclosed, rotate them, and store them again.
    """

    def __init__(
        self,
        secrets_dir: str = "/etc/kailash/secrets",
        *,
        master_key: Optional[str] = None,
        master_key_source: str = "KAILASH_SECRETS_MASTER_KEY",
    ):
        self.secrets_dir = secrets_dir
        self.master_key_source = master_key_source

        key = (
            master_key if master_key is not None else os.environ.get(master_key_source)
        )
        if not key:
            raise SecretEncryptionError(
                f"No master key for encrypted secret storage. Set the "
                f"{master_key_source} environment variable, or pass "
                f"master_key= explicitly. Refusing to store secrets that "
                f"would not be encrypted."
            )
        self._master_key = key.encode() if isinstance(key, str) else key

        os.makedirs(secrets_dir, mode=0o700, exist_ok=True)
        # makedirs' mode is masked by the umask and ignored entirely for a
        # directory that already exists, so re-apply. Per-file 0o600 does not
        # compensate for a listable secrets directory: the reference names
        # alone tell an attacker which credentials exist and where.
        if not restrict_dir_to_owner(secrets_dir):
            logger.warning(
                "Secrets directory %s could not be made owner-only on this "
                "platform; its listing is NOT private.",
                secrets_dir,
            )

    def _path_for(self, reference: str) -> str:
        """Resolve a reference to its file, rejecting traversal.

        ``reference`` reaches ``os.path.join`` unmodified, so without this an
        argument of ``../../etc/kailash/authorized_keys`` would read, write, or
        delete outside the store.
        """
        validate_id(reference)
        return os.path.join(self.secrets_dir, f"{reference}.json")

    def _cipher_for(self, salt: bytes, iterations: int) -> Fernet:
        """Derive the per-file Fernet key from the master key and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations,
        )
        return Fernet(base64.urlsafe_b64encode(kdf.derive(self._master_key)))

    async def get_secret(self, reference: str) -> Union[str, Dict[str, Any]]:
        """Decrypt and return the secret stored under ``reference``.

        Raises:
            SecretNotFoundError: No file for this reference.
            LegacyPlaintextSecretError: The file predates envelope encryption.
            SecretEncryptionError: The envelope is malformed, uses an
                unsupported format, or does not decrypt under this master key.
            OSError: The path is a symlink (refused, not followed).
        """
        file_path = self._path_for(reference)

        # Single O_NOFOLLOW open rather than exists()-then-open(): the latter
        # leaves a window in which the path can be swapped for a symlink
        # pointing anywhere the process can read.
        try:
            envelope = safe_read_json(Path(file_path))
        except FileNotFoundError:
            raise SecretNotFoundError(f"Secret {reference} not found")
        except json.JSONDecodeError as e:
            # Cleartext strings were written verbatim by the old code, so most
            # legacy files are not even JSON.
            raise LegacyPlaintextSecretError(
                f"Secret {reference} is not an encrypted envelope. Files "
                f"written by kailash <= 2.58 are cleartext; rotate the secret "
                f"and store it again."
            ) from e

        return self._open_envelope(reference, envelope)

    def _open_envelope(
        self, reference: str, envelope: Any
    ) -> Union[str, Dict[str, Any]]:
        """Validate an envelope and decrypt it. No plaintext fallback, ever."""
        if not isinstance(envelope, dict) or "ciphertext" not in envelope:
            raise LegacyPlaintextSecretError(
                f"Secret {reference} is stored in cleartext, not an encrypted "
                f"envelope. Rotate the secret and store it again; it is "
                f"deliberately NOT read as-is."
            )

        version = envelope.get("v")
        if version != SECRET_ENVELOPE_VERSION:
            raise SecretEncryptionError(
                f"Secret {reference} uses envelope version {version!r}, "
                f"expected {SECRET_ENVELOPE_VERSION}."
            )

        kdf_name = envelope.get("kdf")
        if kdf_name != SECRET_ENVELOPE_KDF:
            raise SecretEncryptionError(
                f"Secret {reference} names KDF {kdf_name!r}, expected "
                f"{SECRET_ENVELOPE_KDF!r}."
            )

        iterations = envelope.get("iterations")
        if (
            not isinstance(iterations, int)
            or isinstance(iterations, bool)
            or not _MIN_KDF_ITERATIONS <= iterations <= _MAX_KDF_ITERATIONS
        ):
            raise SecretEncryptionError(
                f"Secret {reference} declares an unacceptable iteration count "
                f"{iterations!r}; refusing to derive a key weaker than "
                f"{_MIN_KDF_ITERATIONS}."
            )

        try:
            salt = base64.b64decode(envelope["salt"], validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as e:
            raise SecretEncryptionError(
                f"Secret {reference} has a missing or malformed salt."
            ) from e
        if len(salt) < 16:
            raise SecretEncryptionError(
                f"Secret {reference} has a {len(salt)}-byte salt; refusing to "
                f"derive a key from fewer than 16."
            )

        ciphertext = envelope["ciphertext"]
        if not isinstance(ciphertext, str):
            raise SecretEncryptionError(
                f"Secret {reference} has a non-string ciphertext."
            )

        try:
            plaintext = self._cipher_for(salt, iterations).decrypt(ciphertext.encode())
        except InvalidToken as e:
            # Covers both a wrong master key and a tampered file: Fernet
            # authenticates the ciphertext, and neither case may return data.
            raise SecretEncryptionError(
                f"Secret {reference} did not decrypt. The master key in "
                f"{self.master_key_source} does not match the one it was "
                f"stored under, or the file has been modified."
            ) from e

        return json.loads(plaintext.decode())

    async def store_secret(self, reference: str, secret: Any) -> None:
        """Encrypt ``secret`` and write it owner-only under ``reference``."""
        file_path = self._path_for(reference)

        salt = os.urandom(_SALT_BYTES)
        cipher = self._cipher_for(salt, SECRET_KDF_ITERATIONS)
        # json.dumps rather than str(): it round-trips dicts and strings back
        # to their original type, so get_secret returns what was handed in.
        token = cipher.encrypt(json.dumps(secret).encode())
        envelope = {
            "v": SECRET_ENVELOPE_VERSION,
            "kdf": SECRET_ENVELOPE_KDF,
            "iterations": SECRET_KDF_ITERATIONS,
            "salt": base64.b64encode(salt).decode(),
            "ciphertext": token.decode(),
        }

        # Create restricted up front rather than writing then chmod'ing: the
        # latter leaves the file world-readable for the whole write window.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(file_path, flags, OWNER_ONLY_MODE)
        try:
            # An existing file keeps its original mode, since the mode argument
            # applies only on creation, so re-apply on the open descriptor.
            #
            # NOTE: owner-only access is enforced on POSIX. On Windows the
            # returned flag is False unless pywin32 is present, and the file is
            # then NOT confidential -- see kailash.utils.file_permissions.
            restrict_to_owner(file_path, fd=fd)
            f = os.fdopen(fd, "w")
        except Exception:
            os.close(fd)
            raise

        with f:
            json.dump(envelope, f)

    async def delete_secret(self, reference: str) -> None:
        """Delete secret file."""
        file_path = self._path_for(reference)
        try:
            os.remove(file_path)
        except FileNotFoundError:
            # Deleting an absent secret has always been a no-op; keep that,
            # but without the exists()-then-remove race.
            pass


# For production, you would implement:
# - VaultSecretBackend for HashiCorp Vault
# - AWSSecretsManagerBackend for AWS Secrets Manager
# - AzureKeyVaultBackend for Azure Key Vault
# - GCPSecretManagerBackend for Google Cloud Secret Manager
