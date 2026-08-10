"""Regression: RichOutputManager.show_error must not print raw credentials.

#1974c — surfaced by the #1720 forest redteam (R1 adversarial security pass).

`Agent._run` deliberately drops ``exc_info=True`` and logs
``sanitize_provider_error(e, ...)`` to avoid leaking the raw provider message
through the ``__cause__`` chain — and then handed the SAME raw exception to
``rich_output.show_error(e)``, which did ``str(error)`` straight into
``print()``. In containers, CI, and Nexus deployments stdout and the logger
land in the same aggregator, so the redaction bought nothing on that handler:
the credential was scrubbed on one surface and emitted verbatim on the other
line.

This is the sibling-surface failure `rules/security.md` § "Multi-Site Kwarg
Plumbing" names ("a sibling left unqualified ships the EXACT failure mode the
kwarg fixes") and `rules/observability.md` Rule 6.3 ("masking only the log
line is BLOCKED").

The fix scrubs at the SINK (``show_error``) rather than at the single caller,
so any future caller is covered by construction.

NOTE ON THE TEST VECTORS: they are assembled at runtime from fragments rather
than written as literals. The shapes are synthetic (repeating/sequential
filler), but a literal credential-shaped string in a committed blob trips
GitHub push protection and blocks the push — assembling them keeps the blob
clean while the runtime value still exercises the scrubber.
"""

from __future__ import annotations

import pytest

from kaizen.rich_output import RichOutputManager

# Assembled at runtime — see module docstring.
_SLACK_TAIL = "Zz" * 12
_SLACK_SECRET = "-".join(["xoxb", "9876543210", "9876543210", _SLACK_TAIL])
_STRIPE_SECRET = "_".join(["sk", "live", "9" + "AbCdEfGhIjKlMnOpQr"])


@pytest.mark.regression
def test_show_error_scrubs_credential_from_stdout(capsys):
    """A credential-shaped token in the exception must NOT reach stdout."""
    out = RichOutputManager(enabled=True)

    out.show_error(RuntimeError(f"provider rejected key {_SLACK_SECRET}"))

    printed = capsys.readouterr().out
    assert _SLACK_SECRET not in printed, (
        "raw credential reached stdout; show_error must scrub before printing "
        f"(got: {printed!r})"
    )
    assert (
        "[REDACTED]" in printed
    ), f"expected the node-surface redaction marker in output (got: {printed!r})"


@pytest.mark.regression
def test_show_error_scrubs_second_credential_shape(capsys):
    """Not shape-specific: a second vendor shape must scrub too.

    Guards against a fix that special-cases one pattern instead of routing
    through the shared scrubber.
    """
    out = RichOutputManager(enabled=True)

    out.show_error(ValueError(f"billing error for {_STRIPE_SECRET}"))

    printed = capsys.readouterr().out
    assert _STRIPE_SECRET not in printed
    assert "[REDACTED]" in printed


@pytest.mark.regression
def test_show_error_preserves_diagnosability(capsys):
    """The exception TYPE and benign text must survive the scrub.

    No-false-positive half: over-redaction that destroys the diagnostic value
    of the surface is its own defect, so a message with no credential in it
    must pass through unchanged.
    """
    out = RichOutputManager(enabled=True)

    out.show_error(TimeoutError("upstream timed out after 30s"))

    printed = capsys.readouterr().out
    assert "TimeoutError" in printed, "exception type must still be shown"
    assert (
        "upstream timed out after 30s" in printed
    ), f"benign message must not be over-redacted (got: {printed!r})"
    assert (
        "[REDACTED]" not in printed
    ), f"nothing to redact here; marker indicates over-redaction (got: {printed!r})"


@pytest.mark.regression
def test_show_error_disabled_prints_nothing(capsys):
    """The enabled=False short-circuit must still hold after the fix."""
    out = RichOutputManager(enabled=False)

    out.show_error(RuntimeError(f"key {_SLACK_SECRET}"))

    assert capsys.readouterr().out == ""
