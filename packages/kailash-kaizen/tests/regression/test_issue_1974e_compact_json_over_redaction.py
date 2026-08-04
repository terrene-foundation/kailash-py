# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: compact-JSON over-redaction in `_URL_WITH_AUTH` (W19).

`kaizen.utils.credential_scrub` deliberately errs toward OVER-redaction: given
a choice between leaking a credential and destroying diagnostics, it destroys
diagnostics. This suite pins the boundary of that trade — the point past which
over-redaction stops being conservative and starts eating the error text the
surface exists to carry.

THE DEFECT. Both userinfo halves of `_URL_WITH_AUTH` (and of its overflow
companion `_URL_WITH_AUTH_OVERFLOW`) were `[^\\s]`-class and greedy, with
whitespace the ONLY terminator. A provider 4xx body is compact JSON with no
whitespace, so the entire body is one token: the match ran from the first
`scheme://` to the LAST `@` anywhere in the body. A response carrying a docs
link and a contact address collapsed the error message, the docs link, AND the
JSON delimiters into `https://[REDACTED]:[REDACTED]@example.com"}`.

TWO distinct losses, and the second is why this is a BUG and not a cosmetic
nit:
  1. Diagnosability — on `ProviderError.body_snippet`, whose entire purpose is
     to carry the provider's explanation of the failure.
  2. STRUCTURAL VALIDITY — the swallowed `}` unbalances the braces, so the
     snippet no longer parses as JSON. Any consumer that `json.loads` it gets a
     decode error rather than a degraded-but-readable body.

THE FIX excludes the JSON structural characters `"`, `{`, `}` and the JSON
escape `\\` from the userinfo classes of BOTH rules. That is sound rather than
arbitrary: RFC 3986 §3.2.1 gives
    userinfo = *( unreserved / pct-encoded / sub-delims / ":" )
and none of those four appear in any of those productions, so none can occur
unencoded in a well-formed userinfo. Excluding them stops the match at the JSON
field boundary while preserving the documented `@`-inside-userinfo coverage.

`,` is deliberately NOT excluded despite being a JSON structural character: it
IS a legal sub-delim, so excluding it would stop `user:pa,ss@host` matching and
leak a real password — an UNDER-redaction, the direction this module refuses to
trade for. `test_comma_password_still_redacted` is the teeth on that decision.

WHY BOTH PATTERNS. Fixing only `_URL_WITH_AUTH` left the defect fully intact:
the overflow companion's second run still crossed the JSON string boundary,
walking `…/docs/auth"},"contact"`, taking the `:` after `"contact"`, and
reaching the `@` of the contact address. The bounded rule went clean while the
observable behaviour did not change at all. `test_neither_pattern_matches_*`
pins both so a future edit cannot fix one and call the class closed.

CREDENTIAL-SHAPED VECTORS ARE ASSEMBLED AT RUNTIME FROM FRAGMENTS, never
written as literals. These are synthetic, but push protection matches on shape,
not provenance, and literal vectors have blocked pushes on this branch before.
"""

from __future__ import annotations

import json

import pytest

from kaizen.utils.credential_scrub import (
    _URL_WITH_AUTH,
    _URL_WITH_AUTH_OVERFLOW,
    _URL_WITH_USERINFO_ONLY,
    scrub_credentials,
)

# Assembled at runtime — see module docstring.
_AT = chr(64)


def _provider_4xx_body() -> str:
    """A compact-JSON provider error body: no whitespace, a URL, and a later `@`.

    This is the exact shape that broke: the docs link supplies the `scheme://`,
    the contact address supplies the terminating `@`, and the absence of
    whitespace means nothing between them stops a greedy `[^\\s]` run.
    """
    return (
        '{"error":{"code":"invalid_api_key",'
        '"message":"Incorrect API key provided",'
        '"doc":"https://platform.example.com/docs/auth"},'
        '"contact":"support' + _AT + 'example.com"}'
    )


class TestCompactJsonIsNotOverRedacted:
    """The credential-free compact-JSON body must survive scrubbing intact."""

    def test_body_passes_through_byte_identical(self) -> None:
        body = _provider_4xx_body()
        assert scrub_credentials(body) == body, (
            "A credential-FREE compact-JSON error body was modified by the "
            "scrubber. The greedy userinfo runs have re-crossed a JSON string "
            "boundary — see this module's docstring."
        )

    def test_scrubbed_body_still_parses_as_json(self) -> None:
        """Structural validity, not just substring survival.

        Asserting only that the message text survives would pass on a scrub
        that ate the trailing `}`. The parse is what catches that.
        """
        scrubbed = scrub_credentials(_provider_4xx_body())
        try:
            parsed = json.loads(scrubbed)
        except json.JSONDecodeError as exc:  # pragma: no cover - failure path
            pytest.fail(
                f"Scrubbed body no longer parses as JSON ({exc}). A consumer "
                f"that json.loads body_snippet now fails outright.\n"
                f"Scrubbed: {scrubbed!r}"
            )
        assert parsed["error"]["message"] == "Incorrect API key provided"
        assert parsed["error"]["doc"] == "https://platform.example.com/docs/auth"

    @pytest.mark.parametrize(
        "pattern,name",
        [
            (_URL_WITH_AUTH, "_URL_WITH_AUTH"),
            (_URL_WITH_AUTH_OVERFLOW, "_URL_WITH_AUTH_OVERFLOW"),
        ],
    )
    def test_neither_pattern_matches_credential_free_json(
        self, pattern, name: str
    ) -> None:
        """Pin BOTH rules independently.

        The first fix cleaned `_URL_WITH_AUTH` while the observable
        over-redaction was unchanged, because the overflow companion was still
        matching. A test that only checked scrub output would have gone green
        for the wrong reason had the rules been fixed in the other order.
        """
        assert not pattern.search(_provider_4xx_body()), (
            f"{name} matched a credential-free compact-JSON body; it will "
            f"collapse the error text and unbalance the JSON."
        )


class TestRealCredentialsStillRedacted:
    """The fix must not buy diagnosability with under-redaction."""

    @pytest.mark.parametrize(
        "label,dsn,secret",
        [
            (
                "plain dsn",
                "postgresql://svcuser:" + "s3cr3t" + _AT + "db.internal:5432/app",
                "s3cr3t",
            ),
            (
                # `,` is a legal RFC 3986 sub-delim. Excluding it from the
                # userinfo class would make this leak.
                "comma in password",
                "postgresql://svcuser:pa,ss" + _AT + "db.internal/app",
                "pa,ss",
            ),
            (
                # Documented coverage: a literal `@` inside the password.
                "at inside password",
                "postgresql://svcuser:p" + _AT + "ssw0rd" + _AT + "db.internal/app",
                "ssw0rd",
            ),
            (
                "email-shaped username",
                "https://ad" + _AT + "corp.example.com:pw123" + _AT + "host/x",
                "pw123",
            ),
            (
                # Longer than the 256-char DoS bound: exercises the overflow
                # companion, which this fix also edits.
                "overflow-length secret",
                "postgresql://svcuser:" + ("x" * 400) + _AT + "db.internal/app",
                "x" * 400,
            ),
            # The three below are the OVER-NARROWING probes. The first cut of
            # this fix excluded `"`, `{`, `}` AND `\` on the reasoning that all
            # four are RFC-illegal in userinfo so excluding all four was free.
            # It was not: these three passwords stopped matching and LEAKED IN
            # FULL, while `"` alone already fenced every compact-JSON case. The
            # exclusion set is now exactly `"`, and these pin it there.
            #
            # RFC-illegal is not the same as "cannot occur" — generated
            # passwords carry these bytes and lenient drivers accept them.
            (
                "open brace in password",
                "postgresql://svcuser:pa{ss" + _AT + "db.internal/app",
                "pa{ss",
            ),
            (
                "close brace in password",
                "postgresql://svcuser:pa}ss" + _AT + "db.internal/app",
                "pa}ss",
            ),
            (
                "backslash in password",
                "postgresql://svcuser:pa\\ss" + _AT + "db.internal/app",
                "pa\\ss",
            ),
        ],
    )
    def test_credential_is_redacted(self, label: str, dsn: str, secret: str) -> None:
        scrubbed = scrub_credentials(dsn)
        assert secret not in scrubbed, (
            f"[{label}] credential survived scrubbing — the JSON-structural "
            f"exclusions have narrowed the userinfo class too far.\n"
            f"Scrubbed: {scrubbed!r}"
        )
        assert "REDACTED" in scrubbed, (
            f"[{label}] no redaction marker present; the rule stopped matching "
            f"entirely rather than redacting.\nScrubbed: {scrubbed!r}"
        )

    def test_third_sibling_pattern_does_not_over_match_compact_json(self) -> None:
        """Enforcement-surface parity for `_URL_WITH_USERINFO_ONLY`.

        Two of the three sibling patterns gained the `"` exclusion. The third
        did NOT, and that asymmetry is the classic place an incomplete fix
        hides — so it is PROVEN safe here, not assumed.

        It is structurally fenced already: its userinfo class excludes `/` and
        `:`, so on `{"d":"https://docs.example.com","c":"me@me.com"}` the run
        stops at the first `/` of the path and never reaches the `@`.

        It DOES match `{"m":"https://token@y.com"}` — and that is correct, not a
        miss. `scheme://<token>@host` is the PAT-in-userinfo shape this rule
        exists to catch, and being inside a JSON value does not make it less of
        a credential. Only the token is replaced; the JSON survives.
        """
        for body in (
            '{"d":"https://docs.example.com","c":"me' + _AT + 'me.com"}',
            '{"m":"https://a.example.com/x/me' + _AT + 'y.com"}',
        ):
            assert not _URL_WITH_USERINFO_ONLY.search(body), (
                f"_URL_WITH_USERINFO_ONLY over-matched credential-free compact "
                f'JSON; it needs the `"` exclusion after all.\nBody: {body!r}'
            )

        # Positive control: the shape it MUST still claim.
        pat_url = "https://" + "ghp0abcdef1234567890" + _AT + "github.example.com/o/r"
        assert _URL_WITH_USERINFO_ONLY.search(
            pat_url
        ), "the bare-token-in-userinfo rule stopped matching its own shape"

    def test_same_string_value_over_redaction_is_an_accepted_residual(self) -> None:
        """Pin the KNOWN limit so it is not mistaken for a new regression.

        `"` fences the case provider bodies actually produce (URL in one JSON
        field, `@` in another). It does not fence a URL with a `:` in its path
        followed by an `@` in the SAME string value — that still over-redacts.

        Left deliberately: `scheme://<x>:<y>@<host>` IS the credential shape,
        and no regex separates it from a real DSN without parsing. Over-redaction
        is the safe side of this module's trade.

        This test exists to stop the next reader "fixing" it by widening the
        exclusion set — the exact error already made once here, which leaked
        every password containing `{`, `}` or `\\`.
        """
        body = '{"m":"https://a.example.com/p:q/me' + _AT + 'y.com"}'
        scrubbed = scrub_credentials(body)
        assert scrubbed != body, (
            "The same-string-value case stopped over-redacting. If that was "
            "achieved by EXCLUDING MORE CHARACTERS, revert it and re-run "
            "TestRealCredentialsStillRedacted — that is how the brace and "
            "backslash password leaks were introduced. If it was achieved by "
            "PARSING the candidate URL, that is the sound fix: delete this "
            "test and say so in the commit."
        )

    def test_credential_inside_compact_json_is_still_redacted(self) -> None:
        """The narrowing must not create a compact-JSON safe harbour.

        A DSN embedded in a JSON string value is the case where diagnosability
        and sensitivity actually collide — and sensitivity still wins.
        """
        body = (
            '{"error":"connection refused",'
            '"dsn":"postgresql://svcuser:' + "s3cr3t" + _AT + 'db.internal/app"}'
        )
        scrubbed = scrub_credentials(body)
        assert "s3cr3t" not in scrubbed, (
            f"A credential embedded in a compact-JSON value leaked.\n"
            f"Scrubbed: {scrubbed!r}"
        )
        assert "connection refused" in scrubbed, (
            "Redaction ate the sibling error text; it should stop at the JSON "
            f"field boundary.\nScrubbed: {scrubbed!r}"
        )
