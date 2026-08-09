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

import gc
import re
import time

import pytest
from kaizen.utils.credential_scrub import (
    _CREDENTIAL_KEY_NAMES,
    _CREDENTIAL_KEYVALUE_TOKEN,
    DEFAULT_PLACEHOLDER,
    scrub_credentials,
    scrub_local_error,
    scrub_remote_error,
)

#: `_CREDENTIAL_KEY_NAMES` is a pattern STRING (shared by the two key=value
#: rules so their vocabulary cannot drift); compiled here so the tests below
#: can assert against the key half in isolation.
_CREDENTIAL_KEY_NAME_RE = re.compile(_CREDENTIAL_KEY_NAMES, re.ASCII)

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
    # VOCABULARY GAP (F10). `secret_key` and `passphrase` were absent from
    # `_CREDENTIAL_KEY_NAMES`, so both leaked IN FULL on BOTH presets. See
    # `TestSecretKeyAndPassphraseAreNotCoveredByTheirPrefixes` for why the
    # already-present `secret` and `passwd|password|pwd` alternatives do NOT
    # cover them.
    pytest.param(
        "secret_key=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="secret_key"
    ),
    pytest.param(
        "secret-key=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="secret-key"
    ),
    pytest.param(
        "secretkey=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="secretkey"
    ),
    pytest.param(
        "passphrase=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="passphrase"
    ),
    # The key names are matched case-insensitively (`(?i:...)`), and an env-var
    # dump — the shape these two most often appear in — is UPPERCASE.
    pytest.param(
        "SECRET_KEY=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="secret_key-upper"
    ),
    pytest.param(
        "PASSPHRASE=abcdefghijklmnopqrst", "abcdefghijklmnopqrst", id="passphrase-upper"
    ),
    pytest.param(
        "'secret_key': 'abcdefghijklmnopqrst'",
        "abcdefghijklmnopqrst",
        id="secret_key-dict-repr",
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
class TestSecretKeyAndPassphraseAreNotCoveredByTheirPrefixes:
    """F10. WHY THE TWO NEW ALTERNATIVES ARE NOT REDUNDANT.

    `_CREDENTIAL_KEY_NAMES` already contained a bare `secret`, so
    `secret[-_]?key` LOOKS like a duplicate a future reader would delete as
    dead weight. It is not, and the reason is the key-name sub-pattern's
    MANDATORY TRAILING SEPARATOR: every alternative must be followed by
    `["']?\\s*[=:]`. On `secret_key=...` the `secret` alternative matches its
    six characters and then meets `_`, which is neither `=` nor `:`, so the
    whole key-name match FAILS — and it fails at every other offset too,
    because nothing in the alternation matches a bare `key`.

    Same mechanism for `passphrase`: `pass` is not an alternative, and
    `passwd` / `password` / `pwd` all diverge at the fifth character.

    These assert the MECHANISM against the compiled sub-pattern rather than
    only the end-to-end scrub, so that if a future edit makes the bare
    `secret` alternative genuinely subsume `secret_key` the redundancy becomes
    visible here instead of being argued about.
    """

    @pytest.mark.parametrize(
        "key",
        ["secret_key", "secret-key", "secretkey", "passphrase", "SECRET_KEY"],
    )
    def test_the_key_name_subpattern_claims_the_whole_key(self, key: str) -> None:
        match = _CREDENTIAL_KEY_NAME_RE.search(f"{key}=aB3xY9qq77zz12")
        assert match is not None, (
            f"the key-name sub-pattern does not match {key!r} at all, so "
            "nothing announces the value as a secret and it leaks under BOTH "
            "presets — this is the F10 gap"
        )
        assert match.group(0).lower().startswith(key.lower()), (
            f"the key-name match {match.group(0)!r} does not span the whole "
            f"key {key!r}; a partial key match means the alternation is "
            "claiming a suffix and the value boundary is not where it appears"
        )

    def test_the_bare_secret_alternative_alone_would_not_have_covered_it(self) -> None:
        """THE FALSIFYING CHECK for 'just use the existing `secret`'.

        Reconstructs the pre-F10 vocabulary and shows it returns NO MATCH.
        If a future edit makes this pass, the dedicated alternatives ARE
        redundant and this test says so out loud.
        """
        pre_f10 = re.compile(
            r"[\"']?(?i:passwd|password|pwd|secret|api[-_]?key|apikey|"
            r"access[-_]?token|refresh[-_]?token|id[-_]?token|"
            r"client[-_]?secret|auth[-_]?token|private[-_]?key|"
            r"session[-_]?key|encryption[-_]?key)[\"']?\s*[=:]\s*[\"']?",
            re.ASCII,
        )
        for key in ("secret_key", "secret-key", "secretkey", "passphrase"):
            assert pre_f10.search(f"{key}=aB3xY9qq77zz12") is None, (
                f"the PRE-F10 vocabulary already claimed {key!r}; if that is "
                "now true the new alternatives are redundant and should be "
                "removed rather than left as duplicated vocabulary"
            )

    @pytest.mark.parametrize(
        "text,secret",
        [
            ("secret_key=aB3xY9qq77zz12", "aB3xY9qq77zz12"),
            ("passphrase=aB3xY9qq77zz12", "aB3xY9qq77zz12"),
        ],
    )
    def test_conservative_preset_is_the_load_bearing_half(
        self, text: str, secret: str
    ) -> None:
        """Both keys must be claimed where the shape-only rules are OFF.

        A rule that only fired under the REMOTE preset would leave these on
        every one of the ~180 local-error sinks, which is the surface the gap
        was actually leaking on.
        """
        assert secret not in scrub_local_error(text)


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
            # F10 vocabulary gap: the two NEW key names must buy their coverage
            # at the SAME zero-false-positive cost as the rest of the family.
            # These are the prose shapes an agent reads to decide its retry —
            # the ~180-sink diagnosability cost the value lookahead exists to
            # avoid, now that two more keys can reach it.
            pytest.param("passphrase: unavailable", id="passphrase-prose"),
            pytest.param("secret_key: unavailable", id="secret-key-prose"),
            pytest.param("the passphrase argument is required", id="passphrase-word"),
            pytest.param(
                "invalid value for 'secret_key': expected string",
                id="secret-key-type-prose",
            ),
            pytest.param("passphrase=", id="passphrase-empty-value"),
        ],
    )
    def test_credential_free_text_is_unchanged(self, text: str) -> None:
        assert scrub_local_error(text) == text, (
            "a literal-anchored rule rewrote text carrying no credential; the "
            "conservative preset's whole contract is 'matches nothing but a "
            "real credential'"
        )


@pytest.mark.regression
class TestCommaBearingRunOverRedactsDeliberately:
    """R3-MED-5. The residual is a DECISION, and this is what pins it.

    `_COMMA_BEARING_RUN` consumes to the end of a comma-joined token, so a
    comma-separated field list following a credential key loses every field.
    That is documented at the rule as the deliberate safe trade — under-
    redaction leaks a live credential, over-redaction blanks recoverable prose
    — and the tests below exist so the next reader finds the trade ASSERTED
    rather than inferring it is a bug and "fixing" it into a leak.

    Two pre-existing bounds keep the blast radius narrow, and both are pinned
    here too. Widening the residual means breaking one of them, loudly.
    """

    def test_the_residual_is_real_and_is_the_documented_shape(self) -> None:
        """The over-redaction itself. Asserted, not merely described."""
        assert scrub_local_error("password=abc,user=bob,host=dblocal") == (
            DEFAULT_PLACEHOLDER
        ), (
            "the documented residual changed shape. If this is an intentional "
            "narrowing, check first that `password=ab,cdefghij` (a comma "
            "INSIDE the value) still redacts — that leak is what the rule "
            "exists to close, and it is the same string shape as this one"
        )

    def test_the_leak_the_residual_buys_is_still_closed(self) -> None:
        """CONTROL. The case that makes the residual unboundable.

        `ab,cdefghij` is a password containing a comma. It is structurally
        identical to a short value followed by a field list — which is why the
        run cannot be bounded without guessing, and why guessing wrong leaks.
        """
        assert "cdefghij" not in scrub_local_error("password=ab,cdefghij")

    def test_bound_1_alternation_order_stops_at_a_secret_shaped_value(self) -> None:
        """When the value IS secret-shaped, the earlier alternative claims it.

        So the residual can only reach a field list in the case where the rule
        genuinely cannot tell where the value ends.
        """
        assert (
            scrub_local_error("password=hunter2,user=bob,host=dblocal")
            == f"{DEFAULT_PLACEHOLDER},user=bob,host=dblocal"
        ), (
            "the first alternative no longer wins on a secret-shaped value; "
            "the residual's blast radius just grew from 'short/prose values' "
            "to 'every comma-separated field list after a credential key'"
        )

    def test_alternation_order_caps_the_failing_path(self) -> None:
        """Pins the 16-char boundary `_COMMA_BEARING_RUN`'s linearity rests on.

        When the comma group cannot match, the engine backtracks the leading
        `A+` — so how long `A+` can get IS the failing path's cost. It is capped
        at 15 because alternative 1's `{16,}` lookahead claims any comma-free
        run of 16 or more before this alternative is tried.

        Nothing in `_COMMA_BEARING_RUN` itself expresses that cap. An edit to
        alternative 1's lookahead would remove it while leaving the comma rule
        untouched, and the timing test would not notice — no mutation of the
        comma rule has been shown to red the ratio assertion. This asserts the
        boundary directly, from both sides.
        """
        # 15 chars, pure alpha: alternative 1's discriminators BOTH fail (no
        # digit or token punctuation, under 16), so the comma alternative is
        # reached — and fails, because there is no comma. Bounded exploration.
        assert _CREDENTIAL_KEYVALUE_TOKEN.search("password=" + "a" * 15) is None

        # 16 chars: alternative 1 claims it, so the comma alternative never
        # sees a run this long. THIS is the cap.
        claimed = _CREDENTIAL_KEYVALUE_TOKEN.search("password=" + "a" * 16)
        assert claimed is not None, (
            "alternative 1 no longer claims a 16-char comma-free value, so "
            "`_COMMA_BEARING_RUN`'s failing path is no longer length-capped — "
            "reason (c) at the pattern is now false and its linearity argument "
            "rests on one fewer leg"
        )
        assert "," not in claimed.group(0)

    def test_bound_2_a_space_after_the_comma_is_untouched(self) -> None:
        """The ordinary `key=value, key=value` spelling never matches."""
        for text in (
            "password=xyz, user=bob",
            "secret: unavailable, retrying",
            "invalid value for 'api_key': expected string, got None",
        ):
            assert scrub_local_error(text) == text, (
                "a comma-SPACE separated field list was rewritten; the run "
                "atom excludes whitespace precisely so the ~180 conservative-"
                "preset sinks an agent reads stay diagnosable"
            )


@pytest.mark.regression
class TestNewRulesAreLinear:
    """Module contract: any NEW pattern lands with a linearity test.

    Self-normalising 8x ratio per `rules/testing.md` § Complexity Bounds — an
    absolute wall-clock bound ratchets upward under CI load until it masks the
    regression it exists to catch.

    THREE SPLIT POINTS ARE COVERED HERE, one per rule that has landed:

    * `Basic` is followed by `\\s+` then a class that EXCLUDES whitespace.
    * the key=value rule's separator `[=:]` is excluded from the surrounding
      `\\s*` runs, and its value class excludes the quote characters the
      optional `["']?` can match.
    * `_COMMA_BEARING_RUN` (`A+(?:,+A+)+`) excludes `,` from the run atom `A`,
      so every character belongs to exactly one class and the boundary between
      run and separator cannot float.

    WHAT THE TIMING ASSERTION GUARDS FOR THE THIRD RULE, STATED BECAUSE IT IS
    NOT WHAT A READER WOULD ASSUME. For the URL rules the ratio is a DEMONSTRATED
    detector: remove the `{0,31}` scheme bound and the sibling suites read 64.6x
    and 69.2x. For `_COMMA_BEARING_RUN` it is not, and no mutation has yet made
    it one. Four were tried against this rule — the quadratic `{5,}` form this
    module's own comment names, `*`-not-`+`, a comma-inclusive (ambiguous) atom,
    and an alternative that never fires. None red the ratio; each was caught
    instead by the ENTRY or GUARD assertion.

    NO RATIO NUMBERS ARE QUOTED HERE, DELIBERATELY. An earlier revision cited a
    "7.5-8.3" range from probes that rebound the module NAME
    `_CREDENTIAL_KEYVALUE_TOKEN`. That patch is INERT: `_CREDENTIAL_PATTERNS`
    captured the compiled object at import, so `_CREDENTIAL_PATTERNS[18] IS` the
    old pattern and `scrub_credentials` never saw the mutant. The ratio sat near
    8 because nothing was mutated — a non-reddening result read as a property of
    the rule without proving the mutation reached the code
    (`rules/instrument-discipline.md` MUST-2(b), the exact failure it names).

    The four above are cited because their REACH IS ESTABLISHED: each rewrote
    the pattern in SOURCE and re-imported, and each changed observable behaviour
    while applied — the never-fires mutant reds the residual pins, the `{5,}`
    form reds the entry assertion. A mutation that changes no assertion is not
    evidence about the ratio; it is an unvalidated instrument.

    That is a property of the construct, not a blind test. This alternative has
    no mandatory element after its group, so a match succeeds as soon as the
    group matches once and the engine never exhausts a search; and its failing
    path is capped at 15 characters by alternative 1's `{16,}` lookahead. Both
    are recorded at the pattern, and the 16-char boundary reason (c) depends on
    is pinned by `test_alternation_order_caps_the_failing_path` below — an edit
    to alternative 1 would otherwise remove the cap without touching the rule
    this class is named for.

    So for this rule the ratio is a FORWARD tripwire: it fires if a future edit
    gives the alternative an exhaustible search (a mandatory tail, an uncapped
    failing path). Calling it a detector of a regression in the CURRENT
    construct would be the over-claim; it is retained because that future edit
    is exactly what the module contract exists to catch.

    THE UNITS BELOW WERE, FOR THE THIRD RULE, VACUOUS — AND THAT IS WHY THE
    ENTRY ASSERTION EXISTS. The shipped units were `"password=,"` and
    `"password:,"`, whose character immediately after the separator is a comma;
    `_COMMA_BEARING_RUN`'s leading atom EXCLUDES comma, so the alternative
    failed at its first character at every offset and the `(?:,+A+)+` group was
    never entered. Measured directly, the pattern's match on those payloads is
    `None` — so the timing assertion returned the same verdict whether the
    group was linear or quadratic. A check that cannot discriminate is not
    evidence (`rules/instrument-discipline.md` MUST-1).

    Each unit therefore declares `enters`, and `test_the_probe_reaches_the_rule`
    asserts it. The falsifying result is named and mechanical: for an
    `enters="comma-group"` unit, a match that is None or carries no comma means
    the payload never reached the construct and the timing number below it
    measures something else.
    """

    #: `unit` — the repeated payload. `enters` — the construct the payload is
    #: claimed to reach, checked by `test_the_probe_reaches_the_rule`.
    #: `matches` — whether `scrub` consumes the payload, which selects which
    #: guard the timing test applies (see that test). `scrub` — the preset the
    #: unit is measured under, and it is NOT uniform: the aggressive preset
    #: adds `_CREDENTIAL_KEYVALUE_PROSE`, whose unconstrained `{6,}` value class
    #: claims any 6-char value outright, so a unit probing the TOKEN rule's
    #: FAILING path is invisible there and must be measured where the prose
    #: rule is OFF. Declaring the preset per unit is what keeps the guard below
    #: honest instead of quietly measuring a different rule.
    _UNITS = [
        # Repeats the ANCHOR without ever completing a match — the shape that
        # would backtrack if the rule were ambiguous.
        pytest.param(
            "Basic ",
            "basic-anchor-run",
            "none",
            False,
            scrub_credentials,
            id="basic-anchor",
        ),
        # The original two units. RETAINED, not replaced: they still exercise
        # the key=value anchor's own split point, which is a real rule with a
        # real quantifier. What they never did is reach the comma group, and
        # `enters="none"` now says so out loud instead of implying coverage.
        pytest.param(
            "password=,",
            "keyvalue-anchor-run",
            "none",
            False,
            scrub_credentials,
            id="kv-eq",
        ),
        pytest.param(
            "password:,",
            "keyvalue-colon-run",
            "none",
            False,
            scrub_credentials,
            id="kv-colon",
        ),
        # F10 — the two NEW key-name alternatives, each repeated as a dense
        # anchor that never completes a match. Same construct and same
        # `enters="none"` claim as the two units directly above: the payload
        # exercises the key-name alternation's own split point (the mandatory
        # `[=:]` separator, excluded from the surrounding `\s*` runs) without
        # ever entering a value quantifier.
        #
        # `secret[-_]?key` is the only new alternative carrying a quantifier at
        # all, and it is a BOUNDED `[-_]?` over a two-character class, so it
        # adds O(1) work per start offset. The unit is here because the module
        # contract requires a landing linearity probe per new pattern, not
        # because the optional is suspected — and, per this class's own
        # docstring, it is a FORWARD tripwire: it fires if a future edit gives
        # the key half an exhaustible search.
        pytest.param(
            "secret_key=,",
            "secret-key-anchor-run",
            "none",
            False,
            scrub_credentials,
            id="kv-secret-key",
        ),
        pytest.param(
            "passphrase=,",
            "passphrase-anchor-run",
            "none",
            False,
            scrub_credentials,
            id="kv-passphrase",
        ),
        # NEW — actually enters `(?:,+A+)+`: `ab` then `,cd` then `,ef`. The
        # trailing space terminates the run so the anchor repeats rather than
        # one match swallowing the whole payload.
        pytest.param(
            "password=ab,cd,ef ",
            "comma-dense-run",
            "comma-group",
            True,
            scrub_credentials,
            id="comma-dense",
        ),
        # NEW — the FAILING path, which is the half that backtracks. The value
        # is comma-free and 6 chars, so the token rule's first alternative
        # fails its lookahead (pure-alpha, under 16) and control reaches
        # `_COMMA_BEARING_RUN`; its run atom matches `abcdef` and the
        # `(?:,+A+)+` group then finds no comma and fails. A quantifier that
        # only ever succeeds is measured by nothing: a successful greedy match
        # consumes the payload and `re.sub` resumes past it, so the scan never
        # revisits those characters.
        #
        # CONSERVATIVE preset, and that is load-bearing rather than incidental:
        # under the aggressive preset `_CREDENTIAL_KEYVALUE_PROSE` claims
        # `abcdef` on its own unconstrained alternative, the payload is
        # consumed before the failing path is reached, and the measurement
        # would be of the prose rule.
        pytest.param(
            "password=abcdef ",
            "comma-group-failing-path",
            "keyvalue-floor",
            False,
            scrub_local_error,
            id="comma-group-fails",
        ),
    ]

    @staticmethod
    def _ratio(scrub, small: str, large: str) -> float:
        """Cost of the 8x payload relative to the baseline, in CPU TIME.

        `time.process_time()`, NOT `time.perf_counter()`, and that is the whole
        point of this helper. The property under test is how much WORK the
        pattern does as the input grows; wall clock measures that PLUS every
        other process on the machine, and this repo's suites routinely run
        several at once. Measured on wall clock these three units read
        `[8.0, 8.1, 93.0]`, `[65.6, 49.4, 96.5]` and `[101.0, 7.9, 7.9]` across
        three consecutive runs of the SAME unmodified code; measured on CPU
        time they read `[8.1, 7.9, 8.1]`, `[7.9, 8.1, 8.0]` and
        `[8.1, 7.9, 8.1]` — linear, every time. `process_time` excludes the
        intervals this process was descheduled, which is exactly the noise.

        That flakiness is not cosmetic. A ratio test that fires at 93x on
        unchanged code trains the next reader to raise the bound, and
        `rules/testing.md` § Complexity Bounds names the threshold bump as the
        institutional tell for a buried complexity regression. The instrument
        had to become trustworthy rather than the bound become loose.

        Interleaving and the GC pause are kept as secondary defences: pairing
        each large sample with an adjacent small one keeps any residual drift
        common to both, and a collection landing inside the longer measurement
        would otherwise be indistinguishable from super-linear cost.

        Still self-normalising: no absolute threshold anywhere.
        """
        small_best = float("inf")
        large_best = float("inf")
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            for _ in range(5):
                start = time.process_time()
                scrub(small)
                small_best = min(small_best, time.process_time() - start)

                start = time.process_time()
                scrub(large)
                large_best = min(large_best, time.process_time() - start)
        finally:
            if gc_was_enabled:
                gc.enable()
        return large_best / max(small_best, 1e-9)

    # BOTH tests below declare the FULL five-name parameter set even though
    # each reads only a subset — `test_the_probe_reaches_the_rule` uses
    # `enters`, `test_anchor_dense_input_is_linear` uses `matches` and
    # `scrub`. That is pytest's contract, not dead code: a parametrized test
    # MUST accept every name in the `parametrize` tuple or collection fails
    # with "uses no argument". A checker reporting the unread ones as unused
    # is correct about the letter; dropping them breaks collection.
    @pytest.mark.parametrize("unit,label,enters,matches,scrub", _UNITS)
    def test_the_probe_reaches_the_rule(
        self, unit: str, label: str, enters: str, matches: bool, scrub
    ) -> None:
        """THE GUARD THE SHIPPED PROBE LACKED.

        Timing says nothing about a construct the payload never reaches. This
        asserts reach directly, against the compiled pattern, so a future unit
        that stops discriminating fails HERE — loudly, with the reason — rather
        than passing green forever as the two comma units did.
        """
        match = _CREDENTIAL_KEYVALUE_TOKEN.search(unit)

        if enters == "comma-group":
            assert match is not None, (
                f"[{label}] the key=value rule does not match this payload at "
                "all, so no quantifier in it is being measured"
            )
            assert "," in match.group(0), (
                f"[{label}] the match {match.group(0)!r} spans no comma, so "
                "`_COMMA_BEARING_RUN`'s `(?:,+A+)+` group was never entered — "
                "this is exactly the defect the shipped units had"
            )
        elif enters == "keyvalue-floor":
            assert match is None, (
                f"[{label}] this unit is the FAILING path: the value must "
                f"reach `_COMMA_BEARING_RUN` and fail, but it matched "
                f"{match.group(0)!r} — a succeeding quantifier never backtracks"
            )
        else:
            assert match is None, (
                f"[{label}] this unit is declared not to reach the key=value "
                f"value rule, yet it matched {match.group(0)!r}"
            )

    @pytest.mark.parametrize("unit,label,enters,matches,scrub", _UNITS)
    def test_anchor_dense_input_is_linear(
        self, unit: str, label: str, enters: str, matches: bool, scrub
    ) -> None:
        base_units = 500
        small = unit * base_units
        large = unit * (base_units * 8)

        # Guard the guard: a payload consumed by some OTHER rule would make the
        # timing assertion pass vacuously — it would be measuring that rule.
        # The two branches ask the same question of the two payload kinds.
        if matches:
            # A matching payload is not vacuous, but it must be the rule UNDER
            # TEST doing the consuming. Substituting with only that pattern
            # must reproduce the preset's output; if any other rule were
            # claiming the payload the two would differ.
            assert (
                _CREDENTIAL_KEYVALUE_TOKEN.sub(DEFAULT_PLACEHOLDER, small)
                == scrub(small)
                != small
            ), (
                f"[{label}] the payload is not being consumed by the key=value "
                "rule under test; the timing below would measure another "
                "pattern"
            )
        else:
            assert scrub(small) == small, (
                f"[{label}] the linearity payload is being consumed by a "
                "pattern before the new rules run; this test would pass "
                "vacuously"
            )

        ratio = self._ratio(scrub, small, large)

        assert ratio < 25, (
            f"[{label}] 8x input scaled {ratio:.1f}x (linear ~8x, quadratic "
            "~64x) — a new rule probably lost its deterministic split point"
        )
