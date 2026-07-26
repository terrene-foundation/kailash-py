# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for issue #1974 — error_sanitizer pattern-coverage gaps.

Three gap classes, surfaced by the Wave-F holistic security redteam:

1. Non-http(s) connection-string credentials. ``_URL_WITH_AUTH`` anchored on
   ``https?://``, so ``postgres://``/``redis://``/``mongodb://``/``mysql://``
   embedded passwords survived unredacted. Includes the EMPTY-userinfo shape
   (``redis://:pass@``) that the issue's own proposed one-liner
   (``(\\w+://)[^@\\s]+:[^@\\s]+@``) still leaks, because ``[^@\\s]+`` demands a
   non-empty username.
2. Slack tokens (``xox[baprse]-``) and bare (non-``Bearer``) JWTs (``eyJ...``).
   Both carry segment separators (``-``/``.``/``_``) that break the 40-char
   ``[A-Za-z0-9/+]`` contiguous run, so no pre-existing pattern claimed them.
3. Negative-vector hardening: long URLs/paths must NOT over-redact.

All credential vectors below are obviously synthetic.

Note on gap 3 and the module's stated false-positive posture: the
``FALSE-POSITIVE-vs-SENSITIVITY DECISION`` comment at
``src/kaizen/nodes/ai/error_sanitizer.py:69-84`` records a deliberate
decision to ACCEPT broad over-redaction of any
40+ char contiguous ``[A-Za-z0-9/+]`` run. ``/`` and ``+`` are IN that class, so
a long unbroken URL path IS redacted by design. The negative vectors here are
therefore built from realistic URLs/paths whose runs are broken by ``.``, ``-``,
``?``, ``=`` and ``&`` — they assert the absence of over-redaction for the shapes
the posture actually claims to leave alone.
"""

from __future__ import annotations

import base64
import re
import time

import pytest

from kaizen.nodes.ai.error_sanitizer import (
    _CREDENTIAL_PATTERNS,
    sanitize_provider_error,
)

pytestmark = pytest.mark.regression

# --- Gap 1: connection-string credentials across schemes ---------------------

# (vector, secret that must not survive)
_DSN_VECTORS = [
    ("postgresql://admin:hunter2@db.internal:5432/appdb", "hunter2"),
    ("postgres://admin:hunter2@db.internal:5432/appdb", "hunter2"),
    # SQLAlchemy-style driver-qualified scheme (contains '+')
    ("postgresql+asyncpg://svc:s3cret-pw@db.internal/appdb", "s3cret-pw"),
    # EMPTY userinfo — the shape the issue's own proposed regex still leaks
    ("redis://:hunter2@cache.internal:6379/0", "hunter2"),
    ("rediss://:hunter2@cache.internal:6380/0", "hunter2"),
    ("mongodb://mongouser:m0ngopass@mongo.internal:27017/d", "m0ngopass"),
    ("mongodb+srv://mongouser:m0ngopass@mongo.internal/d", "m0ngopass"),
    ("mysql://root:toor-pw@mysql.internal:3306/app", "toor-pw"),
    ("amqp://rabbit:r4bbitpw@broker.internal:5672/vhost", "r4bbitpw"),
    # Literal '@' inside the password — RFC 3986 says percent-encode it, but
    # real DSNs carry it. A `[^@\s]` userinfo class stops at the FIRST '@' and
    # leaks the tail; found by self-redteam of the first fix attempt.
    ("postgres://user:p@ssw0rd-x@db.internal/app", "ssw0rd-x"),
    # Literal '@' inside the username (Azure AD / corp-directory style).
    ("postgres://ad@corp.example.com:s3cret@db.internal/app", "s3cret"),
]


@pytest.mark.parametrize("dsn,secret", _DSN_VECTORS, ids=[v[0] for v in _DSN_VECTORS])
def test_connection_string_password_redacted(dsn: str, secret: str) -> None:
    """Embedded DSN passwords are redacted for ANY scheme, not just http(s)."""
    out = sanitize_provider_error(RuntimeError(f"connect failed: {dsn}"), "test")
    assert secret not in out, f"password leaked for {dsn!r}: {out!r}"
    assert "[REDACTED]:[REDACTED]@" in out, f"no userinfo redaction in {out!r}"


def test_redis_empty_userinfo_is_the_regression_vector() -> None:
    """`redis://:pass@` — non-empty-username regexes leak this; ours must not.

    This is the specific shape issue #1974 names in gap 1 whose proposed
    one-line fix does NOT close.
    """
    out = sanitize_provider_error(
        RuntimeError("ConnectionError: redis://:hunter2@cache.internal:6379"), "test"
    )
    assert "hunter2" not in out, out
    assert "redis://[REDACTED]:[REDACTED]@cache.internal:6379" in out, out


@pytest.mark.parametrize(
    "text",
    [
        # no '@' at all — nothing to redact
        "GET http://example.com/path returned 502",
        # port colon AND a path colon, but no credentials
        "GET http://host.example.com:8080/a:b returned 404",
        # '://' appearing mid-prose
        "Malformed endpoint: expected the scheme:// prefix, got a bare host",
        # scheme + host + port, no userinfo
        "Connection to redis://cache.internal:6379 refused",
        # a bare email elsewhere in the message must not pair with the URL's
        # port colon to form a false userinfo match (greedy userinfo is still
        # whitespace-terminated)
        "http://api.example.com:8080/v1 failed for user@example.com",
        "Timeout on https://api.example.com/v1/chat after 30s; contact ops@example.com",
    ],
)
def test_urls_without_credentials_are_not_redacted(text: str) -> None:
    """The broadened userinfo match must not fire on credential-free URLs."""
    out = sanitize_provider_error(RuntimeError(text), "test")
    assert "[REDACTED]" not in out, f"over-redacted: {out!r}"


# --- Gap 2: Slack tokens + bare JWTs ----------------------------------------

_SLACK_VECTORS = [
    "xoxb-2345678901-2345678901-abcdefghijklmnopqrstuvwx",
    "xoxp-1111111111-2222222222-zyxwvutsrqponmlkjihgfed",
    "xoxa-2-1111111111-2222222222-aaaaaaaaaaaaaaaaaaaaaa",
    "xoxr-3333333333-4444444444-bbbbbbbbbbbbbbbbbbbbbbb",
    "xoxs-5555555555-6666666666-cccccccccccccccccccccc",
    "xoxe-7777777777-8888888888-dddddddddddddddddddddd",
]


@pytest.mark.parametrize("token", _SLACK_VECTORS)
def test_slack_token_redacted(token: str) -> None:
    out = sanitize_provider_error(RuntimeError(f"slack auth failed: {token}"), "test")
    assert token not in out, f"slack token leaked: {out!r}"
    assert "[REDACTED]" in out, out


@pytest.mark.parametrize(
    "text",
    [
        # 'xoxo' is not a token family letter (families are b/a/p/r/s/e)
        "retry token xoxo-abcdefghijklmnop was rejected",
        # ordinary hyphenated prose
        "proxy-configuration-error-code-1234567890 returned",
    ],
)
def test_slack_pattern_does_not_over_match(text: str) -> None:
    out = sanitize_provider_error(RuntimeError(text), "test")
    assert "[REDACTED]" not in out, f"over-redacted: {out!r}"


_BARE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IlRlc3QifQ"
    ".dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
)


def test_bare_jwt_redacted() -> None:
    """A JWT with no `Bearer ` prefix must still be redacted.

    Its `-`/`_`/`.` separators break the 40-char contiguous-run pattern, so
    before #1974 no pattern claimed it.
    """
    out = sanitize_provider_error(RuntimeError(f"401 token={_BARE_JWT}"), "test")
    assert _BARE_JWT not in out, f"bare JWT leaked: {out!r}"
    # no JWT segment survives
    for segment in _BARE_JWT.split("."):
        assert segment not in out, f"JWT segment {segment!r} survived in {out!r}"


def test_jwt_pattern_does_not_redact_arbitrary_base64_json() -> None:
    """`eyJ` is just base64 for `{"` — a bare base64 JSON blob is NOT a JWT.

    The three-segment (`header.payload.signature`) structure is what makes the
    pattern discriminating; without it we must not redact.
    """
    blob = base64.b64encode(b'{"ok":true,"role":"viewer"}').decode().rstrip("=")
    assert blob.startswith("eyJ"), blob
    out = sanitize_provider_error(RuntimeError(f"decoded payload {blob}"), "test")
    assert "[REDACTED]" not in out, f"over-redacted non-JWT base64: {out!r}"
    assert blob in out, out


def test_jwt_pattern_itself_never_matches_base64_json_of_any_length() -> None:
    """Isolate the JWT rule from the pre-existing 40-char contiguous-run rule.

    The module-level assertion above uses a SHORT (<40 char) blob, because a
    base64 blob of 40+ unbroken ``[A-Za-z0-9/+]`` chars is redacted by the AWS
    secret-key rule (error_sanitizer.py:69-84) regardless of what the JWT rule
    does — that is the module's documented false-positive posture, not a JWT
    over-match. This test therefore asserts against the compiled JWT pattern
    DIRECTLY, at lengths on both sides of the 40-char threshold, so a future
    loosening of the JWT rule (e.g. dropping a required segment) fails here even
    though the module-level output would still look "redacted".
    """
    jwt_pattern = next(
        p for p in _CREDENTIAL_PATTERNS if p.pattern.startswith(r"\beyJ")
    )
    payloads = [
        b'{"ok":true,"role":"viewer"}',
        b'{"status":"degraded","region":"eu-west-1","retries":3}',
        b'{"a":' + b'"x"' * 60 + b"}",
    ]
    for raw in payloads:
        blob = base64.b64encode(raw).decode().rstrip("=")
        assert blob.startswith("eyJ"), blob
        assert jwt_pattern.search(blob) is None, (
            f"JWT pattern matched a non-JWT base64-JSON blob of len {len(blob)}: "
            f"{jwt_pattern.search(blob).group(0)!r}"  # type: ignore[union-attr]
        )


def test_jwt_pattern_requires_all_three_segments() -> None:
    """A two-segment `eyJ...` value is not a JWT and must not be redacted."""
    two_seg = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    out = sanitize_provider_error(RuntimeError(f"partial {two_seg}"), "test")
    assert "[REDACTED]" not in out, f"over-redacted 2-segment value: {out!r}"


# --- Gap 3: long URL / long path negative vectors ---------------------------

_LONG_URL = (
    "https://api.example.com/v1/models/chat-completions/streaming-endpoint"
    "?request-id=abc-123&trace=xyz-789"
)
_LONG_PATH = (
    "/opt/app-runtime/kaizen-service/config-store/provider-settings/default-model.yaml"
)


@pytest.mark.parametrize(
    "value", [_LONG_URL, _LONG_PATH], ids=["long-url", "long-path"]
)
def test_long_url_and_path_are_not_over_redacted(value: str) -> None:
    """>40-char URLs/paths survive intact when no 40+ char run of the
    ``[A-Za-z0-9/+]`` secret class is present.

    Guards the module's documented false-positive posture (error_sanitizer.py
    :69-84): the AWS-secret pattern's broad over-redaction is scoped to
    contiguous runs, and realistic URLs/paths are separator-broken well below
    the threshold.
    """
    assert len(value) > 40, value
    # The vector must not itself trip the documented 40+ contiguous-run rule.
    longest_run = max(len(r) for r in re.findall(r"[A-Za-z0-9/+]+", value))
    assert longest_run < 40, (
        f"vector has a {longest_run}-char [A-Za-z0-9/+] run; the module's stated "
        f"posture redacts those by design (error_sanitizer.py:69-84)"
    )

    out = sanitize_provider_error(RuntimeError(f"Request to {value} failed"), "test")
    assert "[REDACTED]" not in out, f"over-redacted: {out!r}"
    assert value in out, out


def test_documented_posture_still_holds_for_true_long_runs() -> None:
    """Counterpart to the negative vectors: a genuine 40+ contiguous run IS
    still redacted, per the deliberate decision at error_sanitizer.py:69-84."""
    secret = "A" * 20 + "b" * 20  # 40-char contiguous [A-Za-z0-9/+] run
    out = sanitize_provider_error(RuntimeError(f"signature {secret}"), "test")
    assert secret not in out, out
    assert "[REDACTED]" in out, out


# --- Known, PRE-EXISTING over-redaction shapes (pinned, not introduced) ------


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "GET http://host.example.com:8080/@handle returned 404",
            "GET http://[REDACTED]:[REDACTED]@handle returned 404",
        ),
        (
            "GET https://api.example.com/s?q=name:foo@bar.com failed",
            "GET https://[REDACTED]:[REDACTED]@bar.com failed",
        ),
    ],
    ids=["at-sign-in-path", "at-sign-in-query"],
)
def test_known_over_redaction_shapes_are_unchanged_from_before(
    text: str, expected: str
) -> None:
    """A credential-free URL carrying BOTH a ':' and a later '@' over-redacts.

    Pinned deliberately. This is NOT introduced by the #1974 scheme broadening:
    the pre-#1974 pattern ``(https?://)[^@\\s]+:[^@\\s]+@`` produces byte-identical
    output on both vectors, because ``8080/`` and ``com/s?q=name`` satisfy a
    ``[^@\\s]+`` userinfo just as they satisfy ``[^\\s]*``. Narrowing the userinfo
    class back to ``[^@\\s]`` would therefore NOT fix these while it WOULD
    re-open the ``redis://:pass@`` and ``user:p@ssw0rd@host`` leaks above.

    Pinning the exact strings means any future attempt to widen the userinfo
    match further shows up here as a diff rather than silently.
    """
    out = sanitize_provider_error(RuntimeError(text), "test")
    assert out == f"test error (RuntimeError): {expected}", out


def test_url_auth_scan_is_linear_not_quadratic() -> None:
    """The broadened userinfo match must not be quadratic in token length.

    Two adjacent unbounded greedy runs joined by a literal (``[^\\s]*:[^\\s]*@``)
    backtrack quadratically on the NO-MATCH path: a colon-dense token with no
    ``@`` makes the engine retry every ``:`` against every suffix. Measured
    before the ``{0,256}`` bound landed, a 64 KB synthetic token cost ~4.5s of
    CPU per call — on an error path whose text a provider can echo back from
    user input.

    Asserted as a self-normalising RATIO across an 8x size step measured in the
    same process, not an absolute wall-clock threshold: linear is ~8x, quadratic
    is ~64x, so the bound sits between them and is machine-independent.
    """
    small = "http://" + "a:" * 4_000  # 8k chars
    large = "http://" + "a:" * 32_000  # 64k chars, 8x

    def cost(text: str, reps: int = 5) -> float:
        best = float("inf")
        for _ in range(reps):
            start = time.perf_counter()
            sanitize_provider_error(RuntimeError(text), "test")
            best = min(best, time.perf_counter() - start)
        return best

    ratio = cost(large) / cost(small)
    assert ratio < 25, (
        f"sanitize_provider_error scaled {ratio:.1f}x for an 8x longer token "
        f"(linear ~8x, quadratic ~64x) — a userinfo quantifier probably lost "
        f"its length bound"
    )


# --- SCOPE ADDITION beyond the #1974 acceptance criteria ---------------------
#
# Surfaced by self-redteam of the gap-2 fix: `ghp_`/`sk_live_` are the SAME bug
# class the issue names for Slack (an opaque secret behind a fixed vendor prefix
# whose "_" separator drops it under the 40-char contiguous-run threshold), and
# they leaked identically. Closed in the same change rather than deferred; these
# tests and the corresponding patterns are the only content here NOT traceable
# to an issue AC, and are contiguous so they can be reverted as one block.

_PREFIXED_VENDOR_TOKENS = [
    "ghp_16C7e42F292c6912E7710c838347Ae178B4a",
    "gho_16C7e42F292c6912E7710c838347Ae178B4a",
    "ghu_16C7e42F292c6912E7710c838347Ae178B4a",
    "ghs_16C7e42F292c6912E7710c838347Ae178B4a",
    "ghr_16C7e42F292c6912E7710c838347Ae178B4a",
    "github_pat_11ABCDEFG0abcdefghij_KLMNOPqrstuvwxyz0123456789ABCDEFGH",
    "sk_live_51H8xKlAbCdEfGhIjKlMnOpQr",
    "sk_test_51H8xKlAbCdEfGhIjKlMnOpQr",
    "rk_live_51H8xKlAbCdEfGhIjKlMnOpQr",
]


@pytest.mark.parametrize("token", _PREFIXED_VENDOR_TOKENS)
def test_prefixed_vendor_token_redacted(token: str) -> None:
    out = sanitize_provider_error(RuntimeError(f"auth rejected: {token}"), "test")
    assert token not in out, f"vendor token leaked: {out!r}"
    assert "[REDACTED]" in out, out


@pytest.mark.parametrize(
    "text",
    [
        # "gh" + a letter outside [pousr] + "_"
        "ghi_module_loader_failed to initialise correctly",
        # "ghost_" — the 4th char is not "_", so the family rule cannot fire
        "ghost_writer_process_1234567890 exited",
        # hyphenated sk- prose is the OTHER (pre-existing) rule's shape
        "sk_unknown_mode_1234567890 is not a recognised mode",
        # a bare "rk_" without live/test
        "rk_staging_51H8xKlAbCdEfGhIjKlMnOpQr is not a Stripe key shape",
    ],
)
def test_prefixed_vendor_patterns_do_not_over_match(text: str) -> None:
    out = sanitize_provider_error(RuntimeError(text), "test")
    assert "[REDACTED]" not in out, f"over-redacted: {out!r}"


# ---------------------------------------------------------------------------
# Overflow companion rule — found by the holistic redteam's security lens.
# ---------------------------------------------------------------------------


def test_userinfo_longer_than_the_dos_bound_is_still_redacted() -> None:
    """A password longer than ``_URL_WITH_AUTH``'s 256-char bound must not leak.

    The bound is a DoS guard, and its original rationale claimed an overlong
    secret would be "claimed by the 40-char contiguous-run rule instead". That
    is FALSE for any secret containing ``-``, ``_`` or ``.`` — those characters
    are outside ``[A-Za-z0-9/+]`` and break the run. A 272-char hyphenated DSN
    password therefore leaked IN FULL: too long for the bounded rule, too
    fragmented for the contiguous-run rule.

    Realistic instance: a Cloud SQL IAM OAuth access token used as the DSN
    password. Closed by ``_URL_WITH_AUTH_OVERFLOW``.
    """
    password = "-".join("abcdefghijklmnopqrst" for _ in range(13))
    assert len(password) > 256, "vector must exceed the bound it is testing"

    out = sanitize_provider_error(
        RuntimeError(f"connect failed: postgres://svc:{password}@db.internal:5432/app"),
        "test",
    )

    assert password not in out, f"overlong userinfo leaked in full: {out!r}"
    assert "[REDACTED]" in out


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        # git-over-HTTPS with a PAT — the canonical shape.
        (
            "git clone https://s3cretT0kenValue@github.com/org/repo failed",
            "s3cretT0kenValue",
        ),
        # API that accepts a token as the HTTP-basic username.
        (
            "GET https://opaqueApiTokenXYZ@api.example.com/v1 -> 401",
            "opaqueApiTokenXYZ",
        ),
        # Broker DSN with a token and no password half.
        ("amqp://myTokenOnly@broker.internal:5672/vhost refused", "myTokenOnly"),
    ],
)
def test_userinfo_without_password_is_redacted(text: str, secret: str) -> None:
    """`scheme://<token>@host` — userinfo with NO password half.

    Both user:pass rules require a literal ``:``, so a bare token in the
    USERNAME position was matched by NEITHER. Only tokens carrying a recognised
    vendor prefix were caught incidentally by ``_CREDENTIAL_PATTERNS``; an opaque
    one leaked in full. Pre-existing — the original
    ``https?://[^@\\s]+:[^@\\s]+@`` required the colon too.
    """
    out = sanitize_provider_error(RuntimeError(text), "test")
    assert secret not in out, f"userinfo token leaked: {out!r}"
    assert "[REDACTED]@" in out


@pytest.mark.parametrize(
    "text",
    [
        # `/` is excluded from the userinfo class precisely so a PATH segment is
        # never mistaken for userinfo. These must all pass through untouched.
        "https://example.com/@handle is the profile",
        "git://host/user@thing checked out",
        "contact mailto:a@b.com in the log",
        "http://example.com/path returned 500",
    ],
)
def test_userinfo_only_rule_does_not_eat_path_segments(text: str) -> None:
    out = sanitize_provider_error(RuntimeError(text), "test")
    assert "[REDACTED]" not in out, f"over-redacted a credential-free URL: {out!r}"


def test_user_pass_shape_survives_the_userinfo_only_rule() -> None:
    """Ordering guard: the no-colon rule runs LAST and must not re-match.

    The two user:pass rules rewrite to ``scheme://[REDACTED]:[REDACTED]@``, which
    contains a ``:`` and is therefore invisible to the no-colon rule. If that
    ordering is ever inverted, the user/pass split would collapse to a single
    ``[REDACTED]`` and this test fails.
    """
    out = sanitize_provider_error(
        RuntimeError("postgres://admin:hunter2@db:5432/x"), "test"
    )
    assert "[REDACTED]:[REDACTED]@" in out, f"user/pass split was collapsed: {out!r}"


def test_scheme_broadening_is_linear_on_input_with_no_scheme() -> None:
    """The SCHEME prefix must be length-bounded, not just the userinfo halves.

    #1974 broadened `(https?://)` to `([A-Za-z][A-Za-z0-9+.-]*://)`. That trades a
    FIXED LITERAL — which fails in O(1) per start position — for an unbounded
    greedy run, and on input with a long alphanumeric stretch and NO `://` the
    engine retries that run from every start position. Measured before the bound:
    4 KB 7.9 ms / 16 KB 112 ms / 64 KB 1773 ms, against 0.015 ms pre-#1974.

    **The sibling linearity tests cannot catch this**: their input is
    `"http://" + "a:"*n`, which CONTAINS `://`, so the scheme matches immediately
    and never backtracks. A regression here is invisible to them by construction —
    which is exactly how this shipped. This test's input deliberately has NO
    `://` at all.

    Possessive quantifiers do NOT fix it (backtracking is over start positions,
    not inside the group); only bounding the scheme does.
    """
    small = "a" * 8_000
    large = "a" * 64_000  # 8x

    def cost(text: str, reps: int = 5) -> float:
        best = float("inf")
        for _ in range(reps):
            start = time.perf_counter()
            sanitize_provider_error(RuntimeError(text), "test")
            best = min(best, time.perf_counter() - start)
        return best

    ratio = cost(large) / max(cost(small), 1e-9)
    assert ratio < 25, (
        f"8x input scaled {ratio:.1f}x — the scheme prefix is backtracking "
        "quadratically; check that every URL rule bounds it "
        "([A-Za-z0-9+.-]{0,31}://), not just the userinfo halves"
    )


def test_overflow_rule_scan_is_linear_not_quadratic() -> None:
    """The overflow rule must not reintroduce the DoS the bound exists to stop.

    ``_URL_WITH_AUTH_OVERFLOW`` is deliberately UNBOUNDED (that is the point —
    it must reach secrets longer than 256 chars), so its linearity rests
    entirely on the first run excluding ``:``. An earlier revision used
    ``[^\\s@]*:[^\\s@]*@``, allowing ``:`` in the first run, which retries every
    interior colon against every suffix: 4 KB → 59 ms, 16 KB → 923 ms,
    64 KB → 14.8 s. Stopping the first run at the FIRST ``:`` makes the split
    point deterministic.

    Same self-normalising 8x-ratio shape as the bounded rule's test: linear is
    ~8x, quadratic ~64x, so the bound between them is machine-independent.
    """
    small = "http://" + "a:" * 4_000
    large = "http://" + "a:" * 32_000

    def cost(text: str, reps: int = 5) -> float:
        best = float("inf")
        for _ in range(reps):
            start = time.perf_counter()
            sanitize_provider_error(RuntimeError(text), "test")
            best = min(best, time.perf_counter() - start)
        return best

    ratio = cost(large) / max(cost(small), 1e-9)
    assert ratio < 25, (
        f"8x input scaled {ratio:.1f}x — the overflow rule is backtracking "
        "quadratically; check that its first run still excludes ':'"
    )
