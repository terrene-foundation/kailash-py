# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""a2a's degraded-path WARN sinks MUST NOT log a raw provider exception.

Four sinks in ``kaizen/nodes/ai/a2a.py`` wrapped ``super().run(...)`` -- the
LLM provider dispatch -- in a broad ``except Exception as exc`` and put
``str(exc)`` straight into the log record::

    logger.warning("a2a.summarize.llm_failed", extra={..., "error": str(exc)})

Reachable because ``LLMAgentNode._on_error_hook``'s default body is a bare
``raise error`` (``llm_agent.py``), so any exception raised outside
``_provider_llm_response``'s sanitizing wrapper leaves ``run()`` RAW. A
provider auth failure names the endpoint it could not authenticate against,
credentials included.

The SIBLING branch twenty lines above each sink was already safe for the
opposite reason -- it reads the result dict's ``error``, which ``LLMAgentNode``
has already sanitized -- so the exception branch was contradicting the success
branch in the same function.

Asserted on the RENDERED record (``logging.Formatter().format(record)``), not
on ``record.msg``: these sinks pass the payload through ``extra=``, and a
future regression that re-added ``exc_info`` would re-leak via the traceback's
final line while leaving ``msg`` clean. The rendered form is the only view that
sees every surface at once.

The sentinel below is synthetic (RFC 2606 ``.invalid`` TLD, self-describing
value). It is not a credential; it is a string with the SHAPE the scrubber
keys on, so it exercises the same branch a real one would.
"""

import logging

import pytest

from kaizen.nodes.ai import llm_agent
from kaizen.nodes.ai.a2a import A2AAgentNode

pytestmark = pytest.mark.regression

# Synthetic. URL-userinfo shape is what `scrub_credentials` keys on.
_SENTINEL = "SYNTHETIC-NOT-A-REAL-CREDENTIAL-a2a"
_LEAKY_URL = f"https://svc:{_SENTINEL}@api.example.invalid/v1/chat"


class _Capture(logging.Handler):
    """Collects records AND their fully rendered form."""

    def __init__(self):
        super().__init__()
        self.records = []
        self._fmt = logging.Formatter("%(levelname)s %(message)s")

    def emit(self, record):
        # Render eagerly: exc_info is resolved at format time, and the
        # traceback is exactly the surface a message-only assertion misses.
        extras = " ".join(
            f"{k}={v!r}"
            for k, v in vars(record).items()
            if k not in logging.LogRecord("", 0, "", 0, "", None, None).__dict__
        )
        self.records.append(f"{self._fmt.format(record)} {extras}")


@pytest.fixture
def captured_a2a_logs():
    handler = _Capture()
    logger = logging.getLogger("kaizen.nodes.ai.a2a")
    prior_level, prior_propagate = logger.level, logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)
        logger.propagate = prior_propagate


@pytest.fixture
def raising_provider():
    """Make the REAL ``super().run()`` raise a credential-bearing exception.

    This is the escape ``_on_error_hook``'s default ``raise error`` produces
    for anything raised outside ``_provider_llm_response``'s wrapper -- the
    path that made these sinks reachable in the first place.
    """
    original = llm_agent.LLMAgentNode.run

    def _raise(self, **kwargs):
        raise ConnectionError(f"connection refused talking to {_LEAKY_URL}")

    llm_agent.LLMAgentNode.run = _raise
    try:
        yield
    finally:
        llm_agent.LLMAgentNode.run = original


def _node() -> A2AAgentNode:
    node = A2AAgentNode()
    # Deliberately NOT a real provider/model pair: no completion is ever
    # issued here (the dispatch is forced to raise), and these values only
    # ever appear as log-record labels. A real model string would be a
    # hardcoded model name for no behavioural gain (rules/env-models.md).
    node._current_provider = "provider-under-test"
    node._current_model = "model-under-test"
    return node


def _assert_ran_then_clean(handler, expected_event: str):
    """Non-vacuity first, then the security assertion.

    Falsifying result: with the raw ``str(exc)`` restored, the rendered record
    contains ``_SENTINEL`` and the second assertion fails. If the degraded path
    never ran at all, the FIRST assertion fails -- so a green here cannot come
    from an unexercised code path.
    """
    rendered = "\n".join(handler.records)
    assert expected_event in rendered, (
        f"the degraded path never emitted {expected_event!r}; the test proves "
        f"nothing about scrubbing. Records: {handler.records}"
    )
    assert _SENTINEL not in rendered, (
        f"raw provider exception reached the log surface at {expected_event!r}: "
        f"{rendered}"
    )


class TestA2ADegradedWarnSinksAreScrubbed:
    def test_summarize_llm_failed_does_not_log_the_raw_exception(
        self, captured_a2a_logs, raising_provider
    ):
        out = _node()._summarize_with_llm(
            [{"agent_id": "a1", "content": "x", "importance": 0.9}]
        )
        # The degraded fallback still returns a usable summary -- the point of
        # the WARN (not ERROR) level at this sink.
        assert out
        _assert_ran_then_clean(captured_a2a_logs, "a2a.summarize.llm_failed")

    @pytest.mark.parametrize(
        "method, first_arg, event",
        [
            (
                "_stage1_primary_extraction",
                "some model response text",
                "a2a.stage1_primary_extraction.failed",
            ),
            (
                "_stage3_quality_enhancement",
                # stage3 early-returns on an empty list, so it must be non-empty
                # for the dispatch -- and therefore the sink -- to be reached.
                # ``confidence`` is required: the prompt is built BEFORE the
                # try, so an incomplete insight raises past the sink instead of
                # into it, and the test would pass without exercising anything.
                [{"content": "x", "importance": 0.9, "confidence": 0.8}],
                "a2a.stage3_quality_enhancement.failed",
            ),
            (
                "_stage6_meta_insight_synthesis",
                # stage6 early-returns below three insights; same reasoning.
                [
                    {"content": f"x{i}", "importance": 0.9, "confidence": 0.8}
                    for i in range(3)
                ],
                "a2a.stage6_meta_synthesis.failed",
            ),
        ],
    )
    def test_multi_stage_pipeline_sinks_do_not_log_the_raw_exception(
        self, captured_a2a_logs, raising_provider, method, first_arg, event
    ):
        """The three pipeline stages share the sink shape; all three or none.

        Fixed in lockstep deliberately -- a per-stage fix is how one stage
        silently keeps the leak (security.md, Multi-Site Kwarg Plumbing).
        """
        fn = getattr(_node(), method)
        fn(first_arg, "analyst", {})
        _assert_ran_then_clean(captured_a2a_logs, event)


class TestNarrowJsonSinksAreDeliberatelyUnchanged:
    """Pins the verdict that the narrow parse sinks were NOT part of the bug.

    ``except (json.JSONDecodeError, ValueError)`` inside each stage wraps
    ``json.loads`` of the MODEL's own output, never ``super().run()``, so it
    cannot observe a provider auth error -- and a ``JSONDecodeError`` message
    carries a parse POSITION, never the document. Recorded as a test so a
    later sweep does not "fix" them on pattern-match alone and lose the
    payload-position diagnostic for nothing.
    """

    def test_jsondecodeerror_message_carries_position_not_payload(self):
        import json

        with pytest.raises(json.JSONDecodeError) as exc_info:
            json.loads(f'{{"k": "{_SENTINEL}"')
        assert _SENTINEL not in str(exc_info.value)
        assert "line 1" in str(exc_info.value)
