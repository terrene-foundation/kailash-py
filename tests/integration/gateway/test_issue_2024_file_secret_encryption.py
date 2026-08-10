# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Issue #2024 — FileSecretBackend documented encryption and wrote cleartext.

Every assertion is BEHAVIOURAL: each test drives the real store/read path and
then inspects what actually landed on disk (raw bytes read back outside the
class) or what the class raised. No test asserts on source text, which would
pass against a comment.

The byte-absence tests deliberately cannot be satisfied by writing garbage:
the round-trip test in the same file requires the same envelope to decrypt
back to the original value, so an implementation that scrambles the secret
irrecoverably fails here even while the leak assertions pass.

Every test in this file fails against the pre-fix implementation. The named
falsifying results are recorded per class.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from kailash.gateway.security import (
    FileSecretBackend,
    LegacyPlaintextSecretError,
    SecretEncryptionError,
    SecretNotFoundError,
)

pytestmark = pytest.mark.integration

MASTER_KEY = "correct-horse-battery-staple-master"
# High-entropy so a chance appearance in an envelope is not credible.
SENTINEL = "s3nt1nel-6f4b0c9e21ad4d8ba7c35e10f2d9b874-DO-NOT-LEAK"

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX mode bits do not restrict readers on Windows"
)


@pytest.fixture
def backend(tmp_path, monkeypatch) -> FileSecretBackend:
    monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
    return FileSecretBackend(str(tmp_path))


def _raw(tmp_path, reference: str) -> bytes:
    """Read the stored file outside the class, as an attacker with FS access."""
    return (tmp_path / f"{reference}.json").read_bytes()


class TestSecretIsNotOnDiskInClear:
    """Falsifying result: the sentinel appears in the bytes on disk.

    Against the pre-fix code ``store_secret`` wrote ``f.write(secret)`` /
    ``json.dump(secret, f)``, so the sentinel is present verbatim and every
    assertion below fails.
    """

    def test_a_string_secret_is_not_recoverable_from_the_file(
        self, backend, tmp_path
    ) -> None:
        asyncio.run(backend.store_secret("api-token", SENTINEL))
        raw = _raw(tmp_path, "api-token")

        assert SENTINEL.encode() not in raw, "secret stored in cleartext"
        # A base64 or JSON-escaped rendering is just as recoverable as the
        # literal, so absence of the literal alone would be a weak assertion.
        assert base64.b64encode(SENTINEL.encode()) not in raw
        assert json.dumps(SENTINEL).encode().strip(b'"') not in raw

    def test_a_dict_secret_is_not_recoverable_from_the_file(
        self, backend, tmp_path
    ) -> None:
        asyncio.run(backend.store_secret("db-creds", {"password": SENTINEL}))
        raw = _raw(tmp_path, "db-creds")

        assert SENTINEL.encode() not in raw, "secret stored in cleartext"
        assert base64.b64encode(SENTINEL.encode()) not in raw
        # The key name is structure, not the secret, but it leaked too.
        assert b"password" not in raw

    def test_the_envelope_is_well_formed(self, backend, tmp_path) -> None:
        """The bytes that replaced the cleartext are the documented envelope,
        not an accident of some other serialisation."""
        asyncio.run(backend.store_secret("api-token", SENTINEL))
        envelope = json.loads(_raw(tmp_path, "api-token"))

        assert envelope["v"] == 1
        assert envelope["kdf"] == "pbkdf2-sha256"
        assert envelope["iterations"] >= 100_000
        assert len(base64.b64decode(envelope["salt"])) >= 16
        assert isinstance(envelope["ciphertext"], str)


class TestRoundTrip:
    """Falsifying result: the value read back differs from the value stored.

    Pins the fix against the trivial way to pass the leak tests — writing
    something unrecoverable.
    """

    def test_string_round_trips_with_its_type(self, backend) -> None:
        asyncio.run(backend.store_secret("api-token", SENTINEL))
        assert asyncio.run(backend.get_secret("api-token")) == SENTINEL

    def test_dict_round_trips_with_its_type(self, backend) -> None:
        value = {"password": SENTINEL, "port": 5432, "tls": True}
        asyncio.run(backend.store_secret("db-creds", value))
        assert asyncio.run(backend.get_secret("db-creds")) == value

    def test_overwrite_returns_the_new_value(self, backend) -> None:
        asyncio.run(backend.store_secret("api-token", "old"))
        asyncio.run(backend.store_secret("api-token", SENTINEL))
        assert asyncio.run(backend.get_secret("api-token")) == SENTINEL

    def test_a_fresh_instance_can_read_an_earlier_store(
        self, tmp_path, monkeypatch
    ) -> None:
        """The salt lives in the envelope, so the store survives a restart.

        Falsifying result: a per-instance salt held only in memory makes this
        raise SecretEncryptionError — the failure mode #2041 records in
        SecretManager, which is why its cipher was not reused.
        """
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        asyncio.run(FileSecretBackend(str(tmp_path)).store_secret("k", SENTINEL))
        reopened = FileSecretBackend(str(tmp_path))
        assert asyncio.run(reopened.get_secret("k")) == SENTINEL

    def test_deleted_secret_is_reported_missing(self, backend) -> None:
        asyncio.run(backend.store_secret("api-token", SENTINEL))
        asyncio.run(backend.delete_secret("api-token"))
        with pytest.raises(SecretNotFoundError):
            asyncio.run(backend.get_secret("api-token"))


class TestPerSecretSalt:
    """Falsifying result: two files share a salt, hence a derived key."""

    def test_two_secrets_get_distinct_salts(self, backend, tmp_path) -> None:
        asyncio.run(backend.store_secret("one", SENTINEL))
        asyncio.run(backend.store_secret("two", SENTINEL))

        salts = {json.loads(_raw(tmp_path, r))["salt"] for r in ("one", "two")}
        assert len(salts) == 2, "both secrets derived their key from one salt"

    def test_rewriting_a_secret_reuses_neither_salt_nor_ciphertext(
        self, backend, tmp_path
    ) -> None:
        asyncio.run(backend.store_secret("one", SENTINEL))
        first = json.loads(_raw(tmp_path, "one"))
        asyncio.run(backend.store_secret("one", SENTINEL))
        second = json.loads(_raw(tmp_path, "one"))

        assert first["salt"] != second["salt"]
        assert first["ciphertext"] != second["ciphertext"]


class TestFailsClosedWithoutAMasterKey:
    """Falsifying result: construction succeeds and secrets are written anyway.

    Against the pre-fix code there was no key at all, so the constructor
    accepted every environment — which is the defect.
    """

    def test_construction_raises_when_the_env_var_is_unset(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.delenv("KAILASH_SECRETS_MASTER_KEY", raising=False)
        with pytest.raises(SecretEncryptionError) as excinfo:
            FileSecretBackend(str(tmp_path))
        assert "KAILASH_SECRETS_MASTER_KEY" in str(
            excinfo.value
        ), "the operator is not told which variable to set"

    def test_construction_raises_on_an_empty_master_key(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", "")
        with pytest.raises(SecretEncryptionError):
            FileSecretBackend(str(tmp_path))

    def test_an_explicit_master_key_is_accepted(self, tmp_path, monkeypatch) -> None:
        """The env var is the default source, not the only one."""
        monkeypatch.delenv("KAILASH_SECRETS_MASTER_KEY", raising=False)
        backend = FileSecretBackend(str(tmp_path), master_key=MASTER_KEY)
        asyncio.run(backend.store_secret("k", SENTINEL))
        assert asyncio.run(backend.get_secret("k")) == SENTINEL

    def test_the_wrong_master_key_raises_rather_than_returning_data(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        asyncio.run(FileSecretBackend(str(tmp_path)).store_secret("k", SENTINEL))

        monkeypatch.setenv(
            "KAILASH_SECRETS_MASTER_KEY", "a-completely-different-master-key-entirely"
        )
        with pytest.raises(SecretEncryptionError):
            asyncio.run(FileSecretBackend(str(tmp_path)).get_secret("k"))


class TestEnvelopesAreBoundToTheirReference:
    """Falsifying result: the substituted envelope decrypts and its value is
    returned under the requested reference.

    Fernet authenticates its ciphertext but carries no associated data, so an
    envelope with no reference inside it is a free-standing blob: it verifies
    under ANY name. That makes file-copy substitution and backup-restore
    rollback indistinguishable from a legitimate read.
    """

    def test_copying_one_envelope_over_another_is_refused(
        self, backend, tmp_path
    ) -> None:
        asyncio.run(backend.store_secret("db_master", "SECRET-PROD-VALUE"))
        asyncio.run(backend.store_secret("staging_key", "SECRET-STAGING-VALUE"))

        shutil.copyfile(tmp_path / "staging_key.json", tmp_path / "db_master.json")

        with pytest.raises(SecretEncryptionError, match="different reference"):
            asyncio.run(backend.get_secret("db_master"))

    def test_a_restored_pre_rotation_backup_is_refused_under_another_name(
        self, backend, tmp_path
    ) -> None:
        """The no-attacker case: a restore process puts the wrong file back."""
        asyncio.run(backend.store_secret("api_token", "SECRET-CURRENT"))
        backup = tmp_path / "backup.json"
        shutil.copyfile(tmp_path / "api_token.json", backup)

        asyncio.run(backend.store_secret("api_token_old", "SECRET-CURRENT"))
        shutil.copyfile(backup, tmp_path / "api_token_old.json")

        with pytest.raises(SecretEncryptionError, match="different reference"):
            asyncio.run(backend.get_secret("api_token_old"))

    def test_renaming_a_secret_file_does_not_rename_the_secret(
        self, backend, tmp_path
    ) -> None:
        asyncio.run(backend.store_secret("original", SENTINEL))
        (tmp_path / "original.json").rename(tmp_path / "renamed.json")

        with pytest.raises(SecretEncryptionError):
            asyncio.run(backend.get_secret("renamed"))

    def test_the_reference_is_not_recoverable_from_the_envelope(
        self, backend, tmp_path
    ) -> None:
        """The binding lives under the ciphertext, so it is not itself a
        disclosure: the filename already names the reference, but the bound
        copy must not be a second cleartext channel that could be edited."""
        asyncio.run(backend.store_secret("db_master", SENTINEL))
        envelope = json.loads(_raw(tmp_path, "db_master"))
        assert "ref" not in envelope
        assert b"db_master" not in base64.b64decode(envelope["salt"])

    def test_the_legitimate_read_still_works(self, backend) -> None:
        """The binding must not reject the ordinary case — otherwise the tests
        above would pass against a get_secret that raises unconditionally."""
        asyncio.run(backend.store_secret("db_master", "SECRET-PROD-VALUE"))
        assert asyncio.run(backend.get_secret("db_master")) == "SECRET-PROD-VALUE"


class TestMasterKeyStrengthFloor:
    """Falsifying result: a one-character passphrase is accepted.

    ``if not key`` rejected only the empty string, so 100k PBKDF2 iterations
    were being applied to a passphrase with no entropy to stretch.
    """

    @pytest.mark.parametrize("weak", ["x", "short", "a" * 31])
    def test_a_short_master_key_is_refused(self, tmp_path, monkeypatch, weak) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", weak)
        with pytest.raises(SecretEncryptionError) as excinfo:
            FileSecretBackend(str(tmp_path))
        message = str(excinfo.value)
        assert str(len(weak)) in message, "received length is not named"
        assert "32" in message, "the floor is not named"
        assert weak not in message, "the rejected key was echoed into the error"

    def test_the_floor_is_the_repo_wide_one(self) -> None:
        from kailash.trust.auth.jwt import JWTConfig

        assert FileSecretBackend.MIN_MASTER_KEY_LENGTH == JWTConfig.MIN_SECRET_LENGTH

    def test_a_key_exactly_at_the_floor_is_accepted(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", "a" * 32)
        backend = FileSecretBackend(str(tmp_path))
        asyncio.run(backend.store_secret("k", SENTINEL))
        assert asyncio.run(backend.get_secret("k")) == SENTINEL


class TestTheWriteIsAtomic:
    """Falsifying result: a failed write leaves the previous secret truncated.

    An in-place O_TRUNC write that dies partway through produces a file the
    read path reports as LegacyPlaintextSecretError — data loss presented to
    the operator as "this is pre-2.58 cleartext".
    """

    def test_a_failed_write_leaves_the_previous_secret_intact(
        self, backend, tmp_path, monkeypatch
    ) -> None:
        asyncio.run(backend.store_secret("k", SENTINEL))

        from kailash.gateway import security as security_module

        def exploding_dump(obj, fp, *args, **kwargs):
            fp.write('{"v": 1, "kdf": "pbkd')  # a genuine partial write
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(security_module.json, "dump", exploding_dump)
        with pytest.raises(OSError):
            asyncio.run(backend.store_secret("k", "REPLACEMENT"))
        monkeypatch.undo()

        assert asyncio.run(backend.get_secret("k")) == SENTINEL

    def test_a_failed_write_leaves_no_temp_file_behind(
        self, backend, tmp_path, monkeypatch
    ) -> None:
        from kailash.gateway import security as security_module

        def exploding_dump(obj, fp, *args, **kwargs):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(security_module.json, "dump", exploding_dump)
        with pytest.raises(OSError):
            asyncio.run(backend.store_secret("k", SENTINEL))
        monkeypatch.undo()

        assert list(tmp_path.iterdir()) == [], f"left behind {list(tmp_path.iterdir())}"

    @posix_only
    def test_the_payload_is_never_world_readable_even_mid_write(
        self, backend, monkeypatch
    ) -> None:
        """Sampled through the descriptor being written, not the final path:
        the defect this pins is the window, and the final mode was already
        correct before the fix."""
        from kailash.gateway import security as security_module

        observed: list[int] = []
        real_dump = security_module.json.dump

        def spying_dump(obj, fp, *args, **kwargs):
            observed.append(stat.S_IMODE(os.fstat(fp.fileno()).st_mode))
            return real_dump(obj, fp, *args, **kwargs)

        monkeypatch.setattr(security_module.json, "dump", spying_dump)
        asyncio.run(backend.store_secret("k", SENTINEL))

        assert observed, "the write path never ran; test would be vacuous"
        assert observed[0] == 0o600, f"world-readable mid-write ({observed[0]:o})"


class TestLegacyPlaintextRaisesAndIsNeverHonoured:
    """Falsifying result: a cleartext file is read and its contents returned.

    That fallback is a downgrade oracle: anyone who can write into the store
    replaces an envelope with a file of their choosing and it is honoured.
    """

    def test_a_legacy_json_file_raises(self, backend, tmp_path) -> None:
        (tmp_path / "legacy.json").write_text(json.dumps({"password": SENTINEL}))
        with pytest.raises(LegacyPlaintextSecretError):
            asyncio.run(backend.get_secret("legacy"))

    def test_a_legacy_bare_string_file_raises(self, backend, tmp_path) -> None:
        """The old code wrote str secrets with f.write(), so most legacy files
        are not even JSON."""
        (tmp_path / "legacy.json").write_text(SENTINEL)
        with pytest.raises(LegacyPlaintextSecretError):
            asyncio.run(backend.get_secret("legacy"))

    def test_the_migration_error_is_not_a_not_found_error(self, backend) -> None:
        """A caller catching SecretNotFoundError to fall back to a default must
        not swallow 'present but unreadable'."""
        assert not issubclass(LegacyPlaintextSecretError, SecretNotFoundError)
        assert issubclass(LegacyPlaintextSecretError, SecretEncryptionError)


class TestEnvelopeDowngradesAreRejected:
    """Falsifying result: a hostile envelope is accepted on its own terms.

    The KDF parameters come back from the file, so a writer who cannot forge a
    Fernet token can still weaken the derivation used to check their guesses.
    """

    def _write(self, tmp_path, backend, **overrides) -> None:
        asyncio.run(backend.store_secret("k", SENTINEL))
        envelope = json.loads(_raw(tmp_path, "k"))
        envelope.update(overrides)
        (tmp_path / "k.json").write_text(json.dumps(envelope))

    def test_a_lowered_iteration_count_is_refused(self, backend, tmp_path) -> None:
        self._write(tmp_path, backend, iterations=1)
        with pytest.raises(SecretEncryptionError, match="iteration"):
            asyncio.run(backend.get_secret("k"))

    def test_an_absurd_iteration_count_is_refused(self, backend, tmp_path) -> None:
        self._write(tmp_path, backend, iterations=10**12)
        with pytest.raises(SecretEncryptionError, match="iteration"):
            asyncio.run(backend.get_secret("k"))

    def test_an_unknown_kdf_is_refused(self, backend, tmp_path) -> None:
        self._write(tmp_path, backend, kdf="rot13")
        with pytest.raises(SecretEncryptionError, match="KDF"):
            asyncio.run(backend.get_secret("k"))

    def test_an_unknown_envelope_version_is_refused(self, backend, tmp_path) -> None:
        self._write(tmp_path, backend, v=99)
        with pytest.raises(SecretEncryptionError, match="version"):
            asyncio.run(backend.get_secret("k"))

    def test_a_short_salt_is_refused(self, backend, tmp_path) -> None:
        self._write(tmp_path, backend, salt=base64.b64encode(b"tiny").decode())
        with pytest.raises(SecretEncryptionError, match="salt"):
            asyncio.run(backend.get_secret("k"))

    def test_a_tampered_ciphertext_is_refused(self, backend, tmp_path) -> None:
        asyncio.run(backend.store_secret("k", SENTINEL))
        envelope = json.loads(_raw(tmp_path, "k"))
        envelope["ciphertext"] = envelope["ciphertext"][:-4] + "AAAA"
        (tmp_path / "k.json").write_text(json.dumps(envelope))
        with pytest.raises(SecretEncryptionError):
            asyncio.run(backend.get_secret("k"))


class TestReferencesCannotEscapeTheStore:
    """Falsifying result: the traversing reference resolves outside the store.

    Against the pre-fix code the reference reached os.path.join unvalidated on
    all three methods, so ``../../..`` wrote and DELETED outside the directory.
    """

    TRAVERSALS = [
        "../../etc/kailash/authorized_keys",
        "../escape",
        "sub/dir",
        "..",
        "a\x00b",
        "/etc/kailash/absolute",
    ]

    @pytest.mark.parametrize("reference", TRAVERSALS)
    def test_get_rejects(self, backend, reference) -> None:
        with pytest.raises(ValueError):
            asyncio.run(backend.get_secret(reference))

    @pytest.mark.parametrize("reference", TRAVERSALS)
    def test_store_rejects(self, backend, reference) -> None:
        with pytest.raises(ValueError):
            asyncio.run(backend.store_secret(reference, SENTINEL))

    @pytest.mark.parametrize("reference", TRAVERSALS)
    def test_delete_rejects(self, backend, reference) -> None:
        with pytest.raises(ValueError):
            asyncio.run(backend.delete_secret(reference))

    def test_nothing_was_written_outside_the_store(self, backend, tmp_path) -> None:
        """The rejection is not merely an exception raised after the fact."""
        outside = tmp_path.parent / "escape.json"
        with pytest.raises(ValueError):
            asyncio.run(backend.store_secret("../escape", SENTINEL))
        assert not outside.exists(), "traversing write landed outside the store"

    def test_a_file_outside_the_store_survives_a_traversing_delete(
        self, backend, tmp_path
    ) -> None:
        victim = tmp_path.parent / "victim.json"
        victim.write_text("important")
        with pytest.raises(ValueError):
            asyncio.run(backend.delete_secret("../victim"))
        assert victim.exists(), "traversing delete removed a file outside the store"


@posix_only
class TestTheStoreItselfIsPrivate:
    """Falsifying result: the directory is group/world readable or traversable.

    ``os.makedirs(dir, exist_ok=True)`` created it under the umask (typically
    0o755), so the reference names alone disclosed which credentials exist.
    """

    def test_a_new_directory_is_owner_only(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        target = tmp_path / "secrets"
        FileSecretBackend(str(target))
        assert stat.S_IMODE(target.stat().st_mode) == 0o700

    def test_an_existing_world_readable_directory_is_tightened(
        self, tmp_path, monkeypatch
    ) -> None:
        """makedirs' mode argument is ignored for a directory that already
        exists, which is the common case for a long-lived store."""
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        target = tmp_path / "secrets"
        target.mkdir(mode=0o755)
        os.chmod(target, 0o755)
        assert stat.S_IMODE(target.stat().st_mode) == 0o755, "setup did not take"

        FileSecretBackend(str(target))
        assert stat.S_IMODE(target.stat().st_mode) == 0o700

    def test_the_secret_file_is_owner_only(self, backend, tmp_path) -> None:
        asyncio.run(backend.store_secret("k", SENTINEL))
        assert stat.S_IMODE((tmp_path / "k.json").stat().st_mode) == 0o600


@posix_only
class TestTheReadPathDoesNotFollowSymlinks:
    """Falsifying result: the symlink is followed and its target returned.

    The pre-fix read was ``os.path.exists()`` then ``open()`` — a window in
    which the path can be replaced by a link to anything the process can read.
    PR #2036 hardened only the write path.
    """

    def test_reading_through_a_symlink_is_refused(self, backend, tmp_path) -> None:
        outside = tmp_path.parent / "outside.json"
        outside.write_text(json.dumps({"stolen": "data"}))
        (tmp_path / "linked.json").symlink_to(outside)

        with pytest.raises(OSError) as excinfo:
            asyncio.run(backend.get_secret("linked"))
        assert "symlink" in str(excinfo.value).lower()

    def test_the_refusal_is_not_just_a_decode_failure(self, backend, tmp_path) -> None:
        """A symlink pointing at a VALID envelope is still refused, so the
        rejection is the link itself rather than the target's contents."""
        asyncio.run(backend.store_secret("real", SENTINEL))
        (tmp_path / "linked.json").symlink_to(tmp_path / "real.json")

        with pytest.raises(OSError):
            asyncio.run(backend.get_secret("linked"))


class TestSecretManagerStillRoundTripsThroughThisBackend:
    """The manager encrypts before handing the value down; the backend must
    not corrupt an already-``encrypted:``-prefixed string."""

    def test_manager_store_and_get(self, tmp_path, monkeypatch) -> None:
        from cryptography.fernet import Fernet

        from kailash.gateway.security import SecretManager

        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        manager = SecretManager(
            backend=FileSecretBackend(str(tmp_path)),
            encryption_key=Fernet.generate_key().decode(),
        )
        asyncio.run(manager.store_secret("db", {"password": SENTINEL}))

        assert SENTINEL.encode() not in _raw(tmp_path, "db")
        assert asyncio.run(manager.get_secret("db")) == {"password": SENTINEL}


def test_the_class_docstring_no_longer_promises_what_it_does_not_do() -> None:
    """Structural, and the weakest test here — kept only because the ISSUE is a
    documentation/behaviour mismatch, so the doc side deserves one pin. The
    behavioural tests above are what actually hold the encryption claim.
    """
    doc = FileSecretBackend.__doc__ or ""
    assert "envelope" in doc.lower()
    assert "master key" in doc.lower()
    # The migration consequence must be discoverable from the class itself.
    assert "cleartext" in doc.lower()


def test_the_code_under_test_comes_from_this_checkout() -> None:
    """Guards against ``pythonpath = src`` in pytest.ini resolving ``kailash``
    from a DIFFERENT checkout, which would make every test above vacuous.

    Falsifying result: the imported module's path is rooted elsewhere, which is
    exactly what a stale sibling checkout on sys.path produces.
    """
    import kailash.gateway.security as module

    repo_root = Path(__file__).resolve().parents[3]
    module_path = Path(module.__file__).resolve()
    assert module_path.is_relative_to(
        repo_root
    ), f"tests ran against {module_path}, not the checkout at {repo_root}"
