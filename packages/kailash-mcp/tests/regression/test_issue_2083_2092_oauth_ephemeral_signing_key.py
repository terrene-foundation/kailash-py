"""Regression tests for the OAuth instance of the generate-a-key-and-continue class.

Found by the SHAPE sweep the #2083 / #2092 lane was required to run — the fourth
instance of the class, after #2041 (``SecretManager``, PR #2063), #2083
(``JWTAuthManager``) and #2092 (kaizen ``EncryptionProvider``). It is the one a
name-scoped sweep was always going to miss: a fifth distinct generator
(``rsa.generate_private_key``) in a fourth package.

Before the fix, ``JWTManager.__init__`` read::

    if private_key:
        self.private_key = serialization.load_pem_private_key(...)
    else:
        # Generate key pair
        self.private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )

No error, no warning, not even an INFO line — the #2092 signal level, on OAuth
2.1 **token signing**. Every access and refresh token minted by the process
stopped verifying at the next restart, and in a multi-replica deployment a token
issued by replica A was rejected by replica B, presenting as an intermittent,
load-balancer-dependent client bug.

Reachability was never hypothetical: ``AuthorizationServer.__init__`` and
``ResourceServer.__init__`` both default-construct a ``JWTManager``, so this
fired for operators who configured nothing.

Each test docstring names the result it would produce if the property under test
were absent, so a green here is readable as evidence rather than as a pass.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

pytest.importorskip(
    "jwt", reason="OAuth extras (PyJWT/cryptography) are required for these tests"
)

from kailash_mcp.auth import oauth as oauth_module  # noqa: E402
from kailash_mcp.auth.oauth import (  # noqa: E402
    AuthenticationError,
    AuthorizationServer,
    JWTKeyNotConfiguredError,
    JWTManager,
    ResourceServer,
)

_ISSUER = "https://auth.example.com"


def _token_str(issued) -> str:
    """Unwrap the token string.

    ``create_access_token`` returns ``Union[AccessToken, str]`` depending on how
    it is called, and ``verify_access_token`` takes the encoded string. Reading
    the union rather than assuming one arm keeps these tests measuring the key
    property instead of the return shape.
    """
    return issued if isinstance(issued, str) else issued.token


#: A real PEM keypair is expensive to generate per test; one module-scoped pair
#: stands in for "the operator configured a key".
_CONFIGURED_PEM: dict[str, str] = {}


@pytest.fixture(scope="module")
def configured_pem() -> dict[str, str]:
    """A PEM keypair representing properly-configured wiring."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if not _CONFIGURED_PEM:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _CONFIGURED_PEM["private"] = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        _CONFIGURED_PEM["public"] = (
            key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
    return _CONFIGURED_PEM


@pytest.fixture(autouse=True)
def _reset_one_time_signal():
    """Clear the ``lru_cache``d one-time signal between tests.

    Without this only the first test to trigger the signal could observe it, and
    every later assertion would read a cache hit as "no signal was emitted" —
    a test that passes for the wrong reason in both directions.
    """
    warn = getattr(oauth_module, "_warn_ephemeral_jwt_key", None)
    if warn is not None and hasattr(warn, "cache_clear"):
        warn.cache_clear()
    yield
    if warn is not None and hasattr(warn, "cache_clear"):
        warn.cache_clear()


@pytest.fixture(autouse=True)
def _no_ambient_key(monkeypatch):
    """Ensure the environment wiring is absent unless a test sets it.

    A developer machine exporting ``KAILASH_MCP_JWT_PRIVATE_KEY`` would
    otherwise turn every unconfigured-path test green for the wrong reason.
    """
    monkeypatch.delenv("KAILASH_MCP_JWT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("KAILASH_MCP_JWT_PUBLIC_KEY", raising=False)


@pytest.mark.regression
def test_the_module_under_test_is_this_worktree():
    """Provenance guard.

    A bare interpreter can resolve ``kailash_mcp`` from a different checkout or
    from site-packages, in which case every other assertion here would measure
    the wrong tree while still printing green. Falsifying result: a path outside
    this worktree.
    """
    resolved = Path(oauth_module.__file__).resolve()
    expected_root = Path(__file__).resolve().parents[2]
    assert resolved.is_relative_to(expected_root), (
        f"kailash_mcp.auth.oauth resolved to {resolved}, outside {expected_root}. "
        f"These tests would be exercising a different checkout."
    )


@pytest.mark.regression
def test_unconfigured_manager_does_not_generate_a_signing_key():
    """The defect itself: no key configured must NOT mean a minted key.

    Falsifying result (and the pre-fix behaviour): ``private_key`` is a live RSA
    key object, because ``__init__`` fell into ``rsa.generate_private_key``.
    """
    manager = JWTManager(issuer=_ISSUER)
    assert manager.private_key is None, (
        "JWTManager generated a signing key on the unconfigured path. Tokens "
        "signed with it die at restart and are rejected by every other replica."
    )
    assert manager.public_key is None


@pytest.mark.regression
def test_unconfigured_manager_refuses_to_mint_a_token():
    """Fail-closed lands at the signing boundary, naming the wiring.

    Construction stays permitted so metadata-only uses keep working, so the
    refusal has to happen here or nowhere. Falsifying result: a token string is
    returned — a token nothing else can verify.
    """
    manager = JWTManager(issuer=_ISSUER)
    with pytest.raises(JWTKeyNotConfiguredError) as exc_info:
        manager.create_access_token(subject="user-1", scope="mcp.basic")

    message = str(exc_info.value)
    assert "KAILASH_MCP_JWT_PRIVATE_KEY" in message, (
        "The refusal must name the environment variable that fixes it; an error "
        "naming no wiring is a dead end for the operator who hits it."
    )
    assert "allow_ephemeral_key" in message


@pytest.mark.regression
def test_explicit_opt_in_still_generates_but_announces_it_at_error_level(caplog):
    """Local development keeps working — loudly, not silently.

    The pre-fix path emitted NOTHING. Falsifying result: no ERROR record, i.e.
    the generated-key state is once again invisible in the logs.
    """
    with caplog.at_level(logging.DEBUG):
        manager = JWTManager(issuer=_ISSUER, allow_ephemeral_key=True)

    assert manager.private_key is not None, "opt-in must still generate"

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors, (
        "Opting into an ephemeral signing key emitted no ERROR. Silence here is "
        "the #2092 failure mode: unverifiable tokens with nothing in the logs."
    )
    joined = " ".join(r.getMessage() for r in errors)
    assert (
        "KAILASH_MCP_JWT_PRIVATE_KEY" in joined
    ), "The loud signal must name the wiring that turns it off."


@pytest.mark.regression
def test_the_signal_never_carries_the_key_material(caplog):
    """A fix that fails loudly must not become a disclosure bug.

    ``security.md`` forbids logging key material or any fingerprint that
    reconstructs it. Falsifying result: PEM material, or a base64/hex run long
    enough to be key-shaped, appears in the emitted records.
    """
    with caplog.at_level(logging.DEBUG):
        manager = JWTManager(issuer=_ISSUER, allow_ephemeral_key=True)

    from cryptography.hazmat.primitives import serialization

    pem = manager.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    body = "".join(
        line for line in pem.splitlines() if not line.startswith("-----")
    ).strip()

    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "BEGIN PRIVATE KEY" not in logged
    assert "BEGIN RSA PRIVATE KEY" not in logged
    # Any 40-char window of the real key body would be an unacceptable leak.
    assert body[:40] not in logged, "generated key material reached the log"


@pytest.mark.regression
def test_the_loud_signal_fires_once_per_process_not_once_per_instance(caplog):
    """Once per process, matching the #2063 shape.

    A per-instance line from a library is what an operator learns to filter out.
    Falsifying result: two ERROR records for two managers.
    """
    with caplog.at_level(logging.DEBUG):
        JWTManager(issuer=_ISSUER, allow_ephemeral_key=True)
        JWTManager(issuer=_ISSUER, allow_ephemeral_key=True)

    errors = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "GENERATED" in r.getMessage().upper()
    ]
    assert (
        len(errors) == 1
    ), f"expected exactly one process-wide signal, got {len(errors)}"


@pytest.mark.regression
def test_a_configured_key_works_with_no_spurious_signal(caplog, configured_pem):
    """The other polarity: properly wired must be silent AND functional.

    A fix that shouted at correctly-configured operators would be re-tuned to
    INFO within a release, which is how #2083 got quiet in the first place.
    Falsifying result: an ERROR record, or a token that will not verify.
    """
    with caplog.at_level(logging.DEBUG):
        manager = JWTManager(
            issuer=_ISSUER,
            private_key=configured_pem["private"],
            public_key=configured_pem["public"],
        )
        issued = manager.create_access_token(subject="user-1", scope="mcp.basic")
        claims = manager.verify_access_token(_token_str(issued))

    assert claims["sub"] == "user-1"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, (
        f"configured path emitted {len(errors)} ERROR record(s): "
        f"{[r.getMessage() for r in errors]}"
    )


@pytest.mark.regression
def test_environment_variable_supplies_the_key_with_no_code_change(
    monkeypatch, configured_pem
):
    """The wiring the error message advertises must actually be read.

    An error naming a variable nothing reads is worse than silence — it sends
    the operator to a setting that changes nothing. Falsifying result:
    construction still yields ``private_key is None`` despite the export.
    """
    monkeypatch.setenv("KAILASH_MCP_JWT_PRIVATE_KEY", configured_pem["private"])
    monkeypatch.setenv("KAILASH_MCP_JWT_PUBLIC_KEY", configured_pem["public"])

    manager = JWTManager(issuer=_ISSUER)
    assert manager.private_key is not None, (
        "KAILASH_MCP_JWT_PRIVATE_KEY was exported but not read; the error "
        "message advertises wiring that does nothing."
    )
    issued = manager.create_access_token(subject="user-1", scope="mcp.basic")
    assert manager.verify_access_token(_token_str(issued))["sub"] == "user-1"


@pytest.mark.regression
def test_two_managers_from_the_same_configured_key_interoperate(configured_pem):
    """The multi-replica property, which is the operational half of the defect.

    Restart-durability and cross-replica verification are the same property:
    a token minted under configured material verifies in a DIFFERENT manager
    instance. Falsifying result (the pre-fix behaviour): replica B rejects
    replica A's token because each generated its own key.
    """
    replica_a = JWTManager(
        issuer=_ISSUER,
        private_key=configured_pem["private"],
        public_key=configured_pem["public"],
    )
    replica_b = JWTManager(
        issuer=_ISSUER,
        private_key=configured_pem["private"],
        public_key=configured_pem["public"],
    )

    issued = replica_a.create_access_token(subject="user-1", scope="mcp.basic")
    claims = replica_b.verify_access_token(_token_str(issued))
    assert (
        claims["sub"] == "user-1"
    ), "a token minted by one replica must verify on another sharing the key"


@pytest.mark.regression
@pytest.mark.parametrize("server_cls", [AuthorizationServer, ResourceServer])
def test_the_servers_that_default_construct_a_manager_are_fail_closed(server_cls):
    """Reachability: the wrappers are what put this on the default path.

    ``AuthorizationServer`` and ``ResourceServer`` both default-construct a
    ``JWTManager``, which is how a silent generator reached operators who
    configured nothing — the same wrapper-propagation that hid #2092 behind
    ``FieldEncryptor``. Falsifying result: a server constructs with a live
    generated signing key.
    """
    kwargs = {"issuer": _ISSUER}
    if server_cls is ResourceServer:
        kwargs.update(audience="https://mcp.example.com/mcp")

    server = server_cls(**kwargs)
    assert server.jwt_manager.private_key is None, (
        f"{server_cls.__name__} default-constructed a JWTManager that generated "
        f"a signing key; the wrapper laundered the unconfigured default."
    )


@pytest.mark.regression
@pytest.mark.parametrize("method_name", ["verify_access_token", "verify_refresh_token"])
def test_both_verify_paths_report_the_missing_key_the_same_way(method_name):
    """One manager, one missing key, one operator experience.

    ``verify_refresh_token``'s handler chain ends in a bare
    ``except Exception: return None``, and ``JWTKeyNotConfiguredError`` subclasses
    ``AuthenticationError`` rather than ``jwt.InvalidTokenError`` — so with the
    key resolved INSIDE the try it was caught by that final handler, logged, and
    returned as a ``None`` the caller renders as "Invalid refresh token". Its
    sibling ``verify_access_token`` propagated the typed refusal for the same
    manager in the same state. An operator debugging one path was told to check
    their wiring; on the other, that the client sent a bad token.

    Returning ``None`` is a reject, not a fail-open — but it is precisely the
    generic client-looking rejection the typed refusal exists to replace.

    Falsifying result: the call returns ``None`` (or any value at all) instead of
    raising, which is what ``verify_refresh_token`` did before the key was
    hoisted ahead of the try.
    """
    manager = JWTManager(issuer=_ISSUER)

    with pytest.raises(JWTKeyNotConfiguredError) as exc_info:
        getattr(manager, method_name)("any.token.value")

    assert "KAILASH_MCP_JWT_PUBLIC_KEY" in str(exc_info.value) or (
        "KAILASH_MCP_JWT_PRIVATE_KEY" in str(exc_info.value)
    ), "the refusal must name the wiring that fixes it, on both paths"


@pytest.mark.regression
def test_the_refresh_path_still_rejects_a_bad_token_when_the_key_is_configured(
    configured_pem,
):
    """The other polarity: hoisting the key resolution changed nothing else.

    A configured manager must still turn a malformed or wrongly-typed token into
    the ordinary ``AuthenticationError``, not into the not-configured refusal.

    Falsifying result: ``JWTKeyNotConfiguredError`` escapes on a configured
    manager, meaning the hoist broke the normal rejection path.
    """
    manager = JWTManager(
        issuer=_ISSUER,
        private_key=configured_pem["private"],
        public_key=configured_pem["public"],
    )

    with pytest.raises(AuthenticationError) as exc_info:
        manager.verify_refresh_token("not.a.jwt")

    assert not isinstance(exc_info.value, JWTKeyNotConfiguredError), (
        "a configured manager must report a bad token as a bad token, not as "
        "missing configuration"
    )


@pytest.mark.regression
def test_an_access_token_is_refused_by_the_refresh_verifier(caplog, configured_pem):
    """Token-type separation survives the hoist.

    This pins the branch nearest the change: the token-type check that runs
    INSIDE the try, whose reachability the hoist must not alter.

    It also RECORDS a pre-existing shape this test discovered and deliberately
    does NOT change. That branch is written as
    ``raise AuthenticationError("Invalid token type")``, but the method's own
    trailing ``except Exception`` catches it, logs it at ERROR, and returns
    ``None`` — so the raise never reaches a caller. The rejection is real and
    loud, and it matches ``verify_access_token``, which returns ``None`` for the
    same condition; converting it to a propagating raise would introduce an
    asymmetry between the two verifiers rather than remove one, and would change
    a documented ``Optional[Dict]`` contract. Filed as a follow-up rather than
    fixed here.

    Falsifying result: an access token verifies as a refresh token — i.e. a
    payload comes back instead of ``None``.
    """
    manager = JWTManager(
        issuer=_ISSUER,
        private_key=configured_pem["private"],
        public_key=configured_pem["public"],
    )
    issued = manager.create_access_token(subject="user-1", scope="mcp.basic")

    with caplog.at_level(logging.DEBUG):
        result = manager.verify_refresh_token(_token_str(issued))

    assert result is None, (
        "an access token was accepted by the refresh verifier; token-type "
        "separation is what stops a short-lived token being replayed for a "
        "30-day one"
    )
    assert any(
        "Invalid token type" in r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.ERROR
    ), "the rejection must leave an ERROR record naming the reason"
