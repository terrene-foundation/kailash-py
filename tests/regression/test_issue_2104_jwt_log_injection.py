"""Regression: attacker-supplied JWT header ``kid`` reaching a log line (#2104).

``JWTAuthManager.verify_token`` reads the presented token's header with
``jwt.get_unverified_header`` -- BEFORE any signature check, because reading it
is how the verification key gets selected -- and logged the ``kid`` it found by
interpolation::

    logger.warning(f"Token signed with unknown key ID: {key_id}")

So an unauthenticated caller chose the bytes of a ``WARNING`` record. An
embedded newline forges a second well-formed record; a NUL and an ANSI escape
corrupt a console operator's view and downstream SIEM ingestion. It fires on
the FAILURE path, which is the path a key-ID prober drives repeatedly.

**The instrument is the emitted STREAM, not the LogRecord.** A forged record is
forged at FORMAT time: ``caplog`` would show one ``LogRecord`` either way, so
counting records cannot tell a sanitized call from an unsanitized one. These
tests attach a real ``StreamHandler`` with a real ``Formatter`` and count LINES
in what the handler wrote, which is what a log collector actually ingests. If
the value were unsanitized the stream would carry three lines and the control
bytes -- that is the result that would falsify each assertion below.
"""

import io
import logging

import pytest

from kailash.middleware.auth.jwt_auth import JWTAuthManager
from kailash.middleware.auth.models import JWTConfig

# Imported AFTER the module-level imports on purpose: `jwt_auth` guards its own
# PyJWT import (`jwt = None` on ImportError), so importing it is safe without
# the optional dependency, while every test below needs the real library.
jwt = pytest.importorskip("jwt", reason="PyJWT is required for JWT log-injection tests")
pytest.importorskip(
    "cryptography", reason="cryptography is required for the RSA key-id path"
)

#: One value carrying every structural threat the sanitizer must neutralize:
#: a CRLF pair (forges a record), a bare LF (forges another), a NUL (truncates
#: C-string consumers), and an ANSI CSI sequence (rewrites a terminal).
INJECTION = (
    "kid-a\r\n2026-01-01 ERROR forged: admin login succeeded\n"
    "\x00\x1b[31mred\x1b[0m tail"
)

#: Every byte that must not survive INSIDE an emitted line. ``\n`` is not in
#: this list because a ``StreamHandler`` appends its own terminator to every
#: record: a newline the ATTACKER injected shows up as a SECOND line, which is
#: what the line count below asserts on, while the handler's own trailing
#: terminator is not a finding.
CONTROL_BYTES = ("\r", "\x00", "\x1b")


class _StreamProbe:
    """Capture what a real ``Formatter`` writes for one logger."""

    def __init__(self, logger_name: str, level: int = logging.DEBUG):
        self._logger = logging.getLogger(logger_name)
        self._buffer = io.StringIO()
        self._handler = logging.StreamHandler(self._buffer)
        self._handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        self._handler.setLevel(level)
        self._level = level

    def __enter__(self) -> "_StreamProbe":
        self._prior_level = self._logger.level
        self._prior_propagate = self._logger.propagate
        self._logger.setLevel(self._level)
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc_info) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prior_level)
        self._logger.propagate = self._prior_propagate

    @property
    def text(self) -> str:
        self._handler.flush()
        return self._buffer.getvalue()

    @property
    def lines(self) -> list[str]:
        """Non-empty lines the handler emitted, one per un-forged record."""
        return [line for line in self.text.split("\n") if line]


def _assert_single_clean_line(probe: _StreamProbe, expect_substring: str) -> None:
    """One emitted line, no control bytes, and the value still diagnosable."""
    assert probe.lines, "no record was emitted at all -- the probe missed the call"
    assert len(probe.lines) == 1, (
        "an injected newline forged an extra log line: expected exactly ONE, got "
        f"{len(probe.lines)}: {probe.lines!r}"
    )
    for byte in CONTROL_BYTES:
        assert (
            byte not in probe.lines[0]
        ), f"control byte {byte!r} survived into the record: {probe.lines[0]!r}"
    assert expect_substring in probe.text, (
        "the sanitizer redacted the diagnostic instead of neutralizing it: "
        f"{probe.text!r}"
    )


@pytest.fixture
def rsa_manager() -> JWTAuthManager:
    """An RSA manager: the ``kid`` check only runs on the RSA verification path."""
    return JWTAuthManager(
        config=JWTConfig(
            algorithm="RS256",
            use_rsa=True,
            auto_generate_keys=True,
            issuer="test-issuer",
            audience="test-audience",
        )
    )


class TestUnknownKeyIdIsSanitized:
    """The headline site: ``jwt_auth.py`` ``verify_token`` unknown-``kid`` warning."""

    def test_attacker_chosen_kid_yields_one_clean_record(self, rsa_manager):
        """A forged ``kid`` cannot forge a log record.

        The token is signed with the manager's OWN private key so that
        ``jwt.decode`` succeeds and the run reaches the revocation check --
        proving the warning fired on a token that verified, not on a decode
        error that would have taken a different branch.
        """
        token = jwt.encode(
            {
                "sub": "alice",
                "iss": "test-issuer",
                "aud": "test-audience",
                "exp": 2**31 - 1,
            },
            rsa_manager._private_key,
            algorithm="RS256",
            headers={"kid": INJECTION},
        )

        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.WARNING) as probe:
            payload = rsa_manager.verify_token(token)

        assert payload["sub"] == "alice", "the token must still verify"
        _assert_single_clean_line(probe, "kid-a")

    def test_oversized_kid_is_bounded(self, rsa_manager):
        """A megabyte ``kid`` cannot drive log volume."""
        token = jwt.encode(
            {
                "sub": "alice",
                "iss": "test-issuer",
                "aud": "test-audience",
                "exp": 2**31 - 1,
            },
            rsa_manager._private_key,
            algorithm="RS256",
            headers={"kid": "A" * 100_000},
        )

        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.WARNING) as probe:
            rsa_manager.verify_token(token)

        assert (
            len(probe.text) < 1_000
        ), f"the record grew with the attacker's input: {len(probe.text)} chars"


class TestSiblingSitesInTheSameFile:
    """The five siblings #2104 named. A per-site fix here is the drift #2088 documents."""

    @pytest.fixture
    def manager(self) -> JWTAuthManager:
        return JWTAuthManager(secret_key="s" * 48, issuer="iss", audience="aud")

    def test_create_access_token_user_id(self, manager):
        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.DEBUG) as probe:
            manager.create_access_token(user_id=INJECTION)
        _assert_single_clean_line(probe, "kid-a")

    def test_create_refresh_token_user_id(self, manager):
        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.DEBUG) as probe:
            manager.create_refresh_token(user_id=INJECTION)
        _assert_single_clean_line(probe, "kid-a")

    def test_revoke_token_jti(self, manager):
        """``jti`` is decoded from a token the caller presented."""
        token = jwt.encode(
            {
                "sub": "alice",
                "iss": "iss",
                "aud": "aud",
                "exp": 2**31 - 1,
                "jti": INJECTION,
            },
            "s" * 48,
            algorithm="HS256",
        )
        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.INFO) as probe:
            manager.revoke_token(token)
        _assert_single_clean_line(probe, "kid-a")

    def test_revoke_refresh_token_jti(self, manager):
        manager._refresh_tokens[INJECTION] = {"user_id": "alice"}
        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.INFO) as probe:
            manager.revoke_refresh_token(INJECTION)
        _assert_single_clean_line(probe, "kid-a")

    def test_revoke_all_user_tokens_user_id(self, manager):
        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.INFO) as probe:
            manager.revoke_all_user_tokens(INJECTION)
        _assert_single_clean_line(probe, "kid-a")

    def test_verification_error_text_cannot_forge_records(self):
        """The ``except Exception`` sink at ``verify_token`` renders foreign text.

        Measured first, rather than assumed: PyJWT's OWN messages do not echo
        the presented bytes -- ``DecodeError`` reports ``'Invalid header
        string: Invalid control character at: line 1 column 25'``, naming a
        POSITION and not the content. So the taint on this sink does not come
        from PyJWT; it comes from any OTHER exception that reaches it, and the
        documented extension point that can raise one is the revocation store
        (``revocation_store=``, a public constructor argument whose contract
        invites third-party Redis/database backends).

        The store below is a REAL implementation of the public
        :class:`TokenRevocationStore` contract, not a mock of the unit under
        test: it is the collaborator, and a backend that fails with a message
        it read from a remote system is the ordinary case.
        """
        from kailash.middleware.auth.revocation import TokenRevocationStore

        class RaisingStore(TokenRevocationStore):
            """A backend whose failure text carries bytes it did not author."""

            def revoke(self, *, jti=None, token=None, expires_at=None) -> None:
                return None

            def is_revoked(self, *, jti=None, token=None) -> bool:
                raise RuntimeError(f"backend refused: {INJECTION}")

        manager = JWTAuthManager(
            secret_key="s" * 48,
            issuer="iss",
            audience="aud",
            revocation_store=RaisingStore(),
        )
        token = manager.create_access_token(user_id="alice")

        with _StreamProbe("kailash.middleware.auth.jwt_auth", logging.ERROR) as probe:
            with pytest.raises(Exception):
                manager.verify_token(token)

        _assert_single_clean_line(probe, "backend refused")
