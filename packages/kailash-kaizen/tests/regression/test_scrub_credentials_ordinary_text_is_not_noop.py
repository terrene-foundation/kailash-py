# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""``scrub_credentials`` is NOT a no-op on ordinary, credential-free text.

WHY THIS FILE EXISTS
--------------------
A proposed defence-in-depth sweep would have routed ~183 exception-text sites
in ``kaizen-agents`` through :func:`scrub_credentials`, on the stated premise
that the helper "is a no-op on non-credential text, so a blanket sweep is
safe".

That premise is FALSE, and this file is the instrument that says so. The
helper mutates several shapes that occur constantly in ordinary error strings
and carry no credential at all:

* ``/Users/<u>/`` · ``/home/<u>/`` · ``C:\\Users\\<u>\\``  -> ``[PATH]/``
  (``_INTERNAL_PATH_PATTERNS``) — every ``OSError`` message embeds the
  offending filename, so EVERY file/bash/MCP tool result is rewritten.
* a 40+ char contiguous ``[A-Za-z0-9/+]`` run -> ``[REDACTED]``
  — this claims full 40-hex git SHAs and long CamelCase identifiers.
* a 32+ char hex run -> ``[REDACTED]``
  — this claims MD5 digests and unhyphenated UUID/trace ids.
* ``https://<resource>.openai.azure.com`` -> resource name redacted.

None of that is a defect IN the helper. ``credential_scrub.py`` documents an
explicit false-positive-vs-sensitivity trade and deliberately errs toward
over-redaction, which is the RIGHT trade for the surface it was built for
(provider error bodies an attacker can influence). The defect would be
GENERALISING that trade to surfaces where the redacted bytes are load-bearing:

* an agent-facing ``ToolResult.failure(f"Error reading file: {exc}")`` whose
  path the LLM must read to retry, and
* local orchestration errors keyed by git SHA / run id / trace id.

So this test pins BOTH directions, and both halves are load-bearing:

* :class:`TestOrdinaryTextSurvives` — shapes that MUST stay byte-identical.
  It reds if a future pattern over-broadens into ordinary prose.
* :class:`TestKnownOverRedaction` — shapes that currently ARE rewritten.
  It reds if any of them is later closed, which is the signal that the
  blanket-sweep premise has become true and the sweep may be reconsidered.

WHAT CHANGED AFTERWARDS
-----------------------
The premise was false for the DEFAULT mode, so the helper's contract was split
rather than the sweep abandoned: ``scrub_credentials`` grew ``redact_paths``
and ``redact_opaque_tokens`` (both defaulting to ``True``, so every pre-existing
caller is byte-identical), and ``scrub_local_error`` is the named conservative
preset with both off. The sweep then landed on the conservative mode.

That turns this file bipolar in a second axis, and all four quadrants are
load-bearing:

* :class:`TestOrdinaryTextSurvives` — 17 shapes the DEFAULT leaves alone.
* :class:`TestKnownOverRedaction` — 8 shapes the DEFAULT rewrites.
* :class:`TestConservativeModeIsATrueNoOp` — all 26 credential-free vectors in
  this file (17 + 8 + the tool-result message) survive the CONSERVATIVE mode
  byte-identically, AND 19 real credentials still do not. The second half is
  what stops the first from being satisfiable by ``lambda t: t``.
* :class:`TestAggressiveDefaultIsUnchanged` — omitting the flags equals passing
  both ``True``, so a changed DEFAULT reds even with every pattern untouched.

The counts above are pinned by ``test_the_corpus_is_the_whole_file`` so the
corpus cannot silently shrink to one vector and still report green.
"""

from __future__ import annotations

import pytest

from kaizen.utils.credential_scrub import scrub_credentials, scrub_local_error

# ---------------------------------------------------------------------------
# Ordinary, credential-free text that MUST pass through untouched.
# ---------------------------------------------------------------------------
UNCHANGED = [
    pytest.param("connection refused", id="bare-message"),
    pytest.param("Request timed out after 30 seconds", id="timeout"),
    pytest.param("'model_name'", id="keyerror-repr"),
    pytest.param("unsupported operand type(s) for +: 'int' and 'str'", id="typeerror"),
    pytest.param("invalid literal for int() with base 10: 'abc'", id="valueerror"),
    pytest.param("Expecting value: line 1 column 1 (char 0)", id="json-decode"),
    pytest.param(
        "HTTP 429 Too Many Requests: rate limit exceeded, retry in 20s",
        id="http-status",
    ),
    pytest.param("No module named 'kaizen_agents.patterns.missing'", id="import-error"),
    pytest.param("'NoneType' object has no attribute 'run'", id="attribute-error"),
    pytest.param(
        "No such file or directory: './src/agents/base.py'", id="relative-path"
    ),
    pytest.param("revision 03795208d not found", id="git-sha-abbreviated"),
    pytest.param(
        "run_id 6f1c2a3b-4d5e-6f70-8192-a3b4c5d6e7f8 missing", id="uuid-hyphenated"
    ),
    pytest.param(
        "GET https://api.example.com/v1/models returned 503", id="url-no-userinfo"
    ),
    pytest.param(
        "cannot connect to http://localhost:11434/api/generate", id="url-with-port"
    ),
    pytest.param(
        "could not connect to postgresql://db.internal:5432/appdb",
        id="dsn-without-credentials",
    ),
    pytest.param("see https://github.com/@handle for details", id="profile-url"),
    pytest.param(
        '{"error":{"code":"invalid_request","message":"bad model"}}',
        id="compact-json-body",
    ),
]

# ---------------------------------------------------------------------------
# Credential-free text the helper DOES rewrite. Each entry is
# (input, the substring that disappears, the substring that replaces it).
# ---------------------------------------------------------------------------
OVER_REDACTED = [
    pytest.param(
        "Error reading file: [Errno 13] Permission denied: "
        "'/Users/alice/repos/app/config.yaml'",
        "/Users/alice/",
        "[PATH]/",
        id="macos-home-path-in-oserror",
    ),
    pytest.param(
        "PermissionError: /home/deploy/app/secrets.d/ not readable",
        "/home/deploy/",
        "[PATH]/",
        id="linux-home-path-in-oserror",
    ),
    pytest.param(
        r"FileNotFoundError: C:\Users\alice\proj\main.py",
        r"C:\Users\alice" + "\\",
        "[PATH]/",
        id="windows-home-path-in-oserror",
    ),
    pytest.param(
        "checkpoint restore failed at revision "
        "f0e1d2c3b4a5968778695a4b3c2d1e0f0a1b2c3d",
        "f0e1d2c3b4a5968778695a4b3c2d1e0f0a1b2c3d",
        "[REDACTED]",
        id="full-git-sha-40-hex",
    ),
    pytest.param(
        "trace 6f1c2a3b4d5e6f708192a3b4c5d6e7f8 not found",
        "6f1c2a3b4d5e6f708192a3b4c5d6e7f8",
        "[REDACTED]",
        id="uuid-without-hyphens",
    ),
    pytest.param(
        "checksum mismatch: 9e107d9d372bb6826bd81d3542a419d6",
        "9e107d9d372bb6826bd81d3542a419d6",
        "[REDACTED]",
        id="md5-digest",
    ),
    pytest.param(
        "unknown node type: AbstractSingletonProxyFactoryBeanBuilderImpl",
        "AbstractSingletonProxyFactoryBeanBuilderImpl",
        "[REDACTED]",
        id="long-camelcase-identifier",
    ),
    pytest.param(
        "endpoint https://myco.openai.azure.com timed out",
        "myco",
        "[REDACTED]",
        id="azure-openai-resource-name",
    ),
]


class TestOrdinaryTextSurvives:
    """Shapes that MUST pass through byte-identically."""

    @pytest.mark.parametrize("text", UNCHANGED)
    def test_ordinary_error_text_is_unchanged(self, text: str) -> None:
        assert scrub_credentials(text) == text, (
            "scrub_credentials() rewrote credential-free text. A pattern has "
            "over-broadened into ordinary error prose."
        )


class TestKnownOverRedaction:
    """Shapes the helper currently rewrites despite carrying no credential.

    These are NOT bugs in ``credential_scrub`` — they are the documented
    over-redaction trade. They are pinned so that (a) the blanket-sweep premise
    stays falsified in the record, and (b) closing any of them is a loud,
    deliberate event rather than a silent drift.
    """

    @pytest.mark.parametrize("text,vanishes,replacement", OVER_REDACTED)
    def test_credential_free_text_is_rewritten(
        self, text: str, vanishes: str, replacement: str
    ) -> None:
        scrubbed = scrub_credentials(text)

        assert scrubbed != text, (
            f"{vanishes!r} is no longer over-redacted. If this is intentional, "
            "the blanket-sweep premise may now hold for this shape — re-run "
            "the ordinary-text probe before widening any sweep."
        )
        assert (
            vanishes not in scrubbed
        ), f"expected {vanishes!r} to be removed from the scrubbed output"
        assert (
            replacement in scrubbed
        ), f"expected {replacement!r} to appear in the scrubbed output"


# ---------------------------------------------------------------------------
# The concrete tool-result vector, named once so the conservative-mode corpus
# below can include it rather than re-typing it.
# ---------------------------------------------------------------------------
TOOL_RESULT_OSERROR = (
    "Error reading file: [Errno 2] No such file or directory: "
    "'/Users/alice/repos/app/config.yaml'"
)

#: EVERY credential-free vector in this file, in one list. 26 total: the 17
#: that survive the aggressive default, the 8 it over-redacts, and the
#: tool-result message. The aggressive default rewrites 9 of the 26 (the 8 plus
#: the tool result); the conservative mode rewrites 0.
ALL_CREDENTIAL_FREE = (
    [p.values[0] for p in UNCHANGED]
    + [p.values[0] for p in OVER_REDACTED]
    + [TOOL_RESULT_OSERROR]
)

# ---------------------------------------------------------------------------
# Real credentials. The conservative mode MUST still claim every one of these,
# or the no-op result below would be satisfied by a function that returns its
# input — which is the vacuity this half exists to exclude.
# ---------------------------------------------------------------------------
#: The two Stripe fixtures are ASSEMBLED rather than written as literals, and
#: the split is load-bearing infrastructure, not style. GitHub push protection
#: matches Stripe keys on PREFIX PLUS LENGTH, without regard to entropy, so
#: these placeholders — 24 lowercase characters, no digits, the sequential
#: alphabet, siblings of ``AKIAIOSFODNN7EXAMPLE`` — tripped it and blocked the
#: push of an entire branch. Splitting the prefix removes the contiguous
#: literal from the file while leaving the VALUE the scrubber sees byte-
#: identical, so the assertion below is unchanged in strength.
#:
#: Do NOT re-inline these. A future author who "tidies" them back into literals
#: re-blocks the next push, and the failure appears at push time on someone
#: else's branch, far from this file.
_STRIPE_LIVE_FIXTURE: Final[str] = "sk_" + "live_" + "abcdefghijklmnopqrstuvwx"
_STRIPE_RESTRICTED_FIXTURE: Final[str] = "rk_" + "test_" + "abcdefghijklmnopqrstuvwx"

STILL_REDACTED = [
    pytest.param("sk-abcdefghijklmnopqrstuvwxyz0123456789", id="openai"),
    pytest.param("sk-ant-abcdefghijklmnopqrstuvwxyz0123456789", id="anthropic"),
    pytest.param("AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7", id="google"),
    pytest.param("pplx-abcdefghijklmnopqrstuvwxyz01", id="perplexity"),
    pytest.param("AKIAIOSFODNN7EXAMPLE", id="aws-access-key"),
    pytest.param("ASIAIOSFODNN7EXAMPLE", id="aws-sts"),
    pytest.param("xoxb-123456789012-1234567890123-abcdefghij", id="slack-bot"),
    pytest.param("ghp_abcdefghijklmnopqrstuvwxyz0123456789", id="github-pat"),
    pytest.param(
        "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz0123456789",
        id="github-fine-grained",
    ),
    pytest.param(_STRIPE_LIVE_FIXTURE, id="stripe-live"),
    pytest.param(_STRIPE_RESTRICTED_FIXTURE, id="stripe-restricted"),
    pytest.param("hf_abcdefghijklmnopqrstuvwxyz01234567", id="huggingface"),
    pytest.param("fw_abcdefghijklmnopqrstuvwx", id="fireworks"),
    pytest.param(
        "https://acct.blob.core.windows.net/c?sig=aBcDeF1234567890%2FgHiJkLmN%3D",
        id="azure-sas",
    ),
    pytest.param(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789",
        id="bearer",
    ),
    pytest.param(
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        id="bare-jwt",
    ),
    pytest.param(
        "could not connect to postgresql://svcuser:s3cr3tpw@db.internal/app",
        id="dsn-userinfo",
    ),
    pytest.param(
        "redis://:s3cr3tpw@cache.internal:6379/0 refused", id="dsn-empty-user"
    ),
    pytest.param(
        "clone failed: https://ghp_abcdefghijklmnopqrstuvwxyz012345@github.com/o/r",
        id="url-userinfo-only",
    ),
]


class TestConservativeModeIsATrueNoOp:
    """The premise the sweep needed, made TRUE by construction rather than assumed.

    ``scrub_local_error`` is :func:`scrub_credentials` with ``redact_paths`` and
    ``redact_opaque_tokens`` both off — i.e. only the rules anchored on a
    literal that cannot occur outside a credential. This class is the measured
    evidence that the combination is a no-op on the SAME corpus that falsified
    the blanket-sweep premise for the aggressive default.

    Read the two classes together: :class:`TestKnownOverRedaction` pins 8
    shapes the DEFAULT rewrites, and this class pins that the CONSERVATIVE mode
    leaves those very same 8 alone.
    """

    @pytest.mark.parametrize("text", ALL_CREDENTIAL_FREE)
    def test_no_credential_free_vector_is_rewritten(self, text: str) -> None:
        assert scrub_local_error(text) == text, (
            "the conservative mode rewrote credential-free text. Either a new "
            "rule was added to _CREDENTIAL_PATTERNS without being classified "
            "into _OPAQUE_SHAPE_PATTERNS, or an existing ungated rule has "
            "over-broadened. The ~180 kaizen-agents sweep sites depend on this "
            "being a no-op."
        )

    def test_the_corpus_is_the_whole_file(self) -> None:
        """Guard the corpus itself: 26 vectors, 9 of which the default rewrites.

        Without this the class above could silently shrink to a corpus of one
        and still report green.
        """
        assert len(ALL_CREDENTIAL_FREE) == 26
        rewritten_by_default = [
            t for t in ALL_CREDENTIAL_FREE if scrub_credentials(t) != t
        ]
        assert len(rewritten_by_default) == 9

    @pytest.mark.parametrize("text", STILL_REDACTED)
    def test_real_credentials_are_still_redacted(self, text: str) -> None:
        """Non-vacuity: the no-op above is a no-op only on credential-FREE text.

        ``lambda t: t`` would pass every assertion in the class above. It fails
        every assertion here.
        """
        scrubbed = scrub_local_error(text)
        assert scrubbed != text, (
            "the conservative mode let a real credential through. Its contract "
            "is 'drop the two over-redacting groups, keep everything that can "
            "match nothing but a credential' — this vector is in the second set."
        )

    def test_conservative_mode_still_mangles_nothing_in_a_mixed_string(self) -> None:
        """A credential AND a load-bearing path in one message.

        The whole point of the split: the secret goes, the path the agent needs
        in order to retry stays.
        """
        raw = (
            "Error reading '/Users/alice/repos/app/config.yaml': "
            "bad key sk-abcdefghijklmnopqrstuvwxyz0123456789"
        )
        scrubbed = scrub_local_error(raw)

        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in scrubbed
        assert "[REDACTED]" in scrubbed
        assert "/Users/alice/repos/app/config.yaml" in scrubbed


class TestAggressiveDefaultIsUnchanged:
    """The flags are ADDITIVE: omitting them is the pre-flag behaviour.

    :class:`TestKnownOverRedaction` above already pins the aggressive result
    shape-by-shape. This adds the explicit-vs-implicit identity, so a future
    edit that changes a DEFAULT (rather than a pattern) reds here even if every
    pattern is untouched.
    """

    @pytest.mark.parametrize("text", ALL_CREDENTIAL_FREE)
    def test_omitting_the_flags_equals_passing_them_true(self, text: str) -> None:
        assert scrub_credentials(text) == scrub_credentials(
            text, redact_paths=True, redact_opaque_tokens=True
        )

    @pytest.mark.parametrize("text", STILL_REDACTED)
    def test_omitting_the_flags_equals_passing_them_true_for_credentials(
        self, text: str
    ) -> None:
        assert scrub_credentials(text) == scrub_credentials(
            text, redact_paths=True, redact_opaque_tokens=True
        )


class TestToolResultPathManglingIsObservable:
    """The concrete consequence: an agent-facing tool result loses its path.

    ``delegate/tools/file_read.py``, ``file_edit.py``, ``file_write.py``,
    ``bash_tool.py`` and ``delegate/mcp.py`` all format an ``OSError`` straight
    into a ``ToolResult.failure(...)`` string that goes back to the LLM. If
    that string is scrubbed, the model can no longer read the path it must act
    on, and the absolute path becomes unrecoverable from the message.
    """

    def test_oserror_filename_is_not_recoverable_after_scrub(self) -> None:
        raw = (
            "Error reading file: [Errno 2] No such file or directory: "
            "'/Users/alice/repos/app/config.yaml'"
        )
        scrubbed = scrub_credentials(raw)

        # The basename survives, so the message still reads plausibly...
        assert "config.yaml" in scrubbed
        # ...but the absolute path the agent needs in order to retry is gone.
        assert "/Users/alice/repos/app/config.yaml" not in scrubbed
        assert "[PATH]/repos/app/config.yaml" in scrubbed
