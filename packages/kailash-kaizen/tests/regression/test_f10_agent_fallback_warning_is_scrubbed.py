# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""F10 Defect 3: the `kaizen.Agent` fallback WARN logged an unscrubbed traceback.

`kaizen/__init__.py::__getattr__` falls back to the sync `CoreAgent` when
`from kaizen_agents import Agent` raises, and logs a WARN with the traceback.
The traceback was retained on this rationale:

    no provider, DSN or caller-supplied code is reachable from an import
    statement

That is FALSE. An import statement executes the target module's top-level
code and, transitively, every module that imports — so an ImportError message
is whatever that code chose to put in it. This file is the mechanical check
for the CLAIM THAT REPLACED IT:

  1. the only caller-influenced channel in a rendered traceback is the
     exception MESSAGE (frame LOCALS are never rendered); and
  2. that message is scrubbed before it reaches a handler.

`test_the_unscrubbed_message_would_have_leaked` is the paired falsifier: it
shows the same payload surviving `exc_info=True`, so a green above cannot be
the payload having been harmless all along.
"""

from __future__ import annotations

import importlib.machinery
import logging
import sys
import traceback
import types

import kaizen
import pytest

pytestmark = pytest.mark.regression

#: A DSN whose password is the thing that must not survive. URL-userinfo is
#: claimed under BOTH presets, so this probes the wiring rather than the
#: aggressive-only shape rules.
_SECRET = "s3cr3tpasswordvalue"
_DSN = f"postgresql://svcuser:{_SECRET}@db.internal:5432/app"

#: A path shaped like the ones the AGGRESSIVE preset destroys (40+ contiguous
#: `[A-Za-z0-9/+]`). It must SURVIVE — the path is the whole diagnostic.
_DIAGNOSTIC_PATH = "/Users/ci/repos/kailash/build/kailashpy/src/kaizen/utils/x.py"


def _render(caplog: pytest.LogCaptureFixture) -> str:
    """Everything a handler would emit — MESSAGE **and** `exc_info`.

    Rendering only `getMessage()` is the trap this file exists to avoid, and
    it caught this very test first. `logger.warning(msg, exc_info=True)` does
    NOT put the traceback in the message: it hangs it off `record.exc_info`
    for the formatter to render. So a leak check reading only the message
    passes on the UNSCRUBBED `exc_info=True` code — vacuously, because it is
    looking somewhere the credential never was.

    Both channels are rendered here, so the check discriminates against both
    the old shape (traceback in `exc_info`) and the new one (scrubbed
    traceback interpolated into the message).
    """
    parts: list[str] = []
    for record in caplog.records:
        parts.append(record.getMessage())
        if record.exc_info:
            parts.append("".join(traceback.format_exception(*record.exc_info)))
    return "\n".join(parts)


# A static checker reports this function as "not accessed": pytest resolves
# fixtures by NAME through the test's parameter list, which is a binding the
# checker cannot connect to this definition. It IS used — by
# `test_the_fallback_warning_does_not_leak_the_import_error_credential` — and
# deleting it on the checker's word would empty that test.
@pytest.fixture
def _kaizen_agents_that_fails_to_import(monkeypatch: pytest.MonkeyPatch):
    """Make `from kaizen_agents import Agent` raise, carrying a credential.

    A module whose `__getattr__` raises is the faithful shape: the package
    imports fine (so `find_spec` is non-None and the WARN branch is the one
    taken), and the failure happens on the attribute — exactly the
    partially-initialized-module case the lazy resolution exists for.
    """
    module = types.ModuleType("kaizen_agents")

    # `_name` is unused BY DESIGN: PEP 562 calls a module `__getattr__` with
    # the attribute name, so the parameter is required by the protocol even
    # though this stub fails for every attribute. Underscore-prefixed to say
    # so rather than deleted, which would break the call.
    def _raise(_name: str):
        raise ImportError(f"backend unavailable: could not reach {_DSN}")

    module.__getattr__ = _raise  # type: ignore[method-assign]
    # A real `__spec__` is required, not cosmetic: the code under test gates
    # the WARN on `find_spec("kaizen_agents")`, and `find_spec` raises
    # `ValueError: __spec__ is None` for a module that is in `sys.modules`
    # without one — so the branch would never be reached.
    module.__spec__ = importlib.machinery.ModuleSpec("kaizen_agents", loader=None)
    monkeypatch.setitem(sys.modules, "kaizen_agents", module)

    # `Agent` is cached into module globals on first resolution, and
    # `__getattr__` only fires for MISSING attributes.
    monkeypatch.delitem(kaizen.__dict__, "Agent", raising=False)
    yield
    kaizen.__dict__.pop("Agent", None)


def test_the_fallback_warning_does_not_leak_the_import_error_credential(
    caplog: pytest.LogCaptureFixture, _kaizen_agents_that_fails_to_import: None
) -> None:
    """Claim 2: the message is scrubbed before it reaches a handler."""
    with caplog.at_level(logging.WARNING, logger="kaizen"):
        # `getattr`, NOT a direct `kaizen.__getattr__(...)` call: the fixture
        # deletes the cached `Agent`, so ordinary attribute lookup misses and
        # falls through to the PEP 562 hook — which is the path a real consumer
        # takes. Calling the dunder directly would reach the same code while
        # testing an access shape nobody uses.
        resolved = getattr(kaizen, "Agent")

    assert resolved is not None, "the fallback did not resolve an Agent at all"

    logged = _render(caplog)
    assert "falling back to the sync CoreAgent" in logged, (
        "the fallback WARN was not emitted, so this test asserts nothing "
        "about its content"
    )
    assert _DSN in logged or "[REDACTED]" in logged, (
        "the traceback is no longer being logged at all. That is a separate "
        "decision from scrubbing it — the import chain is the entire "
        "diagnostic for a broken dependency"
    )
    assert _SECRET not in logged, (
        "the DSN password from the ImportError message reached the log. The "
        "message is the caller-influenced channel in a traceback and must go "
        "through scrub_local_error()."
    )


def test_the_unscrubbed_message_would_have_leaked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """THE PAIRED FALSIFIER for the test above.

    Reproduces the PREVIOUS behaviour (`exc_info=True`, no scrub) on the same
    payload. If this ever stops leaking, the payload is not credential-shaped
    and the green above proves nothing about the scrub.
    """
    logger = logging.getLogger("kaizen.f10probe")
    with caplog.at_level(logging.WARNING, logger="kaizen.f10probe"):
        try:
            raise ImportError(f"backend unavailable: could not reach {_DSN}")
        except ImportError:
            logger.warning("fallback engaged", exc_info=True)

    rendered = _render(caplog)
    assert _SECRET in rendered, (
        "the payload no longer leaks even UNSCRUBBED, so the sibling test "
        "would pass whether or not the scrub is wired — it would no longer "
        "discriminate"
    )


def test_frame_locals_are_not_rendered_into_a_traceback() -> None:
    """Claim 1: the MESSAGE is the only caller-influenced channel.

    The rationale in `kaizen/__init__.py` rests on locals never being
    rendered — that is what bounds the scrub to `format_exc()`. If CPython
    ever starts including locals, the scrub is no longer sufficient and this
    reds.
    """

    def _raiser() -> None:
        # THE PAYLOAD, and it must be a live frame LOCAL at raise time — that
        # is the whole construct under test, so it is deliberately never
        # interpolated into the message. The `assert` below is what keeps the
        # binding read rather than dead: a checker flagging it "not accessed"
        # is right about the letter and wrong about the intent, and deleting
        # it would silently empty the test.
        credential_in_a_local = _SECRET
        assert credential_in_a_local, "the payload local must be truthy and live"
        raise ImportError("no operand echoed here")

    # `rendered` is bound ONLY in the except branch, so if `_raiser` ever stops
    # raising, the assertions below hit `UnboundLocalError`. Verified by
    # execution rather than reasoned about: a non-raising variant FAILS with
    # `UnboundLocalError: cannot access local variable 'rendered'` — it does
    # NOT pass vacuously. `else: pytest.fail(...)` is used anyway so the
    # failure names the cause instead of making the next reader decode an
    # UnboundLocalError, and so the binding is unconditional on every path
    # that reaches the assertions.
    try:
        _raiser()
    except ImportError:
        rendered = traceback.format_exc()
    else:
        pytest.fail(
            "the probe did not raise, so no traceback was rendered and the "
            "frame-locals claim below is untested"
        )

    assert "no operand echoed here" in rendered, "the probe did not capture it"
    assert _SECRET not in rendered, (
        "a frame LOCAL was rendered into the traceback. Scrubbing "
        "`format_exc()` still covers this, but the bound stated in "
        "`kaizen/__init__.py` — that only the message is caller-influenced — "
        "is no longer true and the rationale needs restating"
    )


def test_the_conservative_preset_keeps_the_diagnostic_path() -> None:
    """Why `scrub_local_error` and not `scrub_remote_error`, asserted.

    A POSIX path is 40+ contiguous `[A-Za-z0-9/+]`, which is exactly the
    shape-only rule the aggressive preset turns on. Keeping the credential out
    is worthless if it takes every file path with it.
    """
    from kaizen.utils.credential_scrub import scrub_local_error, scrub_remote_error

    payload = f'  File "{_DIAGNOSTIC_PATH}", line 9\nImportError: {_DSN}'

    conservative = scrub_local_error(payload)
    assert _SECRET not in conservative, "the conservative preset missed the DSN"
    assert _DIAGNOSTIC_PATH in conservative, (
        "the conservative preset blanked the file path — the traceback is "
        "retained precisely so the import chain stays readable"
    )

    assert _DIAGNOSTIC_PATH not in scrub_remote_error(payload), (
        "the aggressive preset no longer destroys this path, so the measured "
        "reason for choosing the conservative one is stale — recheck which "
        "preset this sink should use"
    )
