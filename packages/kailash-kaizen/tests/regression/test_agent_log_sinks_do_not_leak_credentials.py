# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""The agent logging mixin and both audit forwards must not log credentials.

``LoggingMixin`` wraps EVERY agent's ``run``, so whatever an agent raises
arrives at its failure sink: an LLM provider auth error naming the endpoint it
could not authenticate against, a DB driver error carrying a DSN, a tool's own
exception. It was leaking on THREE surfaces simultaneously::

    agent._agent_logger.error(
        f"Execution failed [{execution_id}] ... : {error}",   # 1. message
        extra={..., "error_message": str(error), ...},        # 2. structured field
        exc_info=True,                                        # 3. traceback
    )

Surface 3 is the one a message-only test cannot see: ``logging`` renders
``exc_info`` by walking the exception chain, so a ``raise Wrapper(...) from
provider_error`` prints the RAW cause under "the above exception was the direct
cause of..." -- verbatim, after any scrub applied to surfaces 1 and 2. Every
assertion below is therefore on the FULLY RENDERED record.

The two audit forwards (``kaizen/security/audit.py`` and
``kaizen/core/autonomy/observability/audit.py``) had clean messages but the same
``exc_info`` over a WRITE to the canonical store, whose driver errors embed the
store's DSN. An audit sink is the worst place to leave that: it is the one
surface whose purpose is to be retained, shipped and read widely.

Sentinels are synthetic -- RFC 2606 ``.invalid`` hosts, self-describing values.
They carry the SHAPE the scrubber keys on so they exercise the same branch a
real credential would.
"""

from __future__ import annotations

import logging

import pytest

pytestmark = pytest.mark.regression

_SENTINEL = "SYNTHETIC-NOT-A-REAL-CREDENTIAL-mixin"
_LEAKY_DSN = f"postgresql://svc:{_SENTINEL}@db.example.invalid:5432/prod"


def _chained_exception() -> Exception:
    """A wrapper whose ``__cause__`` carries the credential.

    ``str(wrapper)`` is clean, so a scrub applied to the message looks
    sufficient while the rendered traceback prints the cause in full. This is
    the shape that defeats a message-only assertion.
    """
    try:
        try:
            raise ConnectionError(f"could not connect: {_LEAKY_DSN}")
        except ConnectionError as inner:
            raise RuntimeError("agent step failed") from inner
    except RuntimeError as wrapper:
        return wrapper


class _RenderingCapture(logging.Handler):
    """Captures the rendered record -- the only view that resolves exc_info."""

    def __init__(self) -> None:
        super().__init__()
        self.rendered: list[str] = []
        self._fmt = logging.Formatter("%(levelname)s %(message)s")

    def emit(self, record: logging.LogRecord) -> None:
        extras = " ".join(
            f"{k}={v!r}"
            for k, v in vars(record).items()
            if k not in logging.LogRecord("", 0, "", 0, "", None, None).__dict__
        )
        self.rendered.append(f"{self._fmt.format(record)} {extras}")

    @property
    def text(self) -> str:
        return "\n".join(self.rendered)


@pytest.fixture
def capture():
    """Root handler, so every module under test is covered by one fixture."""
    handler = _RenderingCapture()
    root = logging.getLogger()
    prior = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(prior)


class TestTheLeakVectorItself:
    """The falsifying control for this whole file.

    Demonstrates the instrument CAN distinguish leaked from scrubbed. If this
    ever goes green with ``exc_info=True``, ``logging`` changed its
    chain-rendering and every drop in this shard must be re-justified rather
    than assumed still-necessary.
    """

    def test_exc_info_renders_the_chained_cause_verbatim(self, capture):
        from kaizen.utils.credential_scrub import scrub_remote_error

        exc = _chained_exception()
        scrubbed = scrub_remote_error(exc)
        assert _SENTINEL not in scrubbed, "the scrub itself is not the problem"

        logging.getLogger("probe.leak").error(
            "failed: %s", scrubbed, exc_info=(type(exc), exc, exc.__traceback__)
        )
        assert _SENTINEL in capture.text, (
            "exc_info no longer renders the chained cause; the premise of this "
            "regression has changed."
        )

    def test_without_exc_info_the_same_call_is_clean(self, capture):
        from kaizen.utils.credential_scrub import scrub_remote_error

        exc = _chained_exception()
        logging.getLogger("probe.clean").error("failed: %s", scrub_remote_error(exc))
        assert _SENTINEL not in capture.text


class TestLoggingMixinFailureSink:
    """Driven through the REAL ``_log_failure`` the mixin installs.

    The mixin is applied to a real agent object and the wrapped ``run`` is
    invoked; only the agent's body is a stub, because the code under test is
    the wrapper, not what it wraps.
    """

    def test_agent_failure_does_not_leak_on_any_of_the_three_surfaces(self, capture):
        from kaizen.core.mixins.logging_mixin import LoggingMixin

        class _Agent:
            def run(self, **kwargs):
                raise _chained_exception()

        agent = _Agent()
        # The REAL wrapper installation -- `apply` creates the logger and
        # replaces `run` with the wrapped form carrying the sink under test.
        LoggingMixin.apply(agent)

        with pytest.raises(RuntimeError):
            agent.run(prompt="x")

        assert (
            "Execution failed" in capture.text
        ), "the failure sink never fired; this test would pass vacuously"
        # Surfaces 1 (message), 2 (error_message field) and 3 (traceback) are
        # all inside `capture.text` by construction of _RenderingCapture.
        assert _SENTINEL not in capture.text, capture.text
        # The diagnostic that is NOT the exception is deliberately retained.
        assert "RuntimeError" in capture.text


class TestCanonicalAuditForwardSinks:
    """Both audit forwards, driven through their REAL append paths."""

    def test_security_audit_forward_failure_is_scrubbed(self, capture):
        from kaizen.security.audit import AuditTrailProvider

        class _ExplodingStore:
            def append_sync(self, **kwargs):
                raise _chained_exception()

        # Real constructor, real log_event; only the canonical store -- a
        # COLLABORATOR -- is the stub, and its failure is the path under test.
        auditor = AuditTrailProvider(
            storage="memory", canonical_store=_ExplodingStore()
        )
        auditor.log_event(user="u", action="a", result="ok")

        assert (
            "audit.canonical_forward_failed" in capture.text
        ), "the forward sink never fired; this test would pass vacuously"
        assert _SENTINEL not in capture.text, capture.text
        # The replacement diagnostic is present -- dropping exc_info must not
        # trade the leak for a blind spot.
        assert "RuntimeError" in capture.text
