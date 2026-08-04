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

Neither half asserts a credential is redacted; that is already covered by the
``test_issue_1974*`` suite. This file asserts ONLY the no-op question, because
that is the question the sweep decision turns on.
"""

from __future__ import annotations

import pytest

from kaizen.utils.credential_scrub import scrub_credentials

# ---------------------------------------------------------------------------
# Ordinary, credential-free text that MUST pass through untouched.
# ---------------------------------------------------------------------------
UNCHANGED = [
    pytest.param("connection refused", id="bare-message"),
    pytest.param("Request timed out after 30 seconds", id="timeout"),
    pytest.param("'model_name'", id="keyerror-repr"),
    pytest.param(
        "unsupported operand type(s) for +: 'int' and 'str'", id="typeerror"
    ),
    pytest.param(
        "invalid literal for int() with base 10: 'abc'", id="valueerror"
    ),
    pytest.param("Expecting value: line 1 column 1 (char 0)", id="json-decode"),
    pytest.param(
        "HTTP 429 Too Many Requests: rate limit exceeded, retry in 20s",
        id="http-status",
    ),
    pytest.param(
        "No module named 'kaizen_agents.patterns.missing'", id="import-error"
    ),
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
        assert vanishes not in scrubbed, (
            f"expected {vanishes!r} to be removed from the scrubbed output"
        )
        assert replacement in scrubbed, (
            f"expected {replacement!r} to appear in the scrubbed output"
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
