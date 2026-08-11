"""Issue #2041 — ``SecretManager`` must never encrypt under a key it throws away.

The defect: with no encryption key configured, ``SecretManager.__init__``
called ``Fernet.generate_key()``, logged a WARNING, and continued. Every secret
that manager encrypted became unreadable the moment the process restarted --
and ``SecretManager()`` is the DEFAULT construction in
``EnhancedDurableAPIGateway`` and ``EnterpriseWorkflowServer``, so this was the
shipped default path rather than an opt-in corner.

The tests that carry the fix are the behavioural ones below. Each states the
result that would falsify it, because a test that cannot go red proves nothing:

* :func:`test_store_refuses_when_no_encryption_key_is_configured` — falsified
  if the store SUCCEEDS with the environment unset (the pre-fix behaviour).
* :func:`test_no_secret_is_ever_written_under_a_key_that_dies_with_the_process`
  — the harm itself. Falsified if a manager accepts a write that a later
  manager over the same backend cannot read back. Pre-fix this raised
  ``InvalidToken`` on the second read; that IS the data loss.
* :func:`test_operator_passphrase_round_trips_across_a_restart` — falsified if
  a human-chosen passphrase cannot be used, which is what raw ``Fernet(key)``
  did to every passphrase that was not already a 32-byte urlsafe-base64 key.

:func:`test_configured_fernet_key_still_round_trips_across_a_restart` is the
NEGATIVE CONTROL: it passes before and after, and exists so that a fix which
merely broke encryption outright could not masquerade as a pass.
"""

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, Union

import pytest
from cryptography.fernet import Fernet

from kailash.gateway.security import (
    FileSecretBackend,
    SecretBackend,
    SecretEncryptionError,
    SecretManager,
)

#: Master key for the on-disk backend. Distinct from the manager's own key so a
#: test cannot pass by accidentally reusing one where the other was meant.
BACKEND_MASTER_KEY = "backend-master-key-that-is-long-enough-32"

#: What an operator would actually type. Deliberately NOT a valid Fernet key --
#: that is the whole point of issue #2041's second acceptance criterion.
OPERATOR_PASSPHRASE = "correct horse battery staple correct horse"

#: Must never appear in ciphertext, and must never appear in an error message.
SENTINEL = "s3ntinel-value-must-never-leak"

ENV_KEY = "KAILASH_ENCRYPTION_KEY"
ENV_STRICT = "KAILASH_REQUIRE_SECRET_ENCRYPTION"


class DictSecretBackend(SecretBackend):
    """A real backend, not a mock.

    ``Mock()`` satisfies every ``hasattr`` and every attribute access, so a
    guard that had been deleted outright would still look alive against one.
    This stores exactly what it is handed and returns exactly that.
    """

    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}

    async def get_secret(self, reference: str) -> Union[str, Dict[str, Any]]:
        if reference not in self.store:
            from kailash.gateway.security import SecretNotFoundError

            raise SecretNotFoundError(f"Secret {reference} not found")
        return self.store[reference]

    async def store_secret(self, reference: str, secret: Any) -> None:
        self.store[reference] = secret

    async def delete_secret(self, reference: str) -> None:
        self.store.pop(reference, None)


@pytest.fixture(autouse=True)
def _clean_encryption_env(monkeypatch):
    """No test may inherit a key from the developer's ``.env`` or shell.

    Without this the central test -- "unset means refuse" -- would silently
    become "set means succeed" on any machine that happens to export the
    variable, which is a vacuous pass rather than a failure.
    """
    monkeypatch.delenv(ENV_KEY, raising=False)
    monkeypatch.delenv(ENV_STRICT, raising=False)

    def _reset_once_per_process_warning() -> None:
        # Tolerant of the symbol's absence so that running this module against
        # the PRE-FIX source produces genuine behavioural failures rather than
        # fixture errors -- an errored run is zero evidence either way.
        from kailash.gateway import security as security_module

        warner = getattr(security_module, "_warn_secret_encryption_unconfigured", None)
        if warner is not None:
            warner.cache_clear()

    _reset_once_per_process_warning()
    yield
    _reset_once_per_process_warning()


def _disk_backend(tmp_path: Path) -> FileSecretBackend:
    """A genuinely durable backend, so "restart" means what it says."""
    return FileSecretBackend(str(tmp_path), master_key=BACKEND_MASTER_KEY)


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


def test_store_refuses_when_no_encryption_key_is_configured() -> None:
    """Encrypting with nothing configured must raise, not invent a key.

    Falsifying result: ``store_secret`` returns normally. That is precisely
    what the pre-fix code did, having generated a throwaway key in ``__init__``.
    """
    manager = SecretManager(backend=DictSecretBackend())

    with pytest.raises(SecretEncryptionError) as excinfo:
        asyncio.run(manager.store_secret("db", {"password": SENTINEL}))

    message = str(excinfo.value)
    # An error an operator cannot act on is barely better than the warning it
    # replaces, so the message must name the variable that fixes it.
    assert ENV_KEY in message


def test_no_secret_is_ever_written_under_a_key_that_dies_with_the_process(
    tmp_path,
) -> None:
    """The harm, stated directly: no write may become unreadable on restart.

    Two managers over one durable backend stand in for before and after a
    process restart. Exactly two outcomes are acceptable -- the write is
    REFUSED, or it is READABLE afterwards. The pre-fix code did neither: it
    accepted the write and then raised ``InvalidToken`` on the second read,
    because the key existed only inside the first instance.

    Falsifying result: the write is accepted and the second read does not
    return the stored value.
    """
    backend = _disk_backend(tmp_path)
    before_restart = SecretManager(backend=backend)

    try:
        asyncio.run(before_restart.store_secret("db", {"password": SENTINEL}))
    except SecretEncryptionError:
        return  # Refused up front. The defect cannot occur.

    after_restart = SecretManager(backend=_disk_backend(tmp_path))
    assert asyncio.run(after_restart.get_secret("db")) == {"password": SENTINEL}


def test_construction_without_a_key_emits_a_loud_one_time_error(caplog) -> None:
    """A library WARNING scrolls past; this must be ERROR and say what is off.

    Falsifying result: no ERROR-level record naming the variable. Pre-fix the
    only record was ``logger.warning("Using default encryption key - not
    secure for production!")``, which names neither the variable nor the
    consequence.
    """
    with caplog.at_level(logging.ERROR, logger="kailash.gateway.security"):
        SecretManager(backend=DictSecretBackend())

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "no ERROR-level record was emitted for an unconfigured manager"
    assert any(ENV_KEY in r.getMessage() for r in errors)


def test_the_loud_signal_is_emitted_once_not_once_per_instance(caplog) -> None:
    """Per-instance logging floods any service that builds a manager per request.

    Falsifying result: three constructions produce three records, which is how
    an operator learns to filter the message out entirely.
    """
    with caplog.at_level(logging.ERROR, logger="kailash.gateway.security"):
        for _ in range(3):
            SecretManager(backend=DictSecretBackend())

    matching = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and ENV_KEY in r.getMessage()
    ]
    assert len(matching) == 1, f"expected exactly one record, got {len(matching)}"


def test_strict_mode_refuses_to_construct_at_all() -> None:
    """Operators who want start-up failure must be able to demand it.

    Falsifying result: construction succeeds, or raises ``TypeError`` because
    the parameter does not exist (the pre-fix state).
    """
    with pytest.raises(SecretEncryptionError) as excinfo:
        SecretManager(backend=DictSecretBackend(), require_encryption=True)

    assert ENV_KEY in str(excinfo.value)


def test_strict_mode_can_be_demanded_by_environment(monkeypatch) -> None:
    """Deployment-wide enforcement must not require editing call sites.

    The two default constructions of this class live inside other classes'
    ``__init__`` bodies, so an operator has no code seam to pass a flag through.
    """
    monkeypatch.setenv(ENV_STRICT, "1")

    with pytest.raises(SecretEncryptionError):
        SecretManager(backend=DictSecretBackend())


# ---------------------------------------------------------------------------
# Key derivation (issue #2041 acceptance criterion 2)
# ---------------------------------------------------------------------------


def test_operator_passphrase_round_trips_across_a_restart(tmp_path) -> None:
    """A human-chosen passphrase must work, and must survive a restart.

    Falsifying result: construction raises, which is what ``Fernet(passphrase
    .encode())`` did for every passphrase that was not already a 32-byte
    urlsafe-base64 key -- making the documented ``encryption_key`` parameter
    unusable with anything an operator would naturally supply.
    """
    secret = {"password": SENTINEL, "port": 5432}

    writer = SecretManager(
        backend=_disk_backend(tmp_path), encryption_key=OPERATOR_PASSPHRASE
    )
    asyncio.run(writer.store_secret("db", secret))

    reader = SecretManager(
        backend=_disk_backend(tmp_path), encryption_key=OPERATOR_PASSPHRASE
    )
    assert asyncio.run(reader.get_secret("db")) == secret


def test_passphrase_from_the_environment_round_trips(tmp_path, monkeypatch) -> None:
    """The env var is the documented path, so it gets its own pin."""
    monkeypatch.setenv(ENV_KEY, OPERATOR_PASSPHRASE)

    asyncio.run(
        SecretManager(backend=_disk_backend(tmp_path)).store_secret(
            "db", {"password": SENTINEL}
        )
    )
    assert asyncio.run(
        SecretManager(backend=_disk_backend(tmp_path)).get_secret("db")
    ) == {"password": SENTINEL}


def test_a_short_key_is_refused_rather_than_stretched(tmp_path) -> None:
    """100k PBKDF2 iterations do not rescue a four-character passphrase.

    Falsifying result: construction succeeds with a trivially guessable key.
    """
    with pytest.raises(SecretEncryptionError) as excinfo:
        SecretManager(backend=DictSecretBackend(), encryption_key="hunter2")

    assert "hunter2" not in str(excinfo.value), "the key itself must not be echoed"


def test_the_wrong_passphrase_does_not_return_data(tmp_path) -> None:
    """Falsifying result: a decrypt under the wrong key returns anything."""
    asyncio.run(
        SecretManager(
            backend=_disk_backend(tmp_path), encryption_key=OPERATOR_PASSPHRASE
        ).store_secret("db", {"password": SENTINEL})
    )

    wrong = SecretManager(
        backend=_disk_backend(tmp_path),
        encryption_key="a completely different passphrase entirely",
    )
    with pytest.raises(SecretEncryptionError):
        asyncio.run(wrong.get_secret("db"))


# ---------------------------------------------------------------------------
# Negative controls -- these pass before AND after the fix
# ---------------------------------------------------------------------------


def test_configured_fernet_key_still_round_trips_across_a_restart(tmp_path) -> None:
    """NEGATIVE CONTROL. Green both before and after the fix.

    Its job is to fail if the fix "closed" the defect by breaking encryption
    for everybody, which would let a broken change pass the tests above.
    """
    key = Fernet.generate_key().decode()

    asyncio.run(
        SecretManager(backend=_disk_backend(tmp_path), encryption_key=key).store_secret(
            "db", {"password": SENTINEL}
        )
    )
    assert asyncio.run(
        SecretManager(backend=_disk_backend(tmp_path), encryption_key=key).get_secret(
            "db"
        )
    ) == {"password": SENTINEL}


def test_unencrypted_storage_still_works_without_a_key() -> None:
    """NEGATIVE CONTROL. ``encrypt=False`` is an explicit caller choice.

    Refusing it would be fail-closed in the wrong place: nothing is being
    promised, so nothing is being broken.
    """
    backend = DictSecretBackend()
    manager = SecretManager(backend=backend)

    asyncio.run(manager.store_secret("plain", {"a": 1}, encrypt=False))
    assert asyncio.run(manager.get_secret("plain")) == {"a": 1}


def test_plain_values_still_read_back_without_a_key() -> None:
    """NEGATIVE CONTROL. A manager with no key must still read plain secrets.

    This is the path ``EnhancedDurableAPIGateway`` takes by default, and it is
    the reason the missing-key error fires at the encryption boundary rather
    than in ``__init__``.
    """
    backend = DictSecretBackend()
    backend.store["api"] = {"value": "not-encrypted"}

    assert asyncio.run(SecretManager(backend=backend).get_secret("api")) == {
        "value": "not-encrypted"
    }


# ---------------------------------------------------------------------------
# Envelope properties
# ---------------------------------------------------------------------------


def test_the_stored_value_does_not_contain_the_secret(tmp_path) -> None:
    """Falsifying result: the sentinel appears in what reached the backend."""
    backend = DictSecretBackend()
    asyncio.run(
        SecretManager(backend=backend, encryption_key=OPERATOR_PASSPHRASE).store_secret(
            "db", {"password": SENTINEL}
        )
    )

    assert SENTINEL not in json.dumps(backend.store)


def test_the_salt_travels_with_the_ciphertext(tmp_path) -> None:
    """A derived key is only recoverable if its salt was persisted.

    Falsifying result: no salt in the stored envelope -- which would mean the
    salt lives in memory, i.e. exactly the defect this issue is about, moved
    one layer down.
    """
    backend = DictSecretBackend()
    asyncio.run(
        SecretManager(backend=backend, encryption_key=OPERATOR_PASSPHRASE).store_secret(
            "db", {"password": SENTINEL}
        )
    )

    stored = backend.store["db"]
    envelope = json.loads(base64.urlsafe_b64decode(stored.split(":", 1)[1]))
    assert envelope["kdf"] == "pbkdf2-sha256"
    assert envelope["iterations"] >= 100_000
    assert len(base64.b64decode(envelope["salt"])) >= 16


def test_an_envelope_does_not_decrypt_under_a_different_reference() -> None:
    """Fernet has no associated-data channel, so the binding must be explicit.

    Falsifying result: an envelope copied from one reference to another is
    honoured, which substitutes an attacker-chosen secret with every integrity
    check still passing. The sibling ``FileSecretBackend`` defends this; the
    manager's own layer must too.
    """
    backend = DictSecretBackend()
    manager = SecretManager(backend=backend, encryption_key=OPERATOR_PASSPHRASE)

    asyncio.run(manager.store_secret("staging", {"password": "staging-value"}))
    backend.store["production"] = backend.store["staging"]

    with pytest.raises(SecretEncryptionError):
        asyncio.run(manager.get_secret("production"))


def test_legacy_raw_fernet_values_are_still_readable(tmp_path) -> None:
    """Anyone who set a valid Fernet key has real, recoverable data.

    Falsifying result: a value written by the pre-fix code under a properly
    configured raw key can no longer be read. Those are the only legacy values
    that were ever recoverable, and breaking them would be gratuitous.
    """
    key = Fernet.generate_key().decode()
    backend = DictSecretBackend()
    # Byte-for-byte the pre-fix wire format.
    legacy = Fernet(key.encode()).encrypt(json.dumps({"password": SENTINEL}).encode())
    backend.store["db"] = f"encrypted:{legacy.decode()}"

    manager = SecretManager(backend=backend, encryption_key=key)
    assert asyncio.run(manager.get_secret("db")) == {"password": SENTINEL}


def test_a_legacy_value_under_a_passphrase_is_a_named_migration_error() -> None:
    """Undecryptable legacy data must say so, not surface as a generic failure."""
    backend = DictSecretBackend()
    backend.store["db"] = (
        "encrypted:" + Fernet(Fernet.generate_key()).encrypt(b'{"a": 1}').decode()
    )

    manager = SecretManager(backend=backend, encryption_key=OPERATOR_PASSPHRASE)
    with pytest.raises(SecretEncryptionError):
        asyncio.run(manager.get_secret("db"))


def test_no_error_message_echoes_key_material_or_the_secret() -> None:
    """Exception text reaches logs and crash reports (``security.md``)."""
    backend = DictSecretBackend()
    manager = SecretManager(backend=backend, encryption_key=OPERATOR_PASSPHRASE)
    asyncio.run(manager.store_secret("staging", {"password": SENTINEL}))
    backend.store["production"] = backend.store["staging"]

    with pytest.raises(SecretEncryptionError) as excinfo:
        asyncio.run(manager.get_secret("production"))

    message = str(excinfo.value)
    assert OPERATOR_PASSPHRASE not in message
    assert SENTINEL not in message


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_the_code_under_test_comes_from_this_checkout() -> None:
    """Without this the whole module can pass vacuously.

    A bare ``python -c "import kailash"`` in a git worktree of this repo
    resolves the package from the MAIN checkout, not the worktree. pytest's
    ``pythonpath = src`` is what makes the worktree win, and that is a property
    worth asserting rather than assuming.

    Falsifying result: the imported module is rooted outside this repo.
    """
    import kailash.gateway.security as module

    repo_root = Path(__file__).resolve().parents[3]
    assert Path(module.__file__).resolve().is_relative_to(repo_root)
