"""Data encryption and decryption for Kaizen AI framework."""

import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

#: Environment variable holding the key material for this module. Shared with
#: ``CheckpointEncryptor`` (``kaizen.core.autonomy.security.encryption``) and
#: already mapped to ``KaizenConfig.encryption_key``, so an operator configures
#: Kaizen encryption in one place rather than one variable per subsystem.
KAIZEN_ENCRYPTION_KEY_ENV = "KAIZEN_ENCRYPTION_KEY"

#: Required length of raw key material, in bytes (AES-256).
AES_256_KEY_BYTES = 32

#: PBKDF2 iterations used to stretch a passphrase. Set to match
#: ``CheckpointEncryptor`` (``kaizen.core.autonomy.security.encryption``), which
#: stretches the SAME environment variable, so the cost of configuring Kaizen
#: encryption does not depend on which subsystem happens to read it first.
_PASSPHRASE_KDF_ITERATIONS = 600_000

#: Fixed salt for passphrase derivation. Deliberately FIXED, not random: the
#: derived key has to be the same in every process that reads the same
#: passphrase, or the store does not survive a restart — which is the defect
#: this module is being fixed for (#2092). A random per-process salt here would
#: reproduce it one layer down. Salts are not secret; their job in a
#: deterministic derivation is domain separation, which a constant provides.
#:
#: This value is deliberately DIFFERENT from ``CheckpointEncryptor``'s
#: ``b"kaizen_checkpoint_encryption_salt_v1"``. The two subsystems read one
#: variable but MUST NOT share a key: domain separation means a checkpoint
#: ciphertext cannot be opened with this module's key, or vice versa. So the
#: matching iteration count above buys equal derivation cost, NOT
#: interchangeable keys — do not "align" these salts to make the two
#: interoperate, because non-interoperability is the point.
_PASSPHRASE_KDF_SALT = b"kaizen.security.encryption.passphrase.v1"

#: Shortest accepted passphrase, matching ``SecretManager`` (#2041 / PR #2063)
#: and ``kailash.trust.auth.jwt.JWTConfig``. 600k PBKDF2 iterations do not
#: rescue a four-character passphrase: the search space, not the stretching,
#: is what bounds an offline attack on material that is never rotated.
MIN_PASSPHRASE_LENGTH = 32


class EncryptionKeyNotConfiguredError(ValueError):
    """Raised when an encryption primitive is built with no key material.

    Subclasses :class:`ValueError` because it reports an invalid argument, and
    because callers already guarding construction with ``except ValueError``
    keep working.

    Distinct from ``kaizen.core.autonomy.security.encryption.EncryptionError``,
    which reports a FAILED encrypt/decrypt in the checkpoint subsystem. This one
    reports missing configuration and is raised before any data is touched. The
    two live in different subsystems deliberately: importing the autonomy error
    here would make this leaf module depend on ``kaizen.core.autonomy``.
    """


@lru_cache(maxsize=1)
def _warn_ephemeral_encryption_key() -> None:
    """Announce, once per process, that encryption keys are ephemeral.

    ERROR rather than WARNING, and once per process rather than once per
    instance. What it replaces was silence — this path previously emitted no
    error, no warning, not even an INFO line, so the first symptom of the defect
    was unreadable data with nothing in the logs pointing at why.

    The variable name is spelled out literally rather than interpolated from
    :data:`KAIZEN_ENCRYPTION_KEY_ENV`. Nothing sensitive is involved either way —
    this is the NAME of an environment variable, never a value — but CodeQL's
    ``py/clear-text-logging-sensitive-data`` matches on identifier names and
    reads a constant called ``..._ENCRYPTION_KEY_ENV`` as key material. A
    literal has no dataflow into the sink at all. The drift this buys is pinned
    by ``test_the_loud_signal_names_the_current_constants``.

    The generated key is NEVER logged, in any encoding: a fix that fails loudly
    must not turn a durability bug into a disclosure bug.
    """
    logger.error(
        "Kaizen encryption keys were GENERATED, not configured: "
        "allow_ephemeral_key=True and no key was supplied. The key exists only "
        "inside this process, so anything encrypted now is UNRECOVERABLE after "
        "a restart, and another replica encrypts under a different key and "
        "cannot read these values. This is for local development only. Set "
        "KAIZEN_ENCRYPTION_KEY, or pass key= (a 32-byte value or a passphrase), "
        "and leave allow_ephemeral_key at its default of False."
    )


def _derive_key_from_passphrase(passphrase: str) -> bytes:
    """Stretch a passphrase into a 32-byte AES key, deterministically.

    Deterministic is the whole requirement: the same passphrase must yield the
    same key in every process, or encrypted data does not survive a restart.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=AES_256_KEY_BYTES,
        salt=_PASSPHRASE_KDF_SALT,
        iterations=_PASSPHRASE_KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def resolve_key_material(
    key: Union[bytes, str, None],
    *,
    allow_ephemeral_key: bool = False,
    what: str = "EncryptionProvider",
) -> bytes:
    """Resolve key material for an encryption primitive, or refuse to build one.

    One chokepoint shared by :class:`EncryptionProvider`, :class:`KeyManager`
    and :class:`FieldEncryptor`, so the floor and the wiring message cannot
    drift between the three classes that all mint AES keys in this module.

    Resolution order: the explicit ``key`` argument, then
    ``KAIZEN_ENCRYPTION_KEY``. If neither is present this RAISES — it does not
    generate one. Releases up to kaizen 0.9 generated a key here in total
    silence, which made every value the process encrypted unreadable after it
    exited.

    Args:
        key: 32 raw bytes, or a passphrase of at least
            :data:`MIN_PASSPHRASE_LENGTH` characters to stretch. ``None`` falls
            through to the environment.
        allow_ephemeral_key: Opt in to a generated process-local key for local
            development. Announces itself once per process at ERROR level.
        what: Class name used in the error message.

    Returns:
        32 bytes of key material.

    Raises:
        EncryptionKeyNotConfiguredError: If no key is configured and
            ``allow_ephemeral_key`` is False, if raw key material is the wrong
            length, or if a passphrase is shorter than
            :data:`MIN_PASSPHRASE_LENGTH`.
    """
    if key is None:
        env_value = os.environ.get(KAIZEN_ENCRYPTION_KEY_ENV)
        if env_value:
            key = env_value

    if isinstance(key, str):
        # An EMPTY or whitespace-only passphrase is treated as NOT CONFIGURED,
        # never as a passphrase. `EncryptionProvider(key=os.environ.get("K", ""))`
        # is the ordinary way a caller expresses "unset", and stretching "" would
        # derive a fixed key that anyone reading this module can reproduce from
        # the constants above — a WORSE outcome than the generated key this fix
        # removes, because it is stable, shared by every deployment, and looks
        # configured. Falling through to the bottom of this function gives it the
        # same fail-closed treatment as key=None.
        if key.strip():
            # Measured stripped, but stretched VERBATIM: " " * 32 clears a naive
            # length check while carrying no entropy, and silently trimming would
            # change the derived key for anyone whose passphrase legitimately
            # ends in whitespace — re-deriving a different key from the same
            # configured value is the exact failure this module is being fixed
            # for.
            if len(key.strip()) < MIN_PASSPHRASE_LENGTH:
                # The length is named; the passphrase is NOT. An exception
                # message reaches logs and crash reports (`security.md`).
                raise EncryptionKeyNotConfiguredError(
                    f"{what} received a passphrase of {len(key.strip())} "
                    f"non-whitespace characters; at least "
                    f"{MIN_PASSPHRASE_LENGTH} are required. A passphrase that "
                    f"brief is brute-forceable regardless of the KDF's "
                    f"iteration count, and whitespace padding adds length "
                    f"without adding entropy. Pass "
                    f"{AES_256_KEY_BYTES} raw bytes instead if you are "
                    f"supplying a generated key rather than a passphrase. Note "
                    f"that leading and trailing whitespace IS significant in "
                    f"the passphrase itself — it is measured trimmed but used "
                    f"verbatim, so a stray newline changes the derived key."
                )
            return _derive_key_from_passphrase(key)

    if isinstance(key, (bytes, bytearray)):
        if len(key) != AES_256_KEY_BYTES:
            raise EncryptionKeyNotConfiguredError(
                f"{what} requires {AES_256_KEY_BYTES} bytes of raw key material "
                f"for AES-256, got {len(key)}. Pass a {AES_256_KEY_BYTES}-byte "
                "value, or pass a passphrase as a str and it will be stretched "
                "with PBKDF2-HMAC-SHA256."
            )
        return bytes(key)

    if allow_ephemeral_key:
        _warn_ephemeral_encryption_key()
        return AESGCM.generate_key(bit_length=256)

    raise EncryptionKeyNotConfiguredError(
        f"{what} requires an encryption key and will not generate one: set the "
        "KAIZEN_ENCRYPTION_KEY environment variable, or pass key= (a 32-byte "
        "value or a passphrase). Pass allow_ephemeral_key=True ONLY for local "
        "development — a generated key lives in this process, so anything "
        "encrypted under it is unrecoverable once the process exits and other "
        "replicas cannot read it (issue #2092)."
    )


class EncryptionProvider:
    """AES-256-GCM encryption provider for sensitive data.

    **A key is required, and there is no default.** With neither ``key=`` nor
    ``KAIZEN_ENCRYPTION_KEY`` set this refuses to construct rather than minting
    a throwaway key: releases up to kaizen 0.9 did exactly that, silently, which
    made every value encrypted by the process unreadable after a restart and
    left a multi-replica deployment unable to read its own data (#2092).
    """

    def __init__(
        self,
        key: Union[bytes, str, None] = None,
        salt: bytes = None,
        *,
        allow_ephemeral_key: bool = False,
    ):
        """
        Initialize encryption provider.

        Args:
            key: 32-byte encryption key, or a passphrase (str) of at least
                :data:`MIN_PASSPHRASE_LENGTH` characters stretched with
                PBKDF2-HMAC-SHA256. When omitted, ``KAIZEN_ENCRYPTION_KEY`` is
                read. An empty or whitespace-only string counts as NOT
                configured, never as a passphrase. If neither is configured this
                RAISES rather than generating a key — a generated key would make
                everything encrypted under it unrecoverable at the next restart.
            salt: Salt used for key derivation (optional, for password-based
                keys created through :meth:`from_password`).
            allow_ephemeral_key: Opt in to a generated process-local key for
                local development. Announces itself once per process at ERROR
                level. Data encrypted under it CANNOT be read after this process
                exits.

        Raises:
            EncryptionKeyNotConfiguredError: If no key is configured and
                ``allow_ephemeral_key`` is False.
        """
        key = resolve_key_material(
            key,
            allow_ephemeral_key=allow_ephemeral_key,
            what="EncryptionProvider",
        )

        self.key = key
        self.salt = salt  # Store salt for password-derived keys
        self.cipher = AESGCM(key)

    @classmethod
    def from_password(cls, password: str, salt: bytes = None):
        """
        Create encryption provider from password using PBKDF2.

        **The caller MUST persist the salt.** When ``salt`` is omitted a random
        one is generated, and :meth:`encrypt` does NOT store it beside the
        ciphertext — only the nonce travels with the data. A caller who does not
        persist :meth:`get_salt` and pass it back cannot re-derive the key, and
        the data is unreadable for the same reason #2092 describes, by a
        different mechanism. Pass an explicit ``salt`` you already store, or
        store ``provider.get_salt()`` alongside the ciphertext.

        For the common case — one key for the process, configured by an
        operator — construct ``EncryptionProvider()`` directly and set
        ``KAIZEN_ENCRYPTION_KEY``; that path derives deterministically and needs
        no salt bookkeeping.

        The passphrase floor is the SAME one :func:`resolve_key_material`
        applies. This classmethod derives its own key and hands the resulting
        ``bytes`` to the constructor, which accepts any correctly-sized raw key
        — so without an explicit check here a caller could clear a floor of 32
        characters simply by switching constructors, and
        ``EncryptionProvider.from_password("x")`` would succeed on the same
        public class whose sibling constructor refuses 31 characters. A floor a
        caller can route around is not a floor.

        Args:
            password: Password to derive key from. At least
                :data:`MIN_PASSPHRASE_LENGTH` characters; empty or
                whitespace-only is rejected.
            salt: Salt for key derivation (if None, generates a random salt that
                the caller must persist via :meth:`get_salt`)

        Returns:
            EncryptionProvider instance with derived key

        Raises:
            EncryptionKeyNotConfiguredError: If ``password`` is shorter than
                :data:`MIN_PASSPHRASE_LENGTH` non-whitespace characters.
        """
        # Measured stripped, derived VERBATIM below — same semantics as
        # resolve_key_material, so a password ending in whitespace keeps
        # deriving the key it always did.
        if not isinstance(password, str) or len(password.strip()) < (
            MIN_PASSPHRASE_LENGTH
        ):
            measured = len(password.strip()) if isinstance(password, str) else 0
            # Names the length, never the password.
            raise EncryptionKeyNotConfiguredError(
                f"EncryptionProvider.from_password received a password of "
                f"{measured} non-whitespace characters; at least "
                f"{MIN_PASSPHRASE_LENGTH} are required. This is the same floor "
                f"EncryptionProvider(key=...) enforces — deriving through this "
                f"classmethod is not a way around it."
            )

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
    """Manages multiple encryption key versions and rotation.

    Every version's key is DERIVED from one configured master key rather than
    generated, so the manager can read back what it wrote after a restart. It
    previously took no key parameter at all and called ``EncryptionProvider()``
    bare for each version, which meant every version was throwaway: a restart
    made all stored ciphertext permanently unreadable, and :meth:`re_encrypt` —
    the documented migration path — destroyed the pre-rotation data too (#2092).

    Derivation is HKDF-SHA256 over the master key with the version number as
    ``info``, so versions are cryptographically distinct (rotation is real) and
    reproducible (rotation is durable).
    """

    def __init__(
        self,
        key: Union[bytes, str, None] = None,
        *,
        allow_ephemeral_key: bool = False,
    ):
        """Initialize key manager.

        Args:
            key: Master key material — 32 bytes, or a passphrase of at least
                :data:`MIN_PASSPHRASE_LENGTH` characters stretched with
                PBKDF2-HMAC-SHA256. When omitted, ``KAIZEN_ENCRYPTION_KEY`` is
                read. An empty or whitespace-only string counts as NOT
                configured. If neither is configured this RAISES.
            allow_ephemeral_key: Opt in to a generated process-local master key
                for local development. Announces itself once per process at
                ERROR level. Nothing encrypted under it survives this process.

        Raises:
            EncryptionKeyNotConfiguredError: If no key is configured and
                ``allow_ephemeral_key`` is False.
        """
        self._master_key = resolve_key_material(
            key,
            allow_ephemeral_key=allow_ephemeral_key,
            what="KeyManager",
        )
        self.keys = {}  # version -> EncryptionProvider
        self.metadata = {}  # version -> metadata dict
        self.current_version = 1

        # Create initial key version 1
        self._create_key_version(version=1)

    def _derive_version_key(self, version: int) -> bytes:
        """Derive the key for one version from the master key.

        HKDF is the right primitive here rather than PBKDF2: the master key is
        already high-entropy (either 32 raw bytes or a PBKDF2-stretched
        passphrase), so this step needs domain separation per version, not
        another round of stretching.
        """
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=AES_256_KEY_BYTES,
            salt=None,
            info=f"kaizen.security.encryption.key-version.{version}".encode("utf-8"),
        )
        return hkdf.derive(self._master_key)

    def _create_key_version(self, version: int):
        """Create a new key version."""
        provider = EncryptionProvider(key=self._derive_version_key(version))
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
    """Field-level encryption for selective data protection.

    ``FieldEncryptor(sensitive_fields=["ssn"])`` reads as fully configured, and
    its ``key=None`` default used to forward straight into a silently generated
    key — so PII was encrypted under material that died with the process. That
    wrapper propagation is what kept #2092 hidden from a sweep scoped to the
    generator call itself; a key is now required here too.
    """

    def __init__(
        self,
        sensitive_fields: list = None,
        key: Union[bytes, str, None] = None,
        *,
        allow_ephemeral_key: bool = False,
    ):
        """
        Initialize field encryptor.

        Args:
            sensitive_fields: List of field paths to encrypt (supports dot notation)
            key: 32-byte encryption key, or a passphrase of at least
                :data:`MIN_PASSPHRASE_LENGTH` characters. When omitted,
                ``KAIZEN_ENCRYPTION_KEY`` is read. An empty or whitespace-only
                string counts as NOT configured. If neither is configured this
                RAISES rather than generating a key.
            allow_ephemeral_key: Opt in to a generated process-local key for
                local development. Encrypted fields cannot be read back after
                this process exits.

        Raises:
            EncryptionKeyNotConfiguredError: If no key is configured and
                ``allow_ephemeral_key`` is False.
        """
        self.sensitive_fields = sensitive_fields or []
        self.provider = EncryptionProvider(
            key=key, allow_ephemeral_key=allow_ephemeral_key
        )

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
