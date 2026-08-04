# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Round-3 Finding 4: `Basic` auth and credential-ANNOUNCING `key=value`.

`_CREDENTIAL_PATTERNS` anchored `Bearer` but NOT `Basic`, and carried no rule
for `password=` / `api_key=` / `client_secret=` / `access_token=` and friends.
So `Authorization: Basic dXNlcjpwYXNzd29yZA==` and `password=hunter2longenough`
passed through IN FULL on BOTH presets.

Both classes are credential-ANNOUNCING — the string literally names its own
value as a secret — so they belong OUTSIDE `_OPAQUE_SHAPE_PATTERNS`, i.e. ON
under the conservative preset too, at zero false-positive cost. That is the
same argument the `(?i:signature|sig)=` widening already won.

WHY THE CONSERVATIVE PRESET IS THE LOAD-BEARING HALF: `scrub_local_error`
switches OFF the only two rules that can claim a prefix-less credential, so on
that surface a literal-anchored rule is the ONLY thing between a credential and
the log. A test that only exercised `scrub_remote_error` would pass on a
`_OPAQUE_SHAPE_PATTERNS`-misclassified rule and prove nothing.
"""

from __future__ import annotations

import time

import pytest

from kaizen.utils.credential_scrub import (
    DEFAULT_PLACEHOLDER,
    scrub_credentials,
    scrub_local_error,
    scrub_remote_error,
)

# A base64 of "user:password" — reversible, not a digest.
_BASIC_VALUE = "dXNlcjpwYXNzd29yZA=="

_BASIC_CASES = [
    pytest.param(f"Authorization: Basic {_BASIC_VALUE}", id="header-form"),
    pytest.param(f"401 Unauthorized (Basic {_BASIC_VALUE})", id="inline-form"),
    pytest.param(f"authorization: basic {_BASIC_VALUE}", id="lowercase"),
    pytest.param(f"Authorization: BASIC {_BASIC_VALUE}", id="uppercase"),
]

_KEYVALUE_CASES = [
    pytest.param("password=hunter2longenough", "hunter2longenough", id="password"),
    pytest.param("passwd=hunter2longenough", "hunter2longenough", id="passwd"),
    pytest.param("pwd=hunter2longenough", "hunter2longenough", id="pwd"),
    pytest.param("secret=s3cr3tvaluelong", "s3cr3tvaluelong", id="secret"),
    pytest.param("api_key=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="api_key"),
    pytest.param("api-key=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="api-key"),
    pytest.param("apikey=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="apikey"),
    pytest.param(
        "access_token=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="access_token"
    ),
    pytest.param(
        "refresh_token=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="refresh_token"
    ),
    pytest.param(
        "client_secret=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="client_secret"
    ),
    pytest.param(
        "private_key=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="private_key"
    ),
    # Separator + quoting variants a real repr / YAML / JSON dump produces.
    pytest.param(
        'password: "hunter2longenough"', "hunter2longenough", id="colon-quoted"
    ),
    pytest.param("password = hunter2longenough", "hunter2longenough", id="spaced-eq"),
    pytest.param(
        "'password': 'hunter2longenough'", "hunter2longenough", id="dict-repr"
    ),
]


@pytest.mark.regression
class TestBasicAuthIsRedactedOnBothPresets:
    @pytest.mark.parametrize("text", _BASIC_CASES)
    def test_basic_credential_does_not_survive(self, text: str) -> None:
        for name, scrub in (
            ("scrub_local_error", scrub_local_error),
            ("scrub_remote_error", scrub_remote_error),
            ("scrub_credentials", scrub_credentials),
        ):
            out = scrub(text)
            assert _BASIC_VALUE not in out, (
                f"{name}() left an HTTP Basic credential intact: {out!r}. "
                "base64 of 'user:password' is reversible — this is a live "
                "credential, not a digest."
            )
            assert DEFAULT_PLACEHOLDER in out

    def test_bearer_still_redacted(self) -> None:
        """CONTROL. The sibling rule that already worked must not regress."""
        tok = "abcdefghijklmnopqrstuvwxyz012345"
        for scrub in (scrub_local_error, scrub_remote_error):
            assert tok not in scrub(f"Authorization: Bearer {tok}")


@pytest.mark.regression
class TestCredentialAnnouncingKeyValueIsRedactedOnBothPresets:
    @pytest.mark.parametrize("text,secret", _KEYVALUE_CASES)
    def test_secret_value_does_not_survive(self, text: str, secret: str) -> None:
        for name, scrub in (
            ("scrub_local_error", scrub_local_error),
            ("scrub_remote_error", scrub_remote_error),
        ):
            out = scrub(text)
            assert secret not in out, (
                f"{name}() left a credential-ANNOUNCING value intact: {out!r}. "
                "The key literally names it a secret; nothing else claims this "
                "shape (no vendor prefix, and the shape-only rules are OFF "
                "under the conservative preset)."
            )

    def test_conservative_preset_is_the_load_bearing_half(self) -> None:
        """The whole point: this shape leaks worst where shape rules are OFF."""
        text = "password=hunter2longenough"
        assert "hunter2longenough" not in scrub_local_error(text), (
            "a rule that only fires under the REMOTE preset would leave this "
            "credential on every local-error surface; the rule must live "
            "OUTSIDE _OPAQUE_SHAPE_PATTERNS"
        )


@pytest.mark.regression
class TestNoFalsePositivesOnOrdinaryText:
    """The new rules are literal-anchored, so credential-free prose is intact.

    The repo-wide tripwire for this is
    `test_scrub_credentials_ordinary_text_is_not_noop.py`; these are the cases
    specific to the two new rules — text that MENTIONS the keywords without
    carrying a credential.
    """

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("Basic authentication is not configured", id="basic-prose"),
            pytest.param("basic usage: see the README", id="basic-lowercase-prose"),
            pytest.param("password must be at least 8 characters", id="password-prose"),
            pytest.param("the api_key argument is required", id="api-key-prose"),
            pytest.param("Invalid secret format", id="secret-prose"),
            pytest.param("password=", id="empty-value"),
            pytest.param("pwd=1", id="short-sentinel-value"),
            pytest.param("secret: null", id="null-value"),
            pytest.param("Connection timed out after 30s", id="unrelated"),
        ],
    )
    def test_credential_free_text_is_unchanged(self, text: str) -> None:
        assert scrub_local_error(text) == text, (
            "a literal-anchored rule rewrote text carrying no credential; the "
            "conservative preset's whole contract is 'matches nothing but a "
            "real credential'"
        )


@pytest.mark.regression
class TestNewRulesAreLinear:
    """Module contract: any NEW pattern lands with a linearity test.

    Self-normalising 8x ratio per `rules/testing.md` § Complexity Bounds — an
    absolute wall-clock bound ratchets upward under CI load until it masks the
    regression it exists to catch.

    Both new rules establish a DETERMINISTIC SPLIT POINT rather than relying on
    bounded quantifiers: `Basic` is followed by `\\s+` then a class that
    EXCLUDES whitespace; the key=value rule's separator `[=:]` is excluded from
    the surrounding `\\s*` runs, and its value class excludes the quote
    characters the optional `["']?` can match. Neither can float.
    """

    @staticmethod
    def _elapsed(text: str) -> float:
        start = time.perf_counter()
        scrub_credentials(text)
        return time.perf_counter() - start

    @pytest.mark.parametrize(
        "unit,label",
        [
            # Repeats the ANCHOR without ever completing a match — the shape
            # that would backtrack if the rule were ambiguous.
            #
            # The key=value units end in a character EXCLUDED from the value
            # class (","), which is what stops the run self-completing: a bare
            # `"password=" * n` is `password=password=password=...`, and the
            # value class happily consumes the rest of the payload, so the
            # guard-the-guard assertion below (correctly) rejects it as a
            # vacuous linearity probe. That rejection is the guard working.
            pytest.param("Basic ", "basic-anchor-run"),
            pytest.param("password=,", "keyvalue-anchor-run"),
            pytest.param("password:,", "keyvalue-colon-run"),
        ],
    )
    def test_anchor_dense_input_is_linear(self, unit: str, label: str) -> None:
        base_units = 500
        small = unit * base_units
        large = unit * (base_units * 8)

        # Guard the guard: a payload already consumed by some other rule would
        # make the timing assertion pass vacuously on a short string.
        assert scrub_credentials(small) == small, (
            f"[{label}] the linearity payload is being consumed by a pattern "
            "before the new rules run; this test would pass vacuously"
        )

        small_t = min(self._elapsed(small) for _ in range(5))
        large_t = min(self._elapsed(large) for _ in range(5))
        ratio = large_t / small_t if small_t > 0 else 1.0

        assert ratio < 25, (
            f"[{label}] 8x input scaled {ratio:.1f}x (linear ~8x, quadratic "
            "~64x) — a new rule probably lost its deterministic split point"
        )
