# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2004 — untrusted spawn command leaked verbatim.

The defect
----------
``HealthChecker.check_server_health`` validates an untrusted ``server.command``
(sourced from a registry / discovery response) through ``validate_spawn_command``
and, on rejection, put ``str(e)`` into BOTH a log ``extra`` and the returned
dict. ``SpawnSecurityError`` embedded the raw command in its message AND in
``.data["command"]``, so a registry entry shaped like
``npx -y @vendor/server --token=<secret>`` leaked the credential.

Three sinks, not two
--------------------
The issue names two (the log ``extra`` and the returned ``error``). There is a
THIRD: ``MCPError.to_dict()`` copies ``self.data`` into the JSON-RPC error
payload, so ``.data["command"]`` reaches the wire. A fix applied at the three
call sites would have closed two sinks and left the wire sink open.

Why the fix is at the RAISE site
--------------------------------
The issue prescribes routing the sinks through the package's scrubbing helper
(``kailash.utils.url_credentials.mask_error_text``). That helper redacts URL
userinfo and credential query parameters; it does NOT redact a CLI-flag
credential, which is the shape this threat actually takes.
``test_prescribed_remedy_does_not_close_the_named_threat`` below measures that
directly rather than asserting it from a reading of the code.

So the fix stores a disclosure-safe reference (``basename#fingerprint``) at
construction time instead of scrubbing the raw command at each sink. A secret
that is never stored cannot leak from a sink that was forgotten, and
``SpawnSecurityError`` becomes structurally incapable of carrying the raw
command regardless of which call site raises it.

The enumeration used (issue AC #3)
----------------------------------
The sweep that originally closed this class matched only f-string-interpolated
log messages::

    logger\\.(error|warning|exception)\\(f?"[^"]*\\{(e|exc|error|...)[^}]*\\}

That pattern structurally cannot match ``extra={"error": str(e)}`` — a keyword
argument whose value binds the exception — nor can it match a ``return`` whose
dict binds one, nor ``to_dict()`` serialising ``.data``. The general instrument
is to enumerate every construction site that binds an exception object into a
dict or ``extra=`` block, including multi-line blocks, and additionally every
field the exception itself carries. Running the narrower pattern and reporting
the class closed was true of the pattern, not of the code.

These tests assert the invariant at the source (the exception never holds the
raw command) rather than at the sinks, so a NEW sink added later inherits the
protection without needing a fourth grep.
"""

from __future__ import annotations

import json
import logging

import pytest

# Clearly synthetic, non-realistic credential values. These must never appear
# in any rendered message, log record, exception payload, or wire dict.
SYNTHETIC_TOKEN = "SYNTHETIC-TOKEN-DO-NOT-LOG-AAA111"
CREDENTIAL_COMMAND = f"npx -y @vendor/mcp-server --token={SYNTHETIC_TOKEN}"


# ---------------------------------------------------------------------------
# 0. The prescribed remedy, measured against the named threat
#    (specification-verification.md MUST-2: test the remedy before adopting it)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_prescribed_remedy_does_not_close_the_named_threat():
    """``mask_error_text`` does not redact a CLI-flag credential.

    The issue prescribes routing the leaking sinks through this helper. It
    covers URL userinfo and credential query parameters — the two control
    cases below prove the helper ran and works on the shapes it does cover,
    so a pass-through on the CLI-flag shapes is a real gap and not a
    mis-invocation.

    If this test ever fails because ``mask_error_text`` gained CLI-flag
    coverage, that is an improvement: update this test. The raise-site fix
    remains the primary defense, because not storing a secret beats redacting
    it at every sink that might later be added.
    """
    from kailash.utils.url_credentials import mask_error_text

    # Controls — shapes the helper DOES cover. These discriminate: if the
    # helper were not running at all, these would leak too.
    assert "SYNTHETIC-URLPW" not in mask_error_text(
        "connect failed: postgres://user:SYNTHETIC-URLPW@host/db"
    )
    assert "SYNTHETIC-QP-DDD" not in mask_error_text(
        "GET https://host/x?api_key=SYNTHETIC-QP-DDD failed"
    )

    # The named threat — a CLI-flag credential. Passes through verbatim.
    leaked = mask_error_text(f"spawn command {CREDENTIAL_COMMAND!r} is not allowed")
    assert SYNTHETIC_TOKEN in leaked, (
        "mask_error_text unexpectedly redacted a CLI-flag credential; "
        "re-derive whether the raise-site fix is still the right shape"
    )
    for variant in (
        f"npx --api-key={SYNTHETIC_TOKEN}",
        f"npx --password {SYNTHETIC_TOKEN}",
        f"npx --token {SYNTHETIC_TOKEN}",
    ):
        assert SYNTHETIC_TOKEN in mask_error_text(variant)


# ---------------------------------------------------------------------------
# 1. The shared helper
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "command",
    [
        CREDENTIAL_COMMAND,
        f"npx --api-key={SYNTHETIC_TOKEN}",
        f"npx --password {SYNTHETIC_TOKEN}",
        f"/opt/vendor/bin/serve--token={SYNTHETIC_TOKEN}",
        f"../../bin/sh -c 'curl -H auth:{SYNTHETIC_TOKEN}'",
        f"user:{SYNTHETIC_TOKEN}@host",
        SYNTHETIC_TOKEN,
    ],
)
def test_safe_command_ref_never_echoes_the_command(command):
    """No input shape survives into the reference."""
    from kailash.utils.command_safety import safe_command_ref

    ref = safe_command_ref(command)
    assert SYNTHETIC_TOKEN not in ref
    # Nor any other whole-command echo.
    assert command not in ref


@pytest.mark.regression
def test_safe_command_ref_preserves_debuggability():
    """The reference stays useful: launcher basename plus a stable fingerprint."""
    from kailash.utils.command_safety import safe_command_ref

    ref = safe_command_ref(CREDENTIAL_COMMAND)
    assert ref.startswith("npx#"), ref
    # Stable across calls -> two log lines about the same command correlate.
    assert ref == safe_command_ref(CREDENTIAL_COMMAND)
    # Distinct commands do not collapse to the same reference.
    assert ref != safe_command_ref(f"npx -y @vendor/mcp-server --token=OTHER-{'B' * 8}")
    # A path-form launcher reduces to its basename.
    assert safe_command_ref("/usr/local/bin/python3").startswith("python3#")
    assert safe_command_ref("../../bin/sh").startswith("sh#")


@pytest.mark.regression
def test_safe_command_ref_redacts_an_unsafe_looking_launcher_token():
    """Fail closed: a first token that is not a plain launcher name is redacted."""
    from kailash.utils.command_safety import safe_command_ref

    assert safe_command_ref(f"--token={SYNTHETIC_TOKEN}").startswith("<redacted>#")
    assert safe_command_ref(f"user:{SYNTHETIC_TOKEN}@host").startswith("<redacted>#")


@pytest.mark.regression
def test_safe_command_ref_uses_distinct_sentinels_for_non_commands():
    """Empty / non-string inputs get distinguishable sentinels, never a crash."""
    from kailash.utils.command_safety import safe_command_ref

    assert safe_command_ref("") == "<empty>"
    assert safe_command_ref(None) == "<non-string>"
    assert safe_command_ref(["npx"]) == "<non-string>"


# ---------------------------------------------------------------------------
# 2. The raise site — all three sinks
# ---------------------------------------------------------------------------


def _raise_spawn_error(command: str):
    from kailash_mcp.security import SpawnSecurityError, validate_spawn_command

    with pytest.raises(SpawnSecurityError) as exc_info:
        validate_spawn_command(command)
    return exc_info.value


@pytest.mark.regression
def test_spawn_error_message_does_not_carry_the_raw_command():
    """Sink 1 of 3: the rendered message (what ``str(e)`` yields)."""
    err = _raise_spawn_error(CREDENTIAL_COMMAND)
    assert SYNTHETIC_TOKEN not in str(err)
    assert SYNTHETIC_TOKEN not in err.message


@pytest.mark.regression
def test_spawn_error_data_does_not_carry_the_raw_command():
    """Sink 2 of 3: the structured ``.data`` payload."""
    err = _raise_spawn_error(CREDENTIAL_COMMAND)
    assert SYNTHETIC_TOKEN not in json.dumps(err.data)
    assert "command" not in err.data, "the raw-command field must be gone, not masked"
    assert err.data["command_ref"].startswith("npx#")


@pytest.mark.regression
def test_spawn_error_to_dict_does_not_carry_the_raw_command():
    """Sink 3 of 3 — the one the issue misses: the JSON-RPC wire payload."""
    err = _raise_spawn_error(CREDENTIAL_COMMAND)
    assert SYNTHETIC_TOKEN not in json.dumps(err.to_dict())


@pytest.mark.regression
@pytest.mark.parametrize(
    "command",
    [
        CREDENTIAL_COMMAND,  # not in the allowlist
        f"../../bin/sh --token={SYNTHETIC_TOKEN}",  # path traversal branch
    ],
)
def test_every_raise_branch_is_covered(command):
    """Each rejection branch, not just the allowlist one, must be safe."""
    err = _raise_spawn_error(command)
    blob = json.dumps(err.to_dict()) + str(err)
    assert SYNTHETIC_TOKEN not in blob


@pytest.mark.regression
def test_spawn_error_remains_useful_for_debugging():
    """zero-tolerance Rule 3: the error must still say what happened and why."""
    err = _raise_spawn_error(CREDENTIAL_COMMAND)
    from kailash_mcp.errors import MCPErrorCode

    assert err.error_code == MCPErrorCode.AUTHORIZATION_FAILED
    assert "npx#" in str(err), "the correlatable reference must survive"
    assert "allowlist" in str(err)
    assert "allow_arbitrary" in str(err), "the remediation hint must survive"


# ---------------------------------------------------------------------------
# 3. The reported call site — discovery health check
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
async def test_health_check_leaks_nothing_to_log_or_return_value(caplog):
    """The reported site: neither the log record nor the returned dict leaks."""
    from kailash_mcp.discovery.discovery import HealthChecker, ServerInfo

    server = ServerInfo(
        name="vendor-mcp",
        transport="stdio",
        command=CREDENTIAL_COMMAND,
    )
    checker = HealthChecker()

    with caplog.at_level(logging.WARNING):
        result = await checker.check_server_health(server)

    assert result["status"] == "blocked"
    assert SYNTHETIC_TOKEN not in json.dumps(result)

    # Every attribute of every record, not just the formatted message —
    # the leak lived in `extra=`, which does not appear in record.message.
    for record in caplog.records:
        assert SYNTHETIC_TOKEN not in record.getMessage()
        for value in vars(record).values():
            assert SYNTHETIC_TOKEN not in str(value)


# ---------------------------------------------------------------------------
# 4. Sibling surface — the core stdio transport validator
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "command",
    [
        CREDENTIAL_COMMAND,
        f"../../bin/sh --token={SYNTHETIC_TOKEN}",
        "",
    ],
)
def test_core_stdio_validator_does_not_echo_the_command(command):
    """``security.md`` enforcement-surface parity: the core sibling validator.

    ``kailash.channels.mcp.stdio.validate_spawn_command`` is an independent
    implementation of the same fail-closed check with the same leak shape.
    Fixing only the packaged one would leave the identical defect reachable
    through the core stdio transport.
    """
    from kailash.channels.mcp.stdio import validate_spawn_command

    if not command:
        pytest.raises(Exception, validate_spawn_command, command)
        return

    with pytest.raises(Exception) as exc_info:
        validate_spawn_command(command)
    assert SYNTHETIC_TOKEN not in str(exc_info.value)
