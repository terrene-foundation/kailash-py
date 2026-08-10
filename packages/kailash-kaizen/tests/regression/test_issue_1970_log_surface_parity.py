"""#1970 follow-up — the LOG surface must be sanitized, not just the RAISE surface.

Found by the holistic redteam's security lens after the #1970 sweep landed.

The sweep sanitized the *raised* message at several sites but left a
``logger.exception(...)`` on the SAME exception object untouched. Two things make
that a real leak rather than a cosmetic gap:

1. ``logger.exception`` emits ``exc_info``, and the traceback's final line is the
   unmodified ``str(exc)``. Sanitizing the raised message while keeping
   ``exc_info`` re-admits the credential through the back door.
2. At ``TraceExporter`` the raise is gated on ``raise_on_error``, which is
   ``False`` at all three constructors. The sanitizer therefore lived on the
   branch that does NOT run for the default configuration, while the log — which
   runs on EVERY sink error — carried the raw text.

The pre-existing test for that site passed ``raise_on_error=True``, exercising
precisely the branch that was already safe; that is why a green suite hid this.
These tests pin the DEFAULT path.

Per ``observability.md`` Rule 6.3: when a value is masked for one surface it MUST
be masked at EVERY surface (log line, metric label, exception message, diagnostic
return).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.regression

# Obviously-synthetic credential embedded in a DSN — the sanitizer's
# ``_URL_WITH_AUTH`` rule is what must claim it.
_SECRET = "hunter2"  # noqa: S105 - synthetic test vector
_RAW = f"sink push failed: postgres://svc:{_SECRET}@obs.internal:5432/telemetry"


class _CapturingHandler(logging.Handler):
    """Collects records so the test can inspect fields AND ``exc_info``."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        self.records.append(record)


def _assert_no_leak(records: list[logging.LogRecord]) -> None:
    """The secret must appear in NO field of ANY record, including the traceback."""
    for record in records:
        blob = "".join(
            (
                record.getMessage() or "",
                repr(getattr(record, "error", "")),
                repr(record.exc_info),
                repr(record.exc_text),
            )
        )
        assert _SECRET not in blob, (
            f"credential leaked via log record {record.name}: "
            f"msg={record.getMessage()!r} error={getattr(record, 'error', None)!r} "
            f"exc_info_present={bool(record.exc_info)}"
        )


def _attach(logger_name: str) -> tuple[logging.Logger, _CapturingHandler]:
    logger = logging.getLogger(logger_name)
    handler = _CapturingHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger, handler


def test_trace_exporter_default_path_log_is_sanitized():
    """``raise_on_error`` defaults to False — the LOG is the surface that fires.

    Before the fix this logged the raw DSN via ``logger.exception``'s traceback
    while the sanitizer sat on the un-taken raise branch.
    """
    from kailash.diagnostics.protocols import TraceEvent, TraceEventType
    from kaizen.observability.trace_exporter import TraceExporter

    def _boom_sink(event, fingerprint):
        raise RuntimeError(_RAW)

    exporter = TraceExporter(sink=_boom_sink)  # raise_on_error defaults to False
    event = TraceEvent(
        event_id="ev-1970-log",
        event_type=TraceEventType.AGENT_RUN_START,
        timestamp=datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc),
        run_id="run-1970-log",
        agent_id="agent-1970-log",
        cost_microdollars=0,
    )

    logger, handler = _attach("kaizen.observability.trace_exporter")
    try:
        # Must NOT raise — this is the default, swallow-and-log configuration.
        exporter.export(event)
    finally:
        logger.removeHandler(handler)

    assert handler.records, "the sink error produced no log record at all"
    _assert_no_leak(handler.records)
    # exc_info would re-admit the raw message through the traceback.
    assert not any(r.exc_info for r in handler.records), (
        "logger.exception/exc_info reintroduces the raw exception text; the "
        "sanitized `error` field is defeated by the traceback's final line"
    )


def test_web_fetch_http_error_arm_is_sanitized():
    """`fetch_url`'s `except HTTPError` arm — the one the other tests never reach.

    `HTTPError` SUBCLASSES `URLError`, so it is caught by the FIRST arm and never
    falls through to the sanitized `URLError` handler. The existing coverage
    missed this two ways: the sweep test raises a plain exception (landing in the
    generic `except Exception` arm), and the structural test only greps the file
    for the string ``sanitize_provider_error``, which the other two arms satisfy.
    Reverting this arm therefore left the whole suite green while
    ``HTTP Error 401: Unauthorized for postgres://admin:hunter2@…`` leaked.

    Asserts on the real handler by raising a genuine `HTTPError` whose `reason`
    carries a credential — the only shape that exercises this arm.
    """
    from urllib.error import HTTPError

    from kaizen.mcp.builtin_server.tools import web

    secret = "hunter2"  # noqa: S105 - synthetic
    reason = f"Unauthorized for postgres://admin:{secret}@db.internal:5432/app"

    def _raise_http_error(*_a, **_k):
        raise HTTPError("https://api.example.com/v1", 401, reason, {}, None)

    # `web.py` calls `urllib_request.urlopen(...)`, so THAT is the patch target.
    # An earlier revision patched `web.urlopen`, which does not exist — and a
    # `pytest.skip` guard swallowed the mismatch, so the test reported as a SKIP
    # while appearing to be coverage. No guard here: if the attribute moves, this
    # fails loudly rather than silently opting out.
    import asyncio

    original = web.urllib_request.urlopen
    web.urllib_request.urlopen = _raise_http_error  # type: ignore[attr-defined]
    try:
        # `fetch_url` is async — calling it without awaiting returns a coroutine
        # and every assertion below would pass vacuously on the coroutine object.
        result = asyncio.run(web.fetch_url("https://api.example.com/v1"))
    finally:
        web.urllib_request.urlopen = original  # type: ignore[attr-defined]

    assert isinstance(result, dict), f"expected a result dict, got {type(result)}"

    assert result["success"] is False
    assert secret not in str(result), (
        "the HTTPError arm returned the raw reason — a credential embedded in "
        f"an upstream 401 reached the MCP client: {result!r}"
    )
    assert "[REDACTED]" in result["error"]


@pytest.mark.parametrize(
    ("helper", "getter", "event", "kwargs"),
    [
        (
            "llm_text_similarity",
            "get_text_similarity_agent",
            "llm_text_similarity.error",
            {"text_a": "a", "text_b": "b"},
        ),
        (
            "llm_capability_match",
            "get_capability_match_agent",
            "llm_capability_match.error",
            {
                "capability_name": "python",
                "capability_description": "writes python",
                "requirement": "build an API",
            },
        ),
    ],
)
def test_reasoning_helper_error_log_is_sanitized(
    monkeypatch, helper, getter, event, kwargs
):
    """``agent.run`` IS the provider dispatch — its exception carries auth text.

    Two surfaces leaked here before the fix: the explicit ``error`` field (raw
    ``str(exc)``) AND ``logger.exception``'s traceback. #1981 rewrote the
    ``.degraded`` WARN a few lines below each of these and left the ``.error``
    sibling untouched — a multi-site sweep gap (``security.md`` § Multi-Site
    Kwarg Plumbing).
    """
    import kaizen.llm.reasoning as reasoning
    from kaizen.core.base_agent import BaseAgentConfig

    class _BoomAgent:
        def run(self, **_kw):
            raise RuntimeError(_RAW)

    monkeypatch.setattr(reasoning, getter, lambda cfg: _BoomAgent())
    config = BaseAgentConfig(llm_provider="mock", model="mock-model")

    logger, handler = _attach("kaizen.llm.reasoning")
    try:
        with pytest.raises(RuntimeError):
            getattr(reasoning, helper)(config=config, **kwargs)
    finally:
        logger.removeHandler(handler)

    error_records = [r for r in handler.records if r.getMessage() == event]
    assert error_records, f"no {event} record was emitted"
    _assert_no_leak(handler.records)
    assert not any(r.exc_info for r in error_records), (
        f"{event} still carries exc_info; the traceback re-leaks the raw "
        "provider message the `error` field no longer contains"
    )
    # The field must still be present and informative — sanitized, not dropped.
    sanitized = getattr(error_records[0], "error", "")
    assert (
        "[REDACTED]" in sanitized
    ), f"expected a redacted marker in the sanitized error field, got {sanitized!r}"
