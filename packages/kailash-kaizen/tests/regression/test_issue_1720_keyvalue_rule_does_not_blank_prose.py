"""The credential ``key=value`` rule must not blank ordinary diagnostic prose.

The rule is anchored on a key name that ANNOUNCES a secret (``password=``,
``api_key:``, ``client_secret=``). Its first revision constrained the KEY but
not the VALUE -- ``[^\\s"',;&]{6,}`` matches any 6+ run that is not whitespace
or a delimiter, which includes ordinary English words. So a message that merely
MENTIONS one of those key names had its text destroyed:

    invalid value for 'api_key': expected string  ->  invalid value for [REDACTED] string
    secret: unavailable                           ->  [REDACTED]
    api_key: Optional[str]                        ->  [REDACTED]

That matters because this rule is ON under the CONSERVATIVE preset, which is
what ~180 kaizen-agents sinks use, and those sinks feed ``ToolResult`` text an
AGENT reads to decide its retry. Blanking a validation error's type information
is exactly the diagnosability cost ``redact_opaque_tokens=False`` exists to
avoid -- the conservative preset's whole contract is "matches nothing but a
real credential".

The fix splits the rule by aggression rather than loosening it:

  * ``_CREDENTIAL_KEYVALUE_TOKEN`` -- value must LOOK like a secret (contains a
    digit / token punctuation, OR is >=16 chars). Runs under BOTH presets.
  * ``_CREDENTIAL_KEYVALUE_PROSE`` -- the original unconstrained form, retained
    for short pure-alphabetic secrets, classified into
    ``_OPAQUE_SHAPE_PATTERNS`` so it is AGGRESSIVE-ONLY.

Both halves are asserted here. A fix that only widened the value class would
pass the prose half and fail the secret half; one that only tightened it would
do the reverse. Neither half alone is the property.
"""

from __future__ import annotations

import pytest

from kaizen.utils.credential_scrub import scrub_credentials, scrub_local_error

# Ordinary diagnostics that MENTION a credential key name but carry no secret.
# Each is a message shape an agent actually receives from a failing tool call.
_PROSE_CASES = [
    pytest.param(
        "invalid value for 'api_key': expected string",
        "expected string",
        id="validation-error-keeps-its-type-info",
    ),
    pytest.param("secret: unavailable", "unavailable", id="short-status-word"),
    pytest.param("api_key: Optional[str]", "Optional[str]", id="type-annotation-echo"),
    pytest.param(
        "password= is required but missing",
        "required",
        id="empty-value-then-prose",
    ),
]

# Real credentials that MUST still be redacted under the CONSERVATIVE preset.
# Assembled from fragments so the file carries no scannable secret literal.
_SECRET_CASES = [
    pytest.param("password=" + "hunter2" + "longenough", id="digit-bearing"),
    pytest.param("api_key=" + "abcdefghij" + "klmnopqrst", id="pure-alpha-20char"),
    pytest.param("client_secret: " + "aB3-xY9" + "_qq77", id="token-punctuation"),
    pytest.param(
        "Authorization: Basic " + "dXNlcjpwYXNz" + "d29yZA==", id="basic-auth"
    ),
]


class TestConservativePresetKeepsDiagnosticProse:
    """The half that regressed: prose must survive the conservative preset."""

    @pytest.mark.parametrize("text,must_survive", _PROSE_CASES)
    def test_prose_is_not_blanked(self, text: str, must_survive: str) -> None:
        out = scrub_local_error(text)
        assert must_survive in out, (
            f"scrub_local_error() destroyed diagnostic prose: {text!r} -> {out!r}. "
            f"The value {must_survive!r} carries no credential -- the key name is "
            f"merely MENTIONED. An agent reads this text to decide its retry."
        )
        assert (
            out == text
        ), f"scrub_local_error() modified credential-free text: {text!r} -> {out!r}"


class TestConservativePresetStillRedactsRealSecrets:
    """The control: tightening the value class must not open a credential gap.

    Without this half, deleting the rule outright would pass the prose tests.
    """

    @pytest.mark.parametrize("text", _SECRET_CASES)
    def test_secret_is_redacted(self, text: str) -> None:
        out = scrub_local_error(text)
        assert out != text, (
            f"scrub_local_error() left a credential-announcing value intact: "
            f"{text!r}. The key names it a secret and the value is secret-shaped."
        )
        # The secret is the run after the separator; none of it may survive.
        secret = text.split("=", 1)[-1].split(": ", 1)[-1].strip()
        assert secret not in out, f"secret survived: {text!r} -> {out!r}"


class TestAggressivePresetStillCatchesPureAlphaProse:
    """The prose-matching half is retained, just confined to aggressive mode.

    A short pure-alphabetic secret is real but indistinguishable from a word,
    so it is redacted on the provider-error surface (where over-redaction is
    the documented trade) and not on the agent-facing one.
    """

    def test_short_pure_alpha_secret_redacted_under_aggressive(self) -> None:
        text = "password=" + "hunter" + "password"
        assert scrub_credentials(text) != text, (
            "the aggressive preset must still claim a short pure-alphabetic "
            "secret; that is why _CREDENTIAL_KEYVALUE_PROSE was retained"
        )

    def test_and_that_same_shape_is_left_alone_under_conservative(self) -> None:
        # Pins the deliberate asymmetry, so a future edit that promotes the
        # prose rule to both presets reds here instead of silently
        # re-introducing the blanking regression.
        text = "secret: unavailable"
        assert scrub_local_error(text) == text
        assert scrub_credentials(text) != text
