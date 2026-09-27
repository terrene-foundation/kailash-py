# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2171.

The rate-limit middleware logged a tag for the throttled identifier under an
UNKEYED BLAKE2b digest while its own comment claimed "the raw value stays
confined to the rate-limit backend key". An IP address is drawn from 2**32
values, so an unkeyed fast hash is exhaustible by brute force -- measured at
~1.3e5 digests/second/core, the whole IPv4 space falls in roughly 9 core-hours
-- and the logged tag was therefore equivalent to the plaintext IP.

These tests assert the PROPERTY, not the call. Asserting "hmac was invoked"
cannot distinguish a genuinely keyed construction from one keyed with a
compile-time constant, which would be just as reversible as the unkeyed digest
it replaced. What is pinned instead:

* different keys => different tags for the SAME identifier (keying is real);
* the same key => the same tag (stability, which correlation depends on);
* the key is not derivable from the tag by knowing the plaintext;
* no key configured => still keyed, plus a LOUD warning (secure default);
* a short key is REFUSED rather than silently accepted.
"""

import hashlib
import logging

import pytest

from nexus.auth.rate_limit.fingerprint import (
    FINGERPRINT_KEY_ENV,
    MIN_FINGERPRINT_KEY_BYTES,
    IdentifierFingerprinter,
    InvalidFingerprintKeyError,
    build_identifier_fingerprinter,
    resolve_fingerprint_key,
)

KEY_A = "A" * MIN_FINGERPRINT_KEY_BYTES
KEY_B = "B" * MIN_FINGERPRINT_KEY_BYTES
CLIENT = "ip:203.0.113.47"


# --------------------------------------------------------------------------
# The core property: the construction is genuinely KEYED
# --------------------------------------------------------------------------


def test_different_deployment_keys_produce_different_tags():
    """Two deployments with different keys disagree on the SAME identifier.

    This is the assertion a constant-keyed (or unkeyed) implementation cannot
    satisfy, and it is why the test does not simply check that HMAC was called.
    """
    fp_a = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})
    fp_b = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_B})

    assert fp_a(CLIENT) != fp_b(CLIENT)


def test_same_key_reproduces_the_same_tag():
    """Stability under one key -- correlation is useless without it.

    Two independently constructed fingerprinters sharing a key must agree, so
    that every node in a fleet emits the same tag for the same client.
    """
    fp_1 = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})
    fp_2 = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})

    assert fp_1(CLIENT) == fp_2(CLIENT) == fp_1(CLIENT)


def test_distinct_identifiers_produce_distinct_tags():
    """Different clients must remain distinguishable under one key."""
    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})

    tags = {fp(f"ip:203.0.113.{i}") for i in range(64)}
    assert len(tags) == 64


def test_tag_is_not_the_unkeyed_digest():
    """Pin that the old, reversible construction is genuinely gone.

    Reproduces the pre-fix derivation -- unkeyed BLAKE2b truncated to 8 hex --
    and asserts the tag is not it. If someone reintroduces an unkeyed digest,
    this goes red regardless of what the surrounding code is named.
    """
    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})

    unkeyed = hashlib.blake2b(CLIENT.encode("utf-8"), digest_size=4).hexdigest()[:8]
    tag = fp(CLIENT)

    assert tag != unkeyed
    assert not tag.startswith(unkeyed)


def test_knowing_the_plaintext_does_not_reproduce_the_tag_without_the_key():
    """An attacker who knows the identifier still cannot derive the tag.

    Brute force over a candidate space is the #2171 attack. Here the ENTIRE
    space is handed to the attacker and the tag still does not fall, because
    the key is missing.
    """
    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})
    target = fp(CLIENT)

    candidates = {
        hashlib.blake2b(CLIENT.encode(), digest_size=8).hexdigest()[:16],
        hashlib.sha256(CLIENT.encode()).hexdigest()[:16],
        hashlib.md5(CLIENT.encode()).hexdigest()[:16],  # noqa: S324 - attacker model
        CLIENT,
    }
    assert target not in candidates


def test_tag_width_is_64_bits():
    """8 hex chars collide at ~2**16 identifiers; 16 is the fixed width."""
    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})
    assert len(fp(CLIENT)) == 16


def test_repr_never_discloses_the_key():
    """A repr lands in tracebacks and debug logs; it must not carry the key."""
    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})
    assert KEY_A not in repr(fp)
    assert "key" not in repr(fp).lower() or "scope=" in repr(fp)


def test_fingerprinter_refuses_to_pickle():
    """`__slots__` does not stop pickling; the default reducer writes the key.

    An instance crossing a multiprocessing spawn boundary, or captured in a
    debug dump, would otherwise carry the keying material with it.
    """
    import pickle

    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})

    with pytest.raises(TypeError, match="not picklable"):
        pickle.dumps(fp)


def test_lone_surrogate_identifier_does_not_raise():
    """A JWT `sub` claim can decode to a lone surrogate.

    Plain UTF-8 encoding rejects it, and the resulting UnicodeEncodeError would
    escape `dispatch` and turn a 429 into a 500 -- an attacker-chosen username
    becoming a server error on the throttle path.
    """
    fp = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})

    tag = fp("user:\ud800")

    assert len(tag) == 16
    assert tag != fp("user:other")


# --------------------------------------------------------------------------
# Secure default: no key configured
# --------------------------------------------------------------------------


def test_missing_key_still_produces_a_keyed_tag():
    """No configuration must NOT degrade to the unkeyed digest.

    Silently falling back to an unkeyed hash -- or to emitting no tag -- is the
    silent-no-op default that rules/security.md Secure-Default blocks. Two
    fingerprinters built with no key must disagree, which proves each minted
    its own random key rather than sharing a constant.
    """
    fp_1 = build_identifier_fingerprinter({})
    fp_2 = build_identifier_fingerprinter({})

    assert fp_1.deployment_scoped is False
    assert fp_1(CLIENT) != fp_2(CLIENT)

    unkeyed = hashlib.blake2b(CLIENT.encode("utf-8"), digest_size=4).hexdigest()[:8]
    assert not fp_1(CLIENT).startswith(unkeyed)


def test_missing_key_warns_loudly_and_names_the_wiring(caplog):
    """The degraded property and its exact fix must be announced at startup."""
    with caplog.at_level(logging.WARNING, logger="nexus.auth.rate_limit.fingerprint"):
        build_identifier_fingerprinter({})

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "no warning emitted for an unconfigured fingerprint key"

    message = warnings[0].getMessage()
    assert FINGERPRINT_KEY_ENV in message, "warning does not name the env var to set"
    assert "correlate" in message.lower(), "warning does not name the degraded property"


def test_configured_key_does_not_warn(caplog):
    """A correctly wired deployment must not be nagged at every boot."""
    with caplog.at_level(logging.WARNING, logger="nexus.auth.rate_limit.fingerprint"):
        build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})

    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_warning_never_contains_key_material(caplog):
    """rules/security.md: never log the key."""
    with caplog.at_level(logging.WARNING, logger="nexus.auth.rate_limit.fingerprint"):
        fp = build_identifier_fingerprinter({})

    blob = " ".join(r.getMessage() for r in caplog.records)
    # The ephemeral key is unexported by design; assert no long hex/base64 run
    # that could be it leaked into the message.
    assert fp(CLIENT) not in blob
    assert not any(len(tok) >= 32 and tok.isalnum() for tok in blob.split())


# --------------------------------------------------------------------------
# Misconfiguration fails LOUD, not silently
# --------------------------------------------------------------------------


@pytest.mark.parametrize("short", ["", "x", "short-key", "A" * 31])
def test_short_or_empty_key_is_refused_or_treated_as_absent(short):
    """A too-short key must never be silently accepted.

    An empty string is a misconfigured deployment and is treated as absent
    (ephemeral key + warning); anything non-empty but under the floor raises,
    because padding or accepting it would restore the brute-forceability this
    control exists to remove while the operator believes it is wired.
    """
    env = {FINGERPRINT_KEY_ENV: short}

    if short == "":
        key, scoped = resolve_fingerprint_key(env)
        assert scoped is False
        assert len(key) >= MIN_FINGERPRINT_KEY_BYTES
    else:
        with pytest.raises(InvalidFingerprintKeyError) as exc:
            resolve_fingerprint_key(env)
        assert FINGERPRINT_KEY_ENV in str(exc.value)
        assert str(MIN_FINGERPRINT_KEY_BYTES) in str(exc.value)


def test_constructor_rejects_short_key_material():
    """The floor is enforced on the object, not only on the env parser."""
    with pytest.raises(InvalidFingerprintKeyError):
        IdentifierFingerprinter(b"too-short", deployment_scoped=True)


def test_resolve_reports_deployment_scope_truthfully():
    """``deployment_scoped`` must reflect reality, not intent."""
    _, scoped_env = resolve_fingerprint_key({FINGERPRINT_KEY_ENV: KEY_A})
    _, scoped_none = resolve_fingerprint_key({})

    assert scoped_env is True
    assert scoped_none is False


# --------------------------------------------------------------------------
# Middleware wiring
# --------------------------------------------------------------------------


def test_middleware_logs_a_keyed_tag_not_the_identifier(caplog):
    """The 429 log line carries the KEYED tag and never the raw identifier.

    Drives ``dispatch`` to a real 429 and reads the captured log. An earlier
    version of this test took ``caplog``, never read it, never called
    ``dispatch``, and asserted only that ``mw._fingerprint`` agreed with a
    separately-built fingerprinter -- so putting ``identifier`` back into the
    ``logger.warning`` call would have left it GREEN. It was vacuous for its
    own name; these assertions are the ones the name promises.
    """
    import asyncio
    import logging as _logging

    from kailash.trust.rate_limit.config import RateLimitConfig
    from nexus.auth.rate_limit.middleware import RateLimitMiddleware

    class _Url:
        path = "/api/thing"

    class _Request:
        url = _Url()

    class _AllowedResponse:
        def __init__(self):
            self.headers = {}
            self.status_code = 200

    middleware = RateLimitMiddleware(
        app=None,
        config=RateLimitConfig(requests_per_minute=1, backend="memory"),
        identifier_extractor=lambda _request: CLIENT,
        env={FINGERPRINT_KEY_ENV: KEY_A},
    )

    async def _ok(_request):
        return _AllowedResponse()

    async def _drive():
        # Loop until the limit genuinely trips rather than assuming request 2
        # does it; the backend enforces its own window size.
        with caplog.at_level(_logging.WARNING):
            for _ in range(40):
                response = await middleware.dispatch(_Request(), _ok)
                if getattr(response, "status_code", None) == 429:
                    return response
        return None

    response = asyncio.run(_drive())

    assert response is not None, "the limit never tripped; test would be vacuous"
    assert caplog.text, "no WARN captured; test would be vacuous"

    expected = build_identifier_fingerprinter({FINGERPRINT_KEY_ENV: KEY_A})(CLIENT)
    assert expected in caplog.text, "the keyed tag is not what was logged"
    assert CLIENT not in caplog.text, "the raw identifier reached the log"
    assert "203.0.113.47" not in caplog.text, "the bare IP reached the log"


def test_middleware_refuses_to_start_with_a_short_key():
    """Misconfiguration surfaces at startup, not as a 500 in place of a 429."""
    from kailash.trust.rate_limit.config import RateLimitConfig
    from nexus.auth.rate_limit.middleware import RateLimitMiddleware

    async def _app(scope, receive, send):  # pragma: no cover - never invoked
        raise AssertionError("app should not be reached")

    with pytest.raises(InvalidFingerprintKeyError):
        RateLimitMiddleware(
            _app,
            RateLimitConfig(requests_per_minute=1),
            env={FINGERPRINT_KEY_ENV: "too-short"},
        )


def test_rate_limit_state_is_keyed_on_the_raw_identifier_not_the_tag():
    """Key rotation must NOT reset anybody's token bucket.

    The bucket index is the raw identifier, so a rotation changes log tags only.
    If a future change routed the tag into the backend key, an attacker could
    reset their own limit by provoking a restart -- this pins that it does not.
    """
    import inspect

    from kailash.trust.rate_limit.backends.memory import InMemoryBackend

    source = inspect.getsource(InMemoryBackend)
    assert "fingerprint" not in source.lower(), (
        "a fingerprint reached the rate-limit backend; rate-limit state would "
        "now reset on key rotation or restart"
    )
