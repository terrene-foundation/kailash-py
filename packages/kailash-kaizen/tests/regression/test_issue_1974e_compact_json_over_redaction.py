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

THE FIX fences the JSON FIELD BOUNDARY, not a set of characters. Both runs use
a tempered token that halts only at a quote FOLLOWED BY a JSON structural
delimiter (`,` `}` `]` `:`). A quote in the middle of a value is ordinary
userinfo and is consumed.

It took three attempts to get there, and the two rejected ones are recorded
because each is a trap a future editor will re-enter:

  1. Exclude `"`, `{`, `}`, `\\` outright — "all four are RFC-3986-illegal in
     userinfo, so excluding them is free". NOT free: `pa{ss`, `pa}ss` and
     `pa\\ss` passwords stopped matching and LEAKED IN FULL. RFC-illegal is not
     the same as cannot-occur; generated passwords carry those bytes and lenient
     drivers accept them.
  2. Exclude `"` alone. Also leaked: a quote ANYWHERE in the userinfo killed the
     match for the WHOLE credential — a quote in the USERNAME leaked the
     PASSWORD, because the halted run could no longer reach the `:` or the `@`.

`,` is never excluded: it IS a legal sub-delim, so excluding it would leak
`user:pa,ss@host`.

THE METHODOLOGICAL LESSON, which is why the quote vectors below exist: attempt
1's leak was caught by probing the characters that had just been excluded.
Attempt 2's was not — because `"` was excluded in BOTH the rejected and the
accepted revision, so it never appeared as a DELTA. A character that SURVIVES a
narrowing is structurally invisible to a probe set derived from the diff. Probe
what the pattern CLAIMS, not what the patch CHANGED.

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
_Q = chr(34)


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
            # QUOTE VECTORS — the gap a differential probe cannot see.
            # The `{`/`}`/`\\` probes above were derived from "which chars did
            # we just exclude?". `"` was excluded in BOTH the rejected 4-char
            # revision AND the accepted 1-char one, so it never appeared as a
            # delta and no probe covered it — while it leaked exactly like the
            # other three. A character that SURVIVES a narrowing is structurally
            # invisible to a probe set built from the diff.
            #
            # Both halves matter: a quote in the USERNAME leaked the PASSWORD,
            # because the halted run could no longer reach the `:` or the `@`.
            (
                "quote in username",
                "postgresql://us" + _Q + "er:s3cr3t" + _AT + "db.internal/app",
                "s3cr3t",
            ),
            (
                "quote in password",
                "postgresql://svcuser:pa" + _Q + "ss" + _AT + "db.internal/app",
                "pa" + _Q + "ss",
            ),
            (
                # The JSON-native escaped form of the same shape.
                #
                # The needle is the FULL secret, not the 2-char tail it used to
                # be. A shorter needle is a STRICTER leak detector (anything
                # containing the whole secret contains the tail), so that was
                # not the weakness — but `ss` was matched against the WHOLE
                # scrubbed string, coupling the assertion to fixture bytes it
                # has nothing to do with. Rename the host to `db.class.internal`
                # or the placeholder to `[REDACTED-PASS]` and it reds with
                # "credential survived scrubbing" while nothing leaked. The
                # strict half is kept by the userinfo-span assertion below.
                "escaped quote in password",
                "postgresql://svcuser:pa\\" + _Q + "ss" + _AT + "db.internal/app",
                "pa\\" + _Q + "ss",
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
        # Userinfo span only — everything before the LAST `@`. Keeps the strict
        # substring check while removing the coupling to host/placeholder bytes
        # that produced misleading false positives.
        userinfo = scrubbed.rsplit(_AT, 1)[0]
        assert "REDACTED" in userinfo, (
            f"[{label}] no redaction marker in the userinfo span; the rule "
            f"stopped matching entirely rather than redacting.\n"
            f"Scrubbed: {scrubbed!r}"
        )
        assert secret not in scrubbed, (
            f"[{label}] credential survived scrubbing — the JSON-structural "
            f"exclusions have narrowed the userinfo class too far.\n"
            f"Scrubbed: {scrubbed!r}"
        )
        # NOTE: no separate `"REDACTED" in scrubbed` check — `userinfo` is a
        # PREFIX of `scrubbed`, so the assertion above strictly implies it. It
        # was retained briefly and read as a second independent check when it
        # was not; a redundant assertion that looks load-bearing is its own
        # small trap.

    @pytest.mark.parametrize(
        "label,body",
        [
            # KEYED transition — fenced by the `:` of `"c":`, even before the
            # tempered fence existed. These two were the ONLY vectors the
            # previous version of this test used, which is why it passed
            # regardless of the gap.
            ("keyed transition", '{"d":"https://docs.example.com","c":"me@me.com"}'),
            ("pathful url", '{"m":"https://a.example.com/x/me@y.com"}'),
            # ARRAY transitions — no key, therefore NO colon to fence on, and a
            # bare authority has no path either. Both were WIDE OPEN.
            (
                "sibling array element",
                '{"eps":["https://example.com","ops@example.com"]}',
            ),
            (
                "nested array element",
                '{"a":["https://example.com",["ops@example.com"]]}',
            ),
            ("object separator", '{"a":"https://example.com"},{"b":"ops@x.com"}'),
        ],
    )
    def test_userinfo_only_rule_does_not_cross_json_boundaries(
        self, label: str, body: str
    ) -> None:
        """`_URL_WITH_USERINFO_ONLY` must not cross a JSON field boundary.

        THIS TEST REPLACES ONE THAT COULD NOT FAIL. The previous version used
        only the first two vectors below, both fenced by the `:` in a
        `"<key>":` transition — so it passed whether or not the rule had a gap,
        and it was cited as proof that the rule "needs no change"
        (`instrument-discipline.md` MUST-1: name the falsifying result).

        The array vectors are the ones that discriminate: an array transition
        carries no key, hence no colon, and a bare authority carries no path.
        Against the un-fenced rule the last three FAIL — including
        `nested array element`, which produced UNPARSEABLE output.
        """
        assert not _URL_WITH_USERINFO_ONLY.search(body.replace("@", _AT)), (
            f"[{label}] the bare-token rule crossed a JSON field boundary; it "
            f"will redact across values and can unbalance the structure."
        )

    def test_userinfo_only_rule_still_claims_its_own_shape(self) -> None:
        """Positive controls, so the fence cannot pass by matching nothing.

        The second control is why this rule uses the tempered fence rather than
        a plain `"` exclusion: a plain exclusion fences the crossings but drops
        a bare token CONTAINING a quote — the under-redaction already made and
        reverted twice on the sibling rules.
        """
        pat = "https://" + "ghp0abcdef1234567890" + _AT + "github.example.com/o/r"
        assert _URL_WITH_USERINFO_ONLY.search(
            pat
        ), "the bare-token-in-userinfo rule stopped matching its own shape"
        quoted = "https://tok" + _Q + "en1234567890" + _AT + "github.example.com/o/r"
        assert _URL_WITH_USERINFO_ONLY.search(quoted), (
            "a bare token containing a quote is no longer claimed — that is the "
            "plain-exclusion under-redaction this rule uses a tempered fence to "
            "avoid"
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "F7 under-redaction residual: a userinfo containing a quote "
            'IMMEDIATELY followed by a JSON delimiter (`",` `"}` `"]` `":`) '
            "halts the tempered runs and leaks in full. Live on ALL THREE URL "
            "rules and in BOTH userinfo positions. This is F2's class narrowed, "
            "not closed, and it trades in the direction this module refuses. "
            "Deliberately NOT chased by tightening the lookahead — that swaps "
            "one aperture for a smaller one indefinitely; the sound route is a "
            "URL parse on the candidate span. strict=True so these XPASS the "
            "moment a parse lands and force the markers off, per testing.md "
            "§ Deferred-Implementation Conformance Vectors Use xfail-Strict, "
            "Not Skip."
        ),
    )
    @pytest.mark.parametrize("delim", [",", "}", "]", ":"])
    @pytest.mark.parametrize(
        "case,dsn_template,secret_template",
        [
            # --- BOUNDED rule, both positions -------------------------------
            (
                "AUTH/password",
                "postgresql://svcuser:pa{q}{d}ss@db.internal/app",
                "pa{q}{d}ss",
            ),
            (
                # The NASTIER half: a quote in the USERNAME halts the run before
                # it can reach the `:`, so the PASSWORD leaks — a secret the
                # username-holder may not even control, from the half more
                # likely to carry a human-typed address. The module comment
                # already records this asymmetry for the plain-`"` generation;
                # the tempered generation reproduces it in narrowed form.
                "AUTH/username",
                "postgresql://us{q}{d}er:s3cr3t@db.internal/app",
                "s3cr3t",
            ),
            # --- OVERFLOW rule, both positions ------------------------------
            #
            # HYPHENATED deliberately. An earlier version used `"x" * 300`,
            # which reads CLEAN — but only INCIDENTALLY: an unbroken 300-char
            # alphanumeric run is claimed by the 40-char contiguous-run rule in
            # _CREDENTIAL_PATTERNS, not by any URL rule. Hyphens break that run
            # (`-` is outside `[A-Za-z0-9/+]`), so the URL rule is genuinely the
            # only thing that could claim it.
            (
                "OVERFLOW/password",
                "postgresql://svcuser:" + ("a-" * 150) + "{q}{d}ss@db.internal/app",
                ("a-" * 150) + "{q}{d}ss",
            ),
            (
                "OVERFLOW/username",
                "postgresql://" + ("a-" * 150) + "{q}{d}u:s3cr3t@db.internal/app",
                "s3cr3t",
            ),
            # --- USERINFO-ONLY rule: a bare token, no `:` separator ----------
            (
                "USERINFO_ONLY/token",
                "https://" + ("a-" * 150) + "{q}{d}tok@github.example.com/o/r",
                ("a-" * 150) + "{q}{d}tok",
            ),
        ],
    )
    def test_quote_then_json_delimiter_in_userinfo_is_redacted(
        self, case: str, dsn_template: str, secret_template: str, delim: str
    ) -> None:
        """KNOWN-FAILING pin for the F7 residual: 3 rules x 2 positions.

        WHAT THIS PIN HOLDS CONSTANT IS THE POINT, and it took three passes to
        get right. v1 varied only the delimiter — one shape, one rule. v2 added
        the rule axis but held POSITION constant, always putting the pair in the
        password; the username position leaks too, and leaks the *other* half.
        Each time the uncovered axis was exactly where the next instance hid.

        That matters because these are `strict=True`: a partial fix flips the
        covered pins to XPASS, strict forces the markers off, and the class
        reads CLOSED while the uncovered axis still leaks with nothing on it.

        The SECRET is passed explicitly rather than sliced out of the DSN. A
        positional slice yields the whole userinfo (`svcuser:pa",ss`), and
        `secret not in output` is then satisfiable by a fix that redacts only
        the username while the password still leaks — green pin, live leak, at
        exactly the moment the pin is supposed to speak.
        """
        dsn = dsn_template.format(q=_Q, d=delim).replace("@", _AT)
        secret = secret_template.format(q=_Q, d=delim)
        rule = {
            "AUTH": _URL_WITH_AUTH,
            "OVERFLOW": _URL_WITH_AUTH_OVERFLOW,
            "USERINFO_ONLY": _URL_WITH_USERINFO_ONLY,
        }[case.split("/")[0]]

        # ATTRIBUTION ON THE PAIR-FREE CONTROL, NOT ON THE DEFECTIVE SHAPE.
        #
        # The previous guard asserted `rule.search(dsn)` — on the shape WITH the
        # fenced pair. That is the negation of the defect: these shapes leak
        # BECAUSE the fence stops the named rule claiming them. So the guard
        # failed first in all 20 cells and the leak assertion below was never
        # reached even once. Measured: 20/20 stopped at the guard, 0/20 reached
        # line `assert secret not in ...`, and because the guard reads a
        # COMPILED REGEX rather than scrub output, the grid behaved identically
        # against a no-op scrubber and a perfect one. Twenty cells carrying zero
        # information about redaction.
        #
        # Worse, the signal was INVERTED at fix time. The sound fix named in
        # credential_scrub.py is a URL PARSE on the candidate span, which leaves
        # these regexes unchanged — so the guard would have stayed False, the
        # pins would have stayed XFAIL forever, strict would never have fired,
        # and the residual would have read permanently OPEN after being closed.
        # Only the UNSOUND fix (widening the delimiter set, which that module
        # explicitly warns against) would have made the guard pass. The pin
        # spoke for the fix we rejected and was silent for the one we recommend.
        #
        # The control carries the attribution instead: same shape, quote NOT
        # followed by a delimiter. The named rule DOES claim it, which is what
        # establishes the rule owns this shape class — and that stays true after
        # either fix, so the guard cannot go inert again.
        control = dsn_template.format(q=_Q, d="x").replace("@", _AT)
        assert rule.search(control), (
            f"[{case}] attribution lost: {rule.pattern[:40]}... no longer claims "
            f"even the pair-free control, so this pin can no longer show the "
            f"named rule owns this shape class"
        )

        # NOT asserting exclusivity, deliberately. On the two short AUTH
        # controls BOTH _URL_WITH_AUTH and _URL_WITH_AUTH_OVERFLOW claim the
        # shape — the overflow rule is unbounded and is a structural superset
        # for short userinfo. Asserting `not OVERFLOW.search(control)` there
        # would be asserting something FALSE. So the guard proves shape-class
        # OWNERSHIP, not rule exclusivity, and says so rather than overstating.
        assert secret not in scrub_credentials(dsn)

    def test_markup_attribute_boundary_over_redacts_accepted(self) -> None:
        """L1 — pin the HTML/XML residual, which was documented but not tested.

        The fence models JSON. A markup attribute closes its quote with `>`,
        which is not in the delimiter set, so the run crosses and swallows the
        `">` — malforming the tag. ACCEPTED: over-redaction is the safe
        direction, and adding `>` would cost a password containing `">`, which
        is the under-redaction residual pinned above.

        THE BODY HAS NO COLON IN THE PATH, deliberately. An earlier version used
        `.../p:q">`, which made this test a DUPLICATE of the same-string-value
        residual below it: the colon let `_URL_WITH_AUTH` claim the body via
        THAT residual, so both assertions held even with the markup crossing
        removed entirely — it would have stayed green if the crossing were fixed
        tomorrow. Without the colon, `_URL_WITH_AUTH` does NOT claim it and
        `_URL_WITH_USERINFO_ONLY` does, which isolates the boundary crossing as
        the only thing under test.

        Asserted as CURRENT BEHAVIOUR, not xfail: unlike the `",` case this is
        not a defect awaiting a fix, so a strict xfail would wrongly imply
        someone should close it.
        """
        body = '<a href="https://docs.example.com">ops' + _AT + "example.com</a>"

        # Attribution guard, same purpose as the pins above: if the claim ever
        # migrates to another rule this fails rather than silently re-becoming a
        # duplicate of its neighbour.
        assert _URL_WITH_USERINFO_ONLY.search(body), (
            "the bare-token rule no longer claims this body, so the test is no "
            "longer isolating the markup boundary crossing"
        )
        for confound in (_URL_WITH_AUTH, _URL_WITH_AUTH_OVERFLOW):
            assert not confound.search(body), (
                f"{confound.pattern[:40]}... now claims this body — the test has "
                f"re-acquired the same-string-value confound it was rewritten to "
                f"remove, and is no longer isolating the markup crossing"
            )

        scrubbed = scrub_credentials(body)
        assert scrubbed != body, (
            "the markup boundary is no longer over-redacted. If that was "
            "achieved by adding `>` to the delimiter set, revert it and re-run "
            'the under-redaction pins — a password containing `">` now leaks. '
            "If it was achieved by a URL parse on the candidate span, that is "
            "the sound fix: delete this test and say so."
        )
        assert "[REDACTED]" in scrubbed

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
