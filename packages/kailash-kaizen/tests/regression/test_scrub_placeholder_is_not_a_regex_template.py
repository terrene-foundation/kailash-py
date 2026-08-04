# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""A hostile ``placeholder`` MUST NOT be able to turn the scrubber into a no-op.

``re.sub``'s STRING replacement is a TEMPLATE: it expands ``\\1``, ``\\g<0>``
and ``\\g<name>``. Every substitution in `scrub_credentials` interpolated the
CALLER-SUPPLIED ``placeholder`` straight into that template, and the guard
rejected ``@``, ``://``, whitespace and the fence trigger — none of which is a
backslash. So a placeholder of ``\\g<0>`` replaced every matched credential
WITH ITSELF: a scrub that returns its own input while reporting success.

Reachable from public config, not hypothetical. `SensitiveDataRedactor`
forwards an operator-settable ``redaction_marker`` (``__init__`` /
``RedactionConfig``, documented with a ``redaction_marker="***"`` example) into
both the shared scrubber AND its own local ``PATTERNS`` loop — and that
redactor sits on a LOGGING path (`hooks/builtin/logging_hook.py`), which is
where credentials actually leak.

TWO INDEPENDENT DEFENCES, tested independently on purpose:

1. ``scrub_credentials`` rejects a backslash-bearing placeholder outright, so
   the failure is LOUD at the boundary rather than a silent no-op.
2. Every substitution passes a CALLABLE, whose return value ``re.sub`` uses
   LITERALLY with no expansion — so the placeholder is inert even where defence
   1 does not run.

Defence 2 is what the local ``PATTERNS`` loop actually relies on: its only
protection was that ``redact_string`` happens to call the shared scrubber
first, and a loop must not depend on the ordering of a call it does not own.
`TestLocalPatternLoopIsLiteralIndependentOfOrdering` neutralises the shared
call to test that loop's own defence, which is the only way to observe it.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from kaizen.core.autonomy.hooks.security import redaction as redaction_mod
from kaizen.core.autonomy.hooks.security.redaction import SensitiveDataRedactor
from kaizen.utils.credential_scrub import scrub_credentials

pytestmark = pytest.mark.regression

#: A real-shaped OpenAI key. Never a live credential — 26 letters + 6 digits.
_SECRET = "sk-abcdefghijklmnopqrstuvwxyz012345"

#: Replacement-template syntax. `\g<0>` expands to THE WHOLE MATCH, so as a
#: template it substitutes each credential with itself.
_WHOLE_MATCH_BACKREF = "\\g<0>"


class TestBackslashPlaceholderIsRejectedLoudly:
    """Defence 1 — the boundary guard."""

    @pytest.mark.parametrize(
        "hostile",
        [
            pytest.param("\\g<0>", id="whole-match-backref"),
            pytest.param("\\1", id="numeric-backref"),
            pytest.param("\\g<name>", id="named-backref"),
            pytest.param("x\\\\y", id="bare-backslash"),
        ],
    )
    def test_backslash_placeholder_raises(self, hostile: str) -> None:
        with pytest.raises(ValueError, match="backslash"):
            scrub_credentials(f"key={_SECRET}", placeholder=hostile)

    def test_rejection_happens_before_any_output_is_produced(self) -> None:
        """The failure must be a raise, NEVER a returned string.

        A returned value is the dangerous outcome: the caller logs it believing
        it scrubbed. Pre-fix this returned `key=<the secret>` verbatim.
        """
        try:
            result = scrub_credentials(
                f"key={_SECRET}", placeholder=_WHOLE_MATCH_BACKREF
            )
        except ValueError:
            return
        pytest.fail(
            "scrub_credentials RETURNED instead of raising for a "
            f"backreference placeholder, and the result was {result!r}; "
            f"secret present in output: {_SECRET in result}"
        )

    @pytest.mark.parametrize(
        "benign", ["[REDACTED]", "***", "[REDACTED-CRED]", "<hidden>"]
    )
    def test_benign_placeholders_still_accepted(self, benign: str) -> None:
        """CONTROL. A guard that rejected everything would pass the tests
        above while breaking every real caller."""
        out = scrub_credentials(f"key={_SECRET}", placeholder=benign)
        assert _SECRET not in out
        assert benign in out


class TestLocalPatternLoopIsLiteralIndependentOfOrdering:
    """Defence 2 — the callable, observed where the guard does not run.

    `redact_string` calls the shared scrubber first, which now raises on a
    backslash marker — so with the real wiring the local loop is never reached
    with a hostile marker. Neutralising that call is the ONLY way to observe
    whether the loop holds the property on its own. It must, because "the call
    before me happens to validate this" is not a defence the loop controls.
    """

    def test_local_loop_redacts_with_a_backreference_marker(self) -> None:
        ssn = "123-45-6789"
        redactor = SensitiveDataRedactor(redaction_marker=_WHOLE_MATCH_BACKREF)

        with patch.object(redaction_mod, "scrub_credentials", lambda t, **kw: t):
            out = redactor.redact_string(f"ssn={ssn}")

        assert ssn not in out, (
            "the local PATTERNS loop substituted the SSN with itself — the "
            "marker was expanded as a replacement TEMPLATE (\\g<0> = whole "
            f"match) rather than used literally; got {out!r}"
        )
        assert out == f"ssn={_WHOLE_MATCH_BACKREF}", (
            "the marker must appear LITERALLY in the output; anything else "
            "means re.sub is still interpreting it as syntax"
        )

    def test_local_loop_still_redacts_with_a_benign_marker(self) -> None:
        """CONTROL. The loop must keep working normally."""
        redactor = SensitiveDataRedactor(redaction_marker="***")
        with patch.object(redaction_mod, "scrub_credentials", lambda t, **kw: t):
            out = redactor.redact_string("ssn=123-45-6789")
        assert out == "ssn=***"


class TestScrubbingStillWorksEndToEnd:
    """CONTROL. The callable rewrite must not change any real behaviour."""

    def test_url_userinfo_scheme_prefix_is_preserved(self) -> None:
        """The two backreference-bearing replacements rebuilt `\\1` from
        `match.group(1)`; the scheme must survive exactly as before."""
        out = scrub_credentials("postgresql://svcuser:hunter2@db.internal/app")
        assert out.startswith(
            "postgresql://"
        ), f"scheme prefix lost in the callable rewrite: {out!r}"
        assert "svcuser" not in out and "hunter2" not in out

    def test_userinfo_only_form_preserves_scheme(self) -> None:
        out = scrub_credentials("https://ghp_aaaaaaaaaaaaaaaaaaaaaaaa@github.com/o/r")
        assert out.startswith("https://")
        assert "ghp_aaaaaaaaaaaaaaaaaaaaaaaa" not in out

    def test_azure_endpoint_resource_still_redacted(self) -> None:
        out = scrub_credentials("call to https://acme-prod.openai.azure.com failed")
        assert "acme-prod" not in out
        assert ".openai.azure.com" in out

    def test_redactor_full_path_with_default_marker(self) -> None:
        """The real wiring, unpatched, end to end."""
        redactor = SensitiveDataRedactor()
        out = redactor.redact_string(f"key={_SECRET} ssn=123-45-6789")
        assert _SECRET not in out
        assert "123-45-6789" not in out
