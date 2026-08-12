"""Regression tests for issue #2083 — JWTAuthManager invented its HS256 signing secret.

Before the fix, ``JWTAuthManager()`` with nothing configured generated a fresh
HS256 secret via ``secrets.token_urlsafe(32)`` and continued, announcing it at
``logger.info``. ``JWTConfig.auto_generate_keys`` defaulted to ``True``, so this
fired for operators who never opted into anything.

The secret lived only inside that process, which produced two failures that
present as a client bug rather than a server misconfiguration:

- every token issued before a restart fails verification after it, and
- in a multi-replica deployment each replica signs with a different secret, so a
  token minted by replica A is rejected by replica B — intermittently, depending
  on which replica the load balancer picked.

Same class as #2041 (``SecretManager``, fixed in PR #2063) and #2092 (kaizen
``EncryptionProvider``). #2041's own sibling sweep MISSED this site because it
was scoped to the literal string ``Fernet.generate_key``; this site uses a
different generator.

Each test's docstring names the result it would produce if the property under
test were absent, so a green here is readable as evidence rather than as "the
suite passed".
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from kailash.middleware.auth import JWTAuthManager, JWTConfig
from kailash.middleware.auth import jwt_auth as jwt_auth_module

#: At least 32 characters, matching the floor documented for JWT signing keys.
CONFIGURED_SECRET = "a-configured-signing-secret-at-least-32-chars"


@pytest.fixture(autouse=True)
def _reset_one_time_signal():
    """Clear the ``lru_cache``d one-time signal between tests.

    The signal fires once per process by design, so without this reset only the
    first test to trigger it could observe it and every later assertion would
    read a cache hit as "the signal is gone".
    """
    warn = getattr(jwt_auth_module, "_warn_ephemeral_signing_key", None)
    if warn is not None and hasattr(warn, "cache_clear"):
        warn.cache_clear()
    yield
    if warn is not None and hasattr(warn, "cache_clear"):
        warn.cache_clear()


@pytest.fixture(autouse=True)
def _no_ambient_secret(monkeypatch):
    """Ensure the environment wiring is absent unless a test sets it.

    Without this a developer machine exporting ``KAILASH_JWT_SECRET_KEY`` would
    turn every unconfigured-path test green for the wrong reason.
    """
    monkeypatch.delenv("KAILASH_JWT_SECRET_KEY", raising=False)


@pytest.mark.regression
def test_the_module_under_test_is_this_worktree():
    """Provenance guard.

    ``pytest.ini`` sets ``pythonpath = src``, which is inserted ahead of any
    ambient ``PYTHONPATH`` — but a bare interpreter in this worktree resolves
    ``kailash`` from the MAIN checkout instead. If that ever regressed, every
    other assertion in this file would be measuring the wrong tree while still
    printing green. Falsifying result: a path outside this worktree.
    """
    resolved = Path(jwt_auth_module.__file__).resolve()
    expected_root = Path(__file__).resolve().parents[2]
    assert resolved.is_relative_to(expected_root), (
        f"jwt_auth resolved to {resolved}, which is outside {expected_root}. "
        "These tests would be exercising a different checkout."
    )


@pytest.mark.regression
def test_hs256_default_path_refuses_to_invent_a_signing_secret():
    """The defect: ``JWTAuthManager()`` bare must not mint its own secret.

    Falsifying result if the fix were absent: no exception, and
    ``manager._secret_key`` holds a freshly generated value.
    """
    with pytest.raises(ValueError) as excinfo:
        JWTAuthManager()

    message = str(excinfo.value)
    assert "KAILASH_JWT_SECRET_KEY" in message, (
        "The error must name the environment variable that fixes it. " f"Got: {message}"
    )
    assert "secret_key=" in message, "The error must name the constructor wiring."


@pytest.mark.regression
def test_rsa_default_path_refuses_to_invent_a_key_pair():
    """The RSA arm of the same function carries the identical defect.

    ``_initialize_keys`` branches on ``use_rsa`` before it reaches the HS256
    code, so a fix applied only to the ``else:`` arm would leave the class alive
    on ``JWTAuthManager(use_rsa=True)`` — the exact form this module's own
    docstring advertises.

    Falsifying result if the fix were absent: no exception, and a 2048-bit RSA
    key pair generated in-process.
    """
    with pytest.raises(ValueError) as excinfo:
        JWTAuthManager(use_rsa=True)

    message = str(excinfo.value)
    assert (
        "private_key" in message and "public_key" in message
    ), f"The RSA error must name the keys it needs. Got: {message}"


@pytest.mark.regression
def test_two_managers_sharing_a_configured_secret_mint_interoperable_tokens():
    """The multi-replica property, stated positively (AC of #2083).

    Models two replicas configured from the same source: a token minted by one
    MUST verify on the other. Before the fix each replica generated its own
    secret and this failed intermittently in production.

    Falsifying result if the property were absent: ``verify_token`` raises
    ``InvalidTokenError`` on the second manager.
    """
    replica_a = JWTAuthManager(secret_key=CONFIGURED_SECRET)
    replica_b = JWTAuthManager(secret_key=CONFIGURED_SECRET)

    token = replica_a.create_access_token(user_id="user-1")
    payload = replica_b.verify_token(token)

    # ``verify_token`` returns a plain dict, not a ``TokenPayload`` — driven,
    # not inferred from the annotation.
    assert payload["sub"] == "user-1"


@pytest.mark.regression
def test_environment_variable_supplies_the_secret_with_no_code_change():
    """The wiring the error message names must actually work.

    An error that names a variable the code never reads is worse than no
    message at all — #2041 shipped exactly that (``KAILASH_ENCRYPTION_KEY``
    appeared once in the repo, at its own read site).

    The assertion is that the manager signs with THAT value, not merely that it
    constructs and round-trips a token: a manager that ignored the variable and
    generated its own secret would also mint and verify its own token happily,
    so a round-trip alone cannot tell the two apart. Before the fix this test
    passed for exactly that wrong reason.

    Falsifying result if the read were absent: ``_secret_key`` holds a generated
    value rather than ``CONFIGURED_SECRET`` (or construction raises).
    """
    import os

    os.environ["KAILASH_JWT_SECRET_KEY"] = CONFIGURED_SECRET
    try:
        manager = JWTAuthManager()
        assert manager._secret_key == CONFIGURED_SECRET, (
            "The manager did not sign with the environment-supplied secret; it "
            "used its own value, so the variable named in the error message is "
            "not actually wired."
        )
        token = manager.create_access_token(user_id="env-user")
        assert manager.verify_token(token)["sub"] == "env-user"

        # A second manager from the same variable is the multi-replica case.
        assert JWTAuthManager().verify_token(token)["sub"] == "env-user"
    finally:
        del os.environ["KAILASH_JWT_SECRET_KEY"]


@pytest.mark.regression
def test_explicit_opt_in_still_generates_but_announces_it_at_error_level(caplog):
    """Dev ergonomics are retained, but only as an EXPLICIT opt-in, and loudly.

    ``security.md`` § Secure-Default For A New Security Feature permits the
    generate-and-continue path only behind a loud one-time signal naming the
    protection that is off and its exact wiring. The signal it replaces was
    ``logger.info("Generated new HS256 secret key")``, which named neither.

    Falsifying result if the fix were absent: the record is emitted at INFO, or
    names neither the ephemerality nor the wiring.
    """
    with caplog.at_level(logging.INFO, logger="kailash.middleware.auth.jwt_auth"):
        manager = JWTAuthManager(auto_generate_keys=True)

    assert manager._secret_key, "The opt-in path must still produce a usable key."

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, (
        "The ephemeral-key path must announce itself at ERROR. Records seen: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )
    message = errors[0].getMessage()
    assert "KAILASH_JWT_SECRET_KEY" in message, "The signal must name the wiring."
    assert "restart" in message.lower(), "The signal must name the consequence."


@pytest.mark.regression
def test_the_loud_signal_fires_once_per_process_not_once_per_instance(caplog):
    """A per-instance line from a library is a line operators learn to filter.

    Falsifying result if the ``lru_cache`` were absent: two ERROR records for
    two managers.
    """
    with caplog.at_level(logging.INFO, logger="kailash.middleware.auth.jwt_auth"):
        JWTAuthManager(auto_generate_keys=True)
        JWTAuthManager(auto_generate_keys=True)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, (
        f"Expected exactly one process-wide signal, got {len(errors)}: "
        f"{[r.getMessage() for r in errors]}"
    )


@pytest.mark.regression
def test_the_signal_never_carries_the_generated_key_material(caplog):
    """A fix that fails loudly must not itself print the secret.

    ``security.md`` forbids logging key material; a signal that echoed the
    generated secret would convert a durability bug into a disclosure bug.

    Falsifying result if the property were absent: the generated secret appears
    verbatim in a captured log record.
    """
    with caplog.at_level(logging.DEBUG, logger="kailash.middleware.auth.jwt_auth"):
        manager = JWTAuthManager(auto_generate_keys=True)

    secret = manager._secret_key
    assert secret
    for record in caplog.records:
        assert (
            secret not in record.getMessage()
        ), "The generated signing secret leaked into a log record."


@pytest.mark.regression
def test_rsa_opt_in_also_announces_itself_at_error_level(caplog):
    """The RSA arm must carry the same signal as the HS256 arm.

    Falsifying result if only the HS256 arm were fixed: no ERROR record for an
    RSA manager that generated a throwaway key pair.
    """
    with caplog.at_level(logging.INFO, logger="kailash.middleware.auth.jwt_auth"):
        JWTAuthManager(use_rsa=True, auto_generate_keys=True)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, (
        "The RSA ephemeral-key path must announce itself at ERROR. Records: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )


@pytest.mark.regression
def test_a_configured_manager_emits_no_ephemeral_key_signal(caplog):
    """Negative control.

    A change that "fixed" the defect by shouting on every construction — including
    correctly configured ones — would be indistinguishable from the real fix in
    every other test here. This one fails in that case.

    Falsifying result: an ERROR record from a properly configured manager.
    """
    with caplog.at_level(logging.DEBUG, logger="kailash.middleware.auth.jwt_auth"):
        JWTAuthManager(secret_key=CONFIGURED_SECRET)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, (
        f"Configured manager emitted a spurious signal: "
        f"{[r.getMessage() for r in errors]}"
    )


@pytest.mark.regression
def test_configured_rsa_keys_still_load_without_a_signal(caplog):
    """Negative control for the RSA arm.

    Falsifying result: a manager handed a real key pair still raises or still
    signals, which would mean the fix broke the configured path rather than the
    defective one.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    with caplog.at_level(logging.DEBUG, logger="kailash.middleware.auth.jwt_auth"):
        manager = JWTAuthManager(
            config=JWTConfig(
                use_rsa=True,
                algorithm="RS256",
                private_key=private_pem,
                public_key=public_pem,
            )
        )

    token = manager.create_access_token(user_id="rsa-user")
    assert manager.verify_token(token)["sub"] == "rsa-user"

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert (
        not errors
    ), f"Configured RSA manager signalled: {[r.getMessage() for r in errors]}"


@pytest.mark.regression
def test_the_loud_signal_names_the_current_constants(caplog):
    """The signal spells its variable names literally, so it can drift.

    ``_warn_ephemeral_signing_key`` writes ``KAILASH_JWT_SECRET_KEY`` as a
    literal rather than interpolating :data:`JWT_SECRET_KEY_ENV`, because CodeQL
    reads a constant with that name as key material flowing into a log sink.
    The cost of the literal is that renaming the constant would leave the
    message pointing at a variable that no longer exists.

    Falsifying result if the two drifted: the constant's value is absent from
    the emitted message.
    """
    with caplog.at_level(logging.INFO, logger="kailash.middleware.auth.jwt_auth"):
        JWTAuthManager(auto_generate_keys=True)

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, "No signal emitted; the drift guard has nothing to check."
    assert jwt_auth_module.JWT_SECRET_KEY_ENV in errors[0].getMessage(), (
        f"The signal names a variable that is no longer "
        f"{jwt_auth_module.JWT_SECRET_KEY_ENV}: {errors[0].getMessage()}"
    )


@pytest.mark.regression
def test_auto_generate_keys_is_not_the_shipped_default():
    """The config default is the reason the defect was on the shipped path.

    Falsifying result if the default were left at ``True``: this assertion reads
    ``True`` and fails.
    """
    assert JWTConfig().auto_generate_keys is False, (
        "auto_generate_keys must default to False; it being True is what put "
        "ephemeral signing keys on the path of operators who configured nothing."
    )
