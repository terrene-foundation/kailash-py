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
import tempfile
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..trust._locking import safe_read_json, validate_id
from ..utils.file_permissions import restrict_dir_to_owner, restrict_to_owner

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


class SecretRollbackError(SecretEncryptionError):
    """Raised when a secret file is older than the version last stored.

    The rotation-undone case: a credential is rotated because it leaked, a
    file-level backup is restored weeks later for unrelated reasons, and the
    store is silently back on the compromised value. The restored envelope is
    cryptographically perfect — correct key, correct reference — so nothing
    but a version comparison against state held OUTSIDE the envelope can catch
    it. See :class:`FileSecretBackend` for exactly which restore scenarios are
    detected and which are not.
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

#: Filename of the high-water-mark manifest. Leading dot, so it can never
#: collide with a secret: ``validate_id`` restricts references to
#: ``[A-Za-z0-9_-]+``, which cannot produce this name.
_VERSION_MANIFEST_NAME = ".secret-versions.json"

#: Internal ``ref`` the manifest's own envelope is bound to. Same reason.
_VERSION_MANIFEST_REF = ".secret-versions"


@lru_cache(maxsize=64)
def _warn_manifest_inside_store(secrets_dir: str) -> None:
    """Warn that rollback detection is running in its weaker form.

    Once per directory rather than once per read: this fires from the
    constructor, and a service that builds a backend per request would
    otherwise flood the operator's log with a message about a static
    configuration fact. Tests reset it with ``cache_clear()``.

    Loud rather than silent because the default provides the WEAKER of two
    guarantees the docstring describes, and an operator who never reads the
    docstring would otherwise believe rollback is covered outright
    (``rules/security.md`` § Secure-Default For A New Security Feature).

    Not defaulted to some directory outside the store instead: no location
    this class could pick is KNOWN to sit outside the operator's backup
    boundary. A sibling directory looks separate but is captured by any backup
    taken one level up, so an automatic default would trade a loud, accurate
    warning for a silent and possibly false claim of protection. Only the
    operator knows where their backup boundary runs.
    """
    logger.warning(
        "Rollback detection is degraded: the secret version manifest lives "
        "inside %s, so it is part of the same backup set as the secrets. A "
        "restore of the WHOLE directory will revert the version marks along "
        "with the secrets and will NOT be detected as a rollback -- a rotated "
        "credential can be silently reverted to its pre-rotation value. "
        "Single-file restores ARE detected. To close the whole-directory "
        "case, set KAILASH_SECRETS_STATE_DIR (or pass state_dir=) to a "
        "directory with an independent backup lifecycle.",
        secrets_dir,
    )


class FileSecretBackend(SecretBackend):
    """Secret backend that encrypts each secret at rest in its own file.

    Every secret is stored as a JSON envelope::

        {"v": 1, "kdf": "pbkdf2-sha256", "iterations": 100000,
         "salt": "<base64>", "ciphertext": "<Fernet token>"}

    The salt is generated fresh for every ``store_secret`` call and persisted
    alongside the ciphertext, so the store survives a process restart and no
    two files share a derived key. The master key itself is never written.

    The plaintext under that ciphertext is ``{"ref": <reference>, "version":
    <int>, "stored_at": <unix seconds>, "secret": <value>}``. Two checks read
    it, and they close two different attacks.

    **Substitution** — ``get_secret`` refuses an envelope whose embedded
    ``ref`` is not the reference it was asked for. Fernet authenticates its
    ciphertext but has no associated-data channel, so without that binding an
    envelope verifies under ANY name: copying ``staging_key.json`` over
    ``db_master.json`` would return the attacker's chosen value with every
    integrity check passing.

    **Rollback** — the ``ref`` binding does NOT close this, because a restored
    backup carries the CORRECT ref. Each store increments ``version``, and the
    high-water mark is kept in a separate authenticated manifest
    (``.secret-versions.json``); a read whose envelope version is BELOW the
    mark raises :class:`SecretRollbackError`.

    **Read this before relying on rollback detection.** With the DEFAULT
    configuration the manifest lives inside ``secrets_dir``, so restoring the
    whole directory reverts the marks along with the secrets and the rollback
    is NOT detected. The default therefore protects against restoring
    individual secret FILES, not against restoring the STORE. Constructing the
    backend in that configuration logs a warning saying so. Set ``state_dir``
    to close it.

    What that guarantee is, precisely
    ---------------------------------

    ================================================  =========
    Scenario                                          Detected?
    ================================================  =========
    Restore one secret file over a rotated secret     YES
    Restore several secret files, manifest untouched  YES
    Tamper with the manifest to lower a mark          YES — it is an
                                                      authenticated envelope
                                                      and cannot be forged
                                                      without the master key
    Restore the WHOLE directory, manifest included    **NO** by default —
                                                      ``state_dir`` outside the
                                                      store closes it
    DELETE the manifest, then restore an old file     **NO.** The marks are the
                                                      only record; once gone, a
                                                      restored old envelope is
                                                      indistinguishable from a
                                                      never-rotated one
    ================================================  =========

    The default keeps the manifest inside ``secrets_dir``, so a whole-directory
    restore reverts the marks along with the secrets and the rollback is
    invisible. Pass ``state_dir`` (or set ``KAILASH_SECRETS_STATE_DIR``) to a
    location with an independent backup lifecycle to close that case; there is
    no way to close it from inside the store alone. Whichever location is used
    needs its own durability: **deleting the manifest silently disables
    rollback detection**, and nothing inside the store can distinguish that
    from a first run.

    ``max_age`` is the complementary check for deployments that cannot provide
    external state, and it is the only one of these that survives losing the
    manifest: it bounds how old a stored envelope may be at read time, turning
    a restored months-old backup into a loud error with no external
    coordination at all. It does NOT detect the restore of a RECENT envelope.

    Concurrency: the manifest is read-modify-written without a cross-process
    lock, so simultaneous stores from separate processes may lose a mark bump.
    The mark is additionally floored at the version already on disk for that
    reference, which bounds the loss to one increment rather than a reset.

    Args:
        secrets_dir: Directory holding one file per secret. Created ``0o700``.
        master_key: The passphrase to derive from, at least
            ``MIN_MASTER_KEY_LENGTH`` characters. Prefer the environment
            variable; pass this only when the key comes from another vault.
        master_key_source: Name of the environment variable read when
            ``master_key`` is not given. Defaults to
            ``KAILASH_SECRETS_MASTER_KEY``.
        state_dir: Where the version manifest lives. Defaults to
            ``KAILASH_SECRETS_STATE_DIR`` if set, otherwise ``secrets_dir`` —
            see the table above for what that default does and does not catch.
        max_age: Optional maximum age, in seconds, of a stored envelope at read
            time. Unset means no staleness check is performed and none is
            claimed.

    Raises:
        SecretEncryptionError: If no master key is available, or if it is
            shorter than ``MIN_MASTER_KEY_LENGTH``. This is deliberate and
            fails CLOSED at construction — a backend that quietly generated its
            own key would either write secrets nobody can recover after a
            restart, or write them under a key with no secrecy at all, and
            100k PBKDF2 iterations do not rescue a one-character passphrase.

    Note:
        Files written by kailash <= 2.58 are cleartext and are NOT readable
        here; reading one raises :class:`LegacyPlaintextSecretError`. Treat
        those secrets as disclosed, rotate them, and store them again.
    """

    #: Minimum master-key length, matching ``trust.auth.jwt.JWTConfig``.
    MIN_MASTER_KEY_LENGTH = 32

    def __init__(
        self,
        secrets_dir: str = "/etc/kailash/secrets",
        *,
        master_key: Optional[str] = None,
        master_key_source: str = "KAILASH_SECRETS_MASTER_KEY",
        state_dir: Optional[str] = None,
        max_age: Optional[float] = None,
    ):
        self.secrets_dir = secrets_dir
        self.master_key_source = master_key_source
        self.max_age = max_age

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
        if len(key) < self.MIN_MASTER_KEY_LENGTH:
            # The length is named, the key is not: an exception message can
            # reach a log or a crash report.
            raise SecretEncryptionError(
                f"Master key from {master_key_source} is {len(key)} characters; "
                f"at least {self.MIN_MASTER_KEY_LENGTH} are required. A "
                f"passphrase that brief is brute-forceable regardless of the "
                f"KDF's iteration count."
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

        self.state_dir = (
            state_dir or os.environ.get("KAILASH_SECRETS_STATE_DIR") or secrets_dir
        )
        if self.state_dir != secrets_dir:
            os.makedirs(self.state_dir, mode=0o700, exist_ok=True)
            restrict_dir_to_owner(self.state_dir)
        else:
            # LOUD, not informational: the default runs the weaker of the two
            # guarantees the docstring describes, and an operator who never
            # reads the docstring would otherwise believe rollback is covered
            # outright.
            _warn_manifest_inside_store(secrets_dir)
        self._manifest_path = os.path.join(self.state_dir, _VERSION_MANIFEST_NAME)

    def _path_for(self, reference: str) -> str:
        """Resolve a reference to its file, rejecting traversal.

        ``reference`` reaches ``os.path.join`` unmodified, so without this an
        argument of ``../../etc/kailash/authorized_keys`` would read, write, or
        delete outside the store.
        """
        validate_id(reference)
        return os.path.join(self.secrets_dir, f"{reference}.json")

    def _read_version_marks(self) -> Dict[str, int]:
        """Return the per-reference high-water marks, or ``{}`` if unset.

        The manifest is itself an authenticated envelope bound to a reserved
        ref, so it can be deleted or restored but not forged: an attacker who
        can write in the directory cannot lower a mark without the master key.
        A manifest that is present but unreadable is a hard error rather than
        an empty dict — treating it as empty would make deleting the mark
        equivalent to having none, which is the whole check undone.
        """
        try:
            envelope = safe_read_json(Path(self._manifest_path))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            raise SecretEncryptionError(
                f"Secret version manifest at {self._manifest_path} is not "
                f"readable JSON. Rollback protection cannot be evaluated; "
                f"refusing to read secrets rather than skipping the check."
            ) from e

        marks = self._open_envelope(_VERSION_MANIFEST_REF, envelope)["secret"]
        if not isinstance(marks, dict):
            raise SecretEncryptionError(
                f"Secret version manifest at {self._manifest_path} has an "
                f"unexpected shape."
            )
        return {k: v for k, v in marks.items() if isinstance(v, int)}

    def _record_version_mark(self, reference: str, version: int) -> None:
        """Raise the high-water mark for ``reference`` to ``version``."""
        marks = self._read_version_marks()
        if marks.get(reference, 0) >= version:
            return
        marks[reference] = version
        self._write_envelope(
            self._manifest_path, self._seal(_VERSION_MANIFEST_REF, marks, version=0)
        )

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
                unsupported format, does not decrypt under this master key, or
                is bound to a different reference.
            SecretRollbackError: The envelope is older than the version last
                stored under this reference, or older than ``max_age``.
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

        payload = self._open_envelope(reference, envelope)
        self._reject_if_rolled_back(reference, payload)
        return payload["secret"]

    def _reject_if_rolled_back(self, reference: str, payload: Dict[str, Any]) -> None:
        """Refuse an envelope that is behind the high-water mark, or stale.

        This is the check the ``ref`` binding cannot do. A restored backup is
        cryptographically perfect — right key, right reference — so the only
        evidence that it is the WRONG generation lives outside the envelope.
        """
        version = payload.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise SecretEncryptionError(
                f"Secret {reference} carries no usable version. It was written "
                f"by a build without rollback protection; rotate the secret and "
                f"store it again."
            )

        mark = self._read_version_marks().get(reference, 0)
        if version < mark:
            raise SecretRollbackError(
                f"Secret {reference} is version {version} but version {mark} "
                f"was stored. This file is an earlier generation — most likely "
                f"a restored backup that has undone a rotation. If the "
                f"rollback is intended, store the current value again rather "
                f"than restoring the old file."
            )

        if self.max_age is None:
            return
        stored_at = payload.get("stored_at")
        if not isinstance(stored_at, (int, float)) or isinstance(stored_at, bool):
            raise SecretEncryptionError(
                f"Secret {reference} carries no usable store timestamp, so the "
                f"configured max_age cannot be enforced."
            )
        age = time.time() - stored_at
        if age > self.max_age:
            raise SecretRollbackError(
                f"Secret {reference} was stored {int(age)}s ago, beyond the "
                f"configured max_age of {int(self.max_age)}s. Rotate it, or "
                f"raise max_age if this lifetime is expected."
            )

    def _open_envelope(self, reference: str, envelope: Any) -> Dict[str, Any]:
        """Validate and decrypt an envelope, returning its whole payload.

        The payload, not just the secret: the version and timestamp under the
        ciphertext are what the rollback check reads. No plaintext fallback,
        ever.
        """
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

        payload = json.loads(plaintext.decode())
        if not isinstance(payload, dict) or "ref" not in payload:
            raise SecretEncryptionError(
                f"Secret {reference} decrypted to an unbound payload. It was "
                f"written by a build that did not bind the ciphertext to its "
                f"reference; rotate the secret and store it again."
            )
        if "secret" not in payload:
            raise SecretEncryptionError(
                f"Secret {reference} decrypted to a payload with no value."
            )
        # The binding check. Fernet proves the bytes were written by a holder
        # of this master key -- NOT that they were written for THIS reference.
        # Without this, copying one envelope over another substitutes the
        # secret while every integrity check still passes. It does NOT close
        # rollback: a restored backup carries the CORRECT ref, which is what
        # _reject_if_rolled_back exists for.
        if payload["ref"] != reference:
            raise SecretEncryptionError(
                f"Secret {reference} holds an envelope written for a different "
                f"reference. The file has been substituted or restored over."
            )

        return payload

    def _seal(self, reference: str, secret: Any, version: int) -> Dict[str, Any]:
        """Build an encrypted envelope binding ``secret`` to ref and version.

        The reference and the version travel INSIDE the ciphertext: Fernet has
        no associated-data channel, so anything left outside it is editable by
        whoever can write the file. ``json.dumps`` rather than ``str()`` — it
        round-trips dicts and strings back to their original type, so
        ``get_secret`` returns what was handed in.
        """
        salt = os.urandom(_SALT_BYTES)
        payload = {
            "ref": reference,
            "version": version,
            "stored_at": time.time(),
            "secret": secret,
        }
        token = self._cipher_for(salt, SECRET_KDF_ITERATIONS).encrypt(
            json.dumps(payload).encode()
        )
        return {
            "v": SECRET_ENVELOPE_VERSION,
            "kdf": SECRET_ENVELOPE_KDF,
            "iterations": SECRET_KDF_ITERATIONS,
            "salt": base64.b64encode(salt).decode(),
            "ciphertext": token.decode(),
        }

    def _next_version(self, reference: str) -> int:
        """One past the highest version seen for ``reference``.

        Both the manifest mark and the version already on disk are consulted,
        so a lost mark (deleted manifest, unlocked concurrent store) costs at
        most one increment rather than resetting the counter to 1 and making
        every later rollback undetectable.
        """
        highest = self._read_version_marks().get(reference, 0)
        try:
            envelope = safe_read_json(Path(self._path_for(reference)))
            current = self._open_envelope(reference, envelope).get("version")
            if isinstance(current, int) and not isinstance(current, bool):
                highest = max(highest, current)
        except (OSError, SecretEncryptionError, json.JSONDecodeError):
            # No readable predecessor — a first store, a legacy file, or one
            # that fails the checks above. Either way the manifest mark alone
            # decides, and a store must not be blocked by an unreadable file it
            # is about to replace.
            pass
        return highest + 1

    async def store_secret(self, reference: str, secret: Any) -> None:
        """Encrypt ``secret`` and write it owner-only under ``reference``."""
        file_path = self._path_for(reference)
        version = self._next_version(reference)
        self._write_envelope(file_path, self._seal(reference, secret, version))
        # Mark AFTER the secret lands. The other order fails closed in the
        # wrong direction: a mark raised past a write that then failed would
        # reject the still-valid previous secret on every subsequent read.
        self._record_version_mark(reference, version)

    def _write_envelope(self, file_path: str, envelope: Dict[str, Any]) -> None:
        """Write the envelope atomically, owner-only, and durably.

        Temp-file-plus-rename rather than an in-place ``O_TRUNC`` write: a
        crash or a full disk partway through an in-place write leaves a
        truncated file, which the read path would then report as
        ``LegacyPlaintextSecretError`` — data loss surfaced to the operator as
        "this is pre-2.58 cleartext". ``os.replace`` is atomic on POSIX and on
        Windows, so a reader sees either the whole old file or the whole new
        one. It also replaces a symlink sitting at the target rather than
        writing through it.

        Not ``trust._locking.atomic_write``, which is otherwise the same shape:
        it has no place to apply ``restrict_to_owner`` to the descriptor, and
        this call site must both apply it and act on its answer.
        """
        directory = os.path.dirname(file_path) or "."
        # mkstemp creates 0o600 on POSIX, so the payload is never world-readable
        # even for the duration of the write; restrict_to_owner then covers
        # Windows, where the mode is not the mechanism.
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=f".{os.path.basename(file_path)}.", suffix=".tmp"
        )
        try:
            if not restrict_to_owner(tmp_path, fd=fd):
                # The helper's contract: False means no mechanism was available
                # and the file is NOT confidential. It warns once per process,
                # which an unrelated earlier write may already have consumed, so
                # secret material logs its own per-file finding.
                logger.warning(
                    "Secret file %s is NOT confidential: owner-only access "
                    "could not be enforced on this platform. Install pywin32, "
                    "or place the secrets directory on a volume whose ACL "
                    "already restricts access.",
                    file_path,
                )
            with os.fdopen(fd, "w") as f:
                fd = -1  # os.fdopen took ownership — do not double-close
                json.dump(envelope, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError as cleanup_error:
                # Not silent: a temp file left in the secrets directory holds
                # a real (encrypted) secret and will not be cleaned up by
                # anything else. The original failure still propagates.
                logger.warning(
                    "Could not remove partial secret file %s after a failed "
                    "write: %s. Remove it manually.",
                    tmp_path,
                    cleanup_error,
                )
            raise

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
