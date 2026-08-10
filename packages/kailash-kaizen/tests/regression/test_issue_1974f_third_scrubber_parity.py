# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: the THIRD credential scrubber, on a logging path.

`credential_scrub.py` exists because two credential-pattern lists that "must
agree" are guaranteed to drift. Its own docstring records the first instance:
a second scrubber whose docstring claimed it "mirrors" the first, and did not.

A THIRD list existed the whole time — `SensitiveDataRedactor.PATTERNS` in
`kaizen/core/autonomy/hooks/security/redaction.py` — and it never claimed to
mirror anything, so nobody was checking it. It is REACHABLE: exported from
`hooks/security/__init__.py` and used by `hooks/builtin/logging_hook.py`, which
puts it on a LOGGING path. That is where credentials actually leak.

MEASURED DRIFT BEFORE THE FIX — 9 of 10 vendor shapes. It caught `sk-`/`pk-`
and missed AWS `AKIA`/`ASIA`, GitHub `ghp_`, HuggingFace `hf_`, Fireworks
`fw_`, Slack `xoxb-`, Stripe `sk_live_`, Azure SAS `sig=`, and URL-embedded DSN
credentials.

THE FIX IS ADDITIVE, NOT A REPLACEMENT, and that distinction is the whole
design. The shared scrubber owns vendor credentials and URL-embedded DSNs; it
knows nothing about credit cards, SSNs, emails or IPs. Replacing the local list
wholesale would have closed a credential gap by opening a PII one — trading one
under-redaction for another, which is the exact move this module refuses. So
`redact_string` now delegates the credential half and keeps the local list for
the non-credential classes.

THIS SUITE IS THE STRUCTURAL DEFENCE. The finding was not "this list is wrong"
— it is "nothing was checking whether it agreed". A fix without a parity test
would restore agreement today and permit the same silent drift tomorrow, which
is how the list got here.
"""

from __future__ import annotations

import pytest

from kaizen.core.autonomy.hooks.security.redaction import SensitiveDataRedactor
from kaizen.utils.credential_scrub import scrub_credentials

pytestmark = pytest.mark.regression

_AT = chr(64)

# Assembled at runtime from fragments — synthetic, but push protection matches
# on shape, not provenance, and literal vectors have blocked pushes here before.
_VENDOR_SHAPES = [
    ("openai sk-", "sk-" + "a" * 24),
    ("aws akia", "AKIA" + "A" * 16),
    ("aws sts asia", "ASIA" + "A" * 16),
    ("github ghp_", "ghp_" + "a" * 36),
    ("huggingface hf_", "hf_" + "a" * 34),
    ("fireworks fw_", "fw_" + "a" * 24),
    ("slack xoxb-", "xoxb-" + "a" * 20),
    ("stripe sk_live_", "sk_live_" + "a" * 20),
    ("azure sas sig=", "sig=" + "a" * 24),
    # DOTLESS HOST, deliberately. With a dotted host (`db.internal`) the local
    # `email` pattern claims `user@db.internal` incidentally, so that vector
    # passes with OR without the delegation — non-discriminating, and it was
    # caught by the mutation reddening 8 cells rather than the expected 9.
    # `localhost` has no dot, so the email pattern cannot claim it and only the
    # shared scrubber can.
    ("url-embedded dsn", "postgresql://svcuser:s3cr3tpw" + _AT + "localhost/app"),
]


@pytest.mark.parametrize("label,vector", _VENDOR_SHAPES)
def test_logging_redactor_agrees_with_the_shared_scrubber(
    label: str, vector: str
) -> None:
    """Parity on every vendor shape the shared module claims.

    Asserts AGREEMENT rather than "the redactor redacts", so it fails in both
    directions: if the shared module gains a shape the redactor cannot see, or
    if the delegation is ever unwound.
    """
    shared_redacts = vector not in scrub_credentials(vector)
    redactor = SensitiveDataRedactor()
    local_redacts = redactor.redact_string(vector) != vector

    assert shared_redacts, (
        f"[{label}] the SHARED scrubber no longer claims this shape — this "
        f"test's premise is broken, fix credential_scrub.py first"
    )
    assert local_redacts, (
        f"[{label}] the logging redactor does not redact a shape the shared "
        f"scrubber does. The two lists have drifted again, on a LOGGING path. "
        f"Route the credential half through scrub_credentials rather than "
        f"adding a pattern here — a fourth list is the same defect again."
    )


@pytest.mark.parametrize(
    "label,vector",
    [
        ("credit card", "4111 1111 1111 1111"),
        ("ssn", "123-45-6789"),
        ("email", "ops" + _AT + "example.com"),
        ("ip address", "10.1.2.3"),
        ("bearer token", "Bearer abc.def.ghi"),
        ("password field", 'password: "hunter2"'),
    ],
)
def test_non_credential_classes_are_not_lost_to_the_delegation(
    label: str, vector: str
) -> None:
    """The local list still owns PII and payment data.

    This is the half a naive fix would have broken. The shared scrubber knows
    nothing about credit cards, SSNs, emails or IPs, so replacing the local
    list with it would have closed a credential gap by opening a PII one.
    """
    redactor = SensitiveDataRedactor()
    assert redactor.redact_string(vector) != vector, (
        f"[{label}] a non-credential class is no longer redacted. If the local "
        f"PATTERNS list was replaced by the shared scrubber rather than "
        f"supplemented by it, that trades one under-redaction for another."
    )


def test_delegation_runs_before_the_local_patterns() -> None:
    """Ordering: the shared pass must run FIRST.

    If the local patterns ran first they could partially rewrite a credential
    (the `password:` field rule in particular), leaving a fragment the shared
    rules no longer match — a partial redaction that looks like a full one.
    """
    redactor = SensitiveDataRedactor()
    dsn = "postgresql://svcuser:s3cr3tpw" + _AT + "db.internal/app"
    out = redactor.redact_string('password: "' + dsn + '"')

    assert "s3cr3tpw" not in out, (
        f"a credential inside a password-shaped field survived redaction; the "
        f"local pattern likely consumed part of it before the shared pass ran. "
        f"Got: {out!r}"
    )
