# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: LoggingHook payload disclosure + redaction-opt-in defeat (#2070).

Two defects, one file, both in `builtin/logging_hook.py`.

DEFECT 1 — full agent payloads at INFO, unredacted, by default. `include_data`
defaults True and `redact_sensitive` defaults False, and `agent_loop.py` feeds
this hook the whole agent I/O (`PRE_AGENT_LOOP` carries `{"inputs": ...}`,
`POST_AGENT_LOOP` carries `{"result": ...}`). Registering the hook therefore
put user prompts, retrieved documents and any credential-bearing parameter on
the INFO log. Same disclosure class as #2030, at a second surface.

DEFECT 2 — an explicitly-requested security control degraded to OFF. On
`ImportError` the constructor set `redact_sensitive = False` and continued
logging at full fidelity behind a WARNING. An operator who deliberately turned
redaction ON had it turned off for them. `zero-tolerance.md` Rule 3 +
`security.md` § Secure-Default.

WHY THE EXISTING SUITE DID NOT CATCH EITHER. `test_builtin_hooks.py` and
`test_structured_logging.py` construct `LoggingHook` a dozen times and assert
only `result.success is True` / `result.error is None`. Not one asserts on log
CONTENT — including `test_text_format_unchanged`, whose docstring says
"produces same output as before" while asserting nothing about output. Those
tests pass identically whether the payload is logged, redacted, or omitted, so
they carry no information about the property that was broken. Every assertion
below is on rendered log content for that reason.

ASYMMETRY PINNED BY TESTS 3 AND 4. An explicit opt-in that cannot be honoured
must RAISE (test 3). A default that cannot be honoured may degrade, but must
then also stop emitting the payloads redaction was protecting (test 4) —
degrading the control while continuing to log is the one outcome that must not
survive.

REACHABILITY, STATED BECAUSE IT BOUNDS THE CLAIM. `security/redaction.py`
imports only stdlib, `kaizen.utils.credential_scrub`, and sibling modules, so
its `ImportError` branch is not reachable through a normal install today.
Defect 2 is a live fail-OPEN DISPOSITION on an unreachable path, not a live
leak. Tests 3 and 4 therefore force a genuine `ImportError` through
`sys.modules` rather than asserting about the branch from a reading of it — the
import machinery really raises, and the constructor really takes the branch.
"""

from __future__ import annotations

import logging
import sys
import time

import pytest

from kaizen.core.autonomy.hooks.builtin.logging_hook import LoggingHook
from kaizen.core.autonomy.hooks.types import HookContext, HookEvent

REDACTION_MODULE = "kaizen.core.autonomy.hooks.security.redaction"
LOGGER_NAME = "kaizen.core.autonomy.hooks.builtin.logging_hook"

#: Credential-SHAPED so the redactor can recognise it. A value that no scrubber
#: claims to match would make a passing test unfalsifiable about redaction.
CREDENTIAL = "sk-live-LOGGINGHOOK2070SECRETVALUE"

#: Prose the user typed. NOT credential-shaped and NOT PII-shaped, so no
#: scrubber will remove it — it is here to prove the INFO line withholds VALUES
#: as such, not merely values a scrubber happens to recognise.
PROMPT = "summarize the acquisition memo for board review"


def _context() -> HookContext:
    """A PRE_AGENT_LOOP context shaped exactly as `agent_loop.py` builds it."""
    return HookContext(
        event_type=HookEvent.PRE_AGENT_LOOP,
        agent_id="agent-2070",
        timestamp=time.time(),
        data={"inputs": {"prompt": PROMPT, "api_key": CREDENTIAL}},
        metadata={"iteration": 1},
        trace_id="trace-2070",
    )


def _rendered(caplog: pytest.LogCaptureFixture) -> str:
    """Every captured record rendered as the handler would emit it."""
    return "\n".join(r.getMessage() for r in caplog.records)


class TestDefaultConstructionWithholdsValues:
    """DEFECT 1 — default construction must not put payload VALUES on INFO."""

    @pytest.mark.asyncio
    async def test_credential_absent_from_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        hook = LoggingHook()  # defaults only — the shape an operator gets free
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await hook.handle(_context())

        assert CREDENTIAL not in _rendered(caplog), (
            "A credential-shaped value in context.data reached the INFO log "
            "under DEFAULT construction. agent_loop feeds this hook whole "
            "agent inputs, so this is #2030's disclosure at a second surface."
        )

    @pytest.mark.asyncio
    async def test_user_prompt_absent_from_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Not scrubber-recognisable, so only withholding VALUES can pass this.

        Distinct from the credential assertion above: flipping
        `redact_sensitive` to True would satisfy that one while leaving every
        user prompt and retrieved document on the INFO log. This is the
        assertion that forces structure-only logging.
        """
        hook = LoggingHook()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await hook.handle(_context())

        assert PROMPT not in _rendered(caplog), (
            "The user's prompt text reached the INFO log under default "
            "construction. Redaction does not cover prose; only declining to "
            "log values does."
        )

    @pytest.mark.asyncio
    async def test_structure_is_preserved(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """NEGATIVE CONTROL — blanket-masking must not be able to pass.

        Without this, deleting the log call entirely, or masking the whole
        line, would satisfy every assertion above. The hook has to stay useful:
        the event, the agent, the trace and the payload's SHAPE all survive.
        """
        hook = LoggingHook()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            await hook.handle(_context())

        rendered = _rendered(caplog)
        assert rendered.strip(), "Hook emitted nothing at all; that is not a fix."
        for token in ("pre_agent_loop", "agent-2070", "trace-2070", "inputs"):
            assert token in rendered, (
                f"{token!r} missing from the INFO line. Structure — event, "
                f"agent, trace, and payload KEY names — must survive; only "
                f"values are withheld."
            )


class TestExplicitRedactionOptInFailsClosed:
    """DEFECT 2 — an explicit opt-in that cannot be honoured must RAISE."""

    def test_raises_when_redactor_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A genuine ImportError from the real import machinery, not a stand-in
        # for one: `None` in sys.modules makes the `from ... import ...` inside
        # the constructor raise for real, so the branch is really executed.
        monkeypatch.setitem(sys.modules, REDACTION_MODULE, None)

        with pytest.raises(RuntimeError, match="redact_sensitive"):
            LoggingHook(redact_sensitive=True)

    def test_error_names_the_protection_and_the_remedy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, REDACTION_MODULE, None)

        with pytest.raises(RuntimeError) as excinfo:
            LoggingHook(redact_sensitive=True)

        message = str(excinfo.value)
        assert "redaction" in message.lower(), "Error must name the OFF protection."
        assert "SensitiveDataRedactor" in message, "Error must name what failed."


class TestUnrequestedRedactionDegradesWithoutDisclosing:
    """DEFECT 2, other polarity — a DEFAULT may degrade, but must stop logging.

    The asymmetry is the whole point. Raising on a default nobody asked for
    would break installs where redaction is genuinely unavailable; continuing
    to log payloads after the control failed is the disclosure the control
    existed to prevent. Degrade, and stop emitting.
    """

    @pytest.mark.asyncio
    async def test_does_not_raise_and_still_withholds_values(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setitem(sys.modules, REDACTION_MODULE, None)

        hook = LoggingHook()  # redaction NOT explicitly requested
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            await hook.handle(_context())

        rendered = _rendered(caplog)
        assert CREDENTIAL not in rendered, (
            "Redaction degraded to OFF and the hook kept logging payloads. "
            "A degraded control must also stop emitting what it protected."
        )
        assert PROMPT not in rendered


class TestRedactionAppliedWhenAvailable:
    """Positive polarity — with the redactor present, it is actually used."""

    @pytest.mark.asyncio
    async def test_credential_redacted_in_full_payload_mode(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Opt in to everything: explicit redaction AND explicit full payloads.

        This is the configuration that emits values at all. It pins that the
        opt-in path is wired to a redactor that really runs — without it, the
        suite above would be satisfied by a hook that can only ever stay quiet.
        """
        hook = LoggingHook(redact_sensitive=True, log_full_payloads=True)
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            await hook.handle(_context())

        rendered = _rendered(caplog)
        assert rendered.strip(), "Full-payload mode emitted nothing."
        assert CREDENTIAL not in rendered, (
            "Explicit redaction was requested and the redactor was available, "
            "yet the credential survived into the log."
        )
