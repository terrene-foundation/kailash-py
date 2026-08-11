# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: SecureLoggingHook leaks payload PROSE at INFO (#2070 sibling).

`SecureLoggingHook` (`hooks/security/redaction.py`) is a near-verbatim copy of
the pre-fix `LoggingHook` body — `Data={safe_context.data}` on the text path,
`log_event["context"] = safe_context.data` on the JSON path. It is public API
(exported from `hooks.security`).

SCOPE, stated precisely because it is narrower than the sibling defect. This
class DOES redact: `redact_sensitive` defaults True and the redactor is
constructed unconditionally, so credential shapes and PII patterns are removed.
What survives is everything the redactor does not claim — the user's prompt,
retrieved document text, free-form tool output. A class named
`SecureLoggingHook` publishing those at INFO is the same disclosure #2030
describes, reduced but not absent.

That is why the credential assertion below is a NEGATIVE control rather than
the finding: the credential is expected to be gone already, and a suite that
only checked credentials would report this class clean. The load-bearing
assertion is the PROSE one.
"""

from __future__ import annotations

import logging
import time

import pytest

from kaizen.core.autonomy.hooks.security.redaction import SecureLoggingHook
from kaizen.core.autonomy.hooks.types import HookContext, HookEvent

LOGGER_NAME = "kaizen.core.autonomy.hooks.security.redaction"

#: Credential-shaped: the redactor already claims this class today.
CREDENTIAL = "sk-live-SECUREHOOK2070SECRETVALUE"

#: Prose: matches no credential or PII pattern, so no redactor removes it.
#: This is the value the defect is actually about.
PROMPT = "draft the termination letter for the Henderson account"


def _context() -> HookContext:
    return HookContext(
        event_type=HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-secure-2070",
        timestamp=time.time(),
        data={"inputs": {"prompt": PROMPT, "api_key": CREDENTIAL}},
        metadata={"iteration": 1},
        trace_id="trace-secure-2070",
    )


def _rendered(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


class TestSecureLoggingHookWithholdsValues:
    @pytest.mark.asyncio
    async def test_user_prose_absent_from_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """THE FINDING. Redaction does not cover prose; only structure-only does."""
        hook = SecureLoggingHook()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await hook.handle(_context())

        assert PROMPT not in _rendered(caplog), (
            "SecureLoggingHook published the user's prompt text at INFO. The "
            "redactor claims credential shapes and PII patterns, neither of "
            "which matches prose, so redaction cannot close this — only "
            "declining to log values can."
        )

    @pytest.mark.asyncio
    async def test_credential_absent_from_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """NEGATIVE control — expected to pass BEFORE the fix as well.

        If this ever reddens, the redactor itself regressed, which is a
        different defect from the one this suite is about.
        """
        hook = SecureLoggingHook()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await hook.handle(_context())

        assert CREDENTIAL not in _rendered(caplog)

    @pytest.mark.asyncio
    async def test_structure_is_preserved(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """NEGATIVE control — deleting or blanket-masking the line cannot pass."""
        hook = SecureLoggingHook()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await hook.handle(_context())

        rendered = _rendered(caplog)
        assert rendered.strip(), "Hook emitted nothing at all; that is not a fix."
        for token in (
            "pre_agent_loop",
            "agent-secure-2070",
            "trace-secure-2070",
            "inputs",
        ):
            assert token in rendered, (
                f"{token!r} missing. Structure — event, agent, trace and "
                f"payload KEY names — must survive; only values are withheld."
            )

    @pytest.mark.asyncio
    async def test_full_payload_mode_is_opt_in_and_scrubbed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Positive polarity — values are reachable deliberately, and scrubbed.

        Without this the suite would be satisfied by a hook that can only ever
        stay quiet, which would be a regression in usefulness rather than a fix.
        """
        hook = SecureLoggingHook(log_full_payloads=True)
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            await hook.handle(_context())

        rendered = _rendered(caplog)
        assert rendered.strip(), "Full-payload mode emitted nothing."
        assert (
            CREDENTIAL not in rendered
        ), "Deliberate full-payload mode must still scrub credentials."
