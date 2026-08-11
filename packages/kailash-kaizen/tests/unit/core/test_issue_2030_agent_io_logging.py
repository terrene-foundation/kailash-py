"""Regression: BaseAgent MUST NOT log agent I/O values at INFO (#2030).

`BaseAgent._pre_execution_hook` / `_post_execution_hook` rendered the WHOLE
inputs and result dicts into an INFO message, gated only by `logging_enabled`
which defaults True. `_handle_error` additionally passed the caller-supplied
context — which `agent_loop` populates as ``{"inputs": inputs}`` — straight
into ``logger.error(..., extra=context)``, putting the full inputs on the
LogRecord at ERROR, a level that survives every production log configuration.

Agent I/O routinely carries user prompts, retrieved documents, PII and (for
agents that take credentials as parameters) secrets.

BOTH POLARITIES ARE PINNED, per the redaction-test contract:
  * POSITIVE — credential-shaped and PII-shaped VALUES must be absent.
  * NEGATIVE — the structured metadata that makes the log useful (signature
    name, input/result KEY names, counts, the error message and type) must be
    PRESERVED. A fix that simply deletes the log statements would pass the
    positive half alone; the negative controls are what forbid it.

Rendering surface note (this is what makes the instrument discriminating):
``_rendered()`` reads the formatted message AND every ``extra=`` attribute on
the record. A test that read only ``record.getMessage()`` would report GREEN
while ``extra=context`` still leaked the full inputs — structured handlers
(python-json-logger, structlog, OTel log export) all render record attributes.
"""

from __future__ import annotations

import logging

import pytest

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

LOGGER_NAME = "kaizen.core.base_agent"

# A credential SHAPE the scrubber is expected to claim.
SECRET = "sk-ant-api03-EXAMPLEDONOTLOGabcdef0123456789ABCDEF"
# A PII-shaped value carrying no credential prefix — the scrubber does NOT
# claim this, so only the level/opt-in gate can protect it. That asymmetry is
# deliberate and is asserted explicitly in the DEBUG tests below.
PII = "patient Jane Roe, MRN 4417829, dob 1961-03-02"

_BASE_RECORD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def _rendered(records) -> str:
    """Everything a handler could emit: message text PLUS ``extra=`` attrs."""
    parts: list[str] = []
    for record in records:
        parts.append(record.getMessage())
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _BASE_RECORD_ATTRS
        }
        if extras:
            parts.append(repr(extras))
    return "\n".join(parts)


def _agent(**config_kwargs) -> BaseAgent:
    # mcp_servers=[] is REQUIRED, not incidental: passing None (the default)
    # auto-injects the builtin MCP server config and constructs an MCPClient
    # per agent, which spawns `python -m kaizen.mcp.builtin_server`. Harmless
    # in a small local run; in CI's single-process 6600-test suite it
    # accumulated into a MemoryError, an orphaned python process and a job
    # timeout. Every other BaseAgent unit test in this package passes [].
    return BaseAgent(
        config=BaseAgentConfig(llm_provider="mock", **config_kwargs),
        mcp_servers=[],
    )


class TestPreExecutionHookInfoLevel:
    """Inputs are summarized at INFO, never rendered."""

    def test_input_values_absent_at_info(self, caplog):
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._pre_execution_hook({"question": PII, "api_key": SECRET})

        text = _rendered(caplog.records)
        assert SECRET not in text, "credential value leaked at INFO"
        assert PII not in text, "PII value leaked at INFO"

    def test_structured_metadata_preserved_at_info(self, caplog):
        """NEGATIVE CONTROL — deleting the log entirely must NOT pass."""
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._pre_execution_hook({"question": PII, "api_key": SECRET})

        text = _rendered(caplog.records)
        assert caplog.records, "pre-execution INFO record disappeared entirely"
        assert "question" in text, "input key names must survive for diagnosis"
        assert "api_key" in text, "input key names must survive for diagnosis"

    def test_hook_still_returns_inputs_unchanged(self):
        """The hook is on the hot path — it must stay a pass-through."""
        agent = _agent()
        inputs = {"question": PII, "api_key": SECRET}
        assert agent._pre_execution_hook(inputs) == inputs


class TestPostExecutionHookInfoLevel:
    """Results are summarized at INFO, never rendered."""

    def test_result_values_absent_at_info(self, caplog):
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._post_execution_hook({"answer": PII, "token": SECRET})

        text = _rendered(caplog.records)
        assert SECRET not in text, "credential value leaked at INFO"
        assert PII not in text, "PII value leaked at INFO"

    def test_structured_metadata_preserved_at_info(self, caplog):
        """NEGATIVE CONTROL."""
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._post_execution_hook({"answer": PII, "token": SECRET})

        text = _rendered(caplog.records)
        assert caplog.records, "post-execution INFO record disappeared entirely"
        assert "answer" in text, "result key names must survive for diagnosis"
        assert "token" in text, "result key names must survive for diagnosis"

    def test_hook_still_returns_result_unchanged(self):
        agent = _agent()
        result = {"answer": PII, "token": SECRET}
        assert agent._post_execution_hook(result) == result


class TestHandleErrorDoesNotLeakContext:
    """``extra=context`` carried the full inputs onto the record at ERROR.

    This is the site CodeQL #11244 flagged and the issue dismissed as a
    harmless generic pass-through. It is not harmless: `agent_loop` calls it
    as ``_handle_error(error, {"inputs": inputs})``.
    """

    def test_inputs_absent_from_error_record(self, caplog):
        agent = _agent()
        with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
            agent._handle_error(
                RuntimeError("boom"),
                {"inputs": {"question": PII, "api_key": SECRET}},
            )

        text = _rendered(caplog.records)
        assert SECRET not in text, "credential leaked via extra= at ERROR"
        assert PII not in text, "PII leaked via extra= at ERROR"

    def test_error_message_and_keys_preserved(self, caplog):
        """NEGATIVE CONTROL — the diagnostic payload must survive."""
        agent = _agent()
        with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
            agent._handle_error(
                RuntimeError("boom"),
                {"inputs": {"question": PII, "api_key": SECRET}},
            )

        text = _rendered(caplog.records)
        assert caplog.records, "error record disappeared entirely"
        assert "boom" in text, "error message must survive"
        assert "question" in text, "input key names must survive for diagnosis"

    def test_return_shape_unchanged(self):
        """Backward compat: non-configuration errors still return the dict."""
        agent = _agent()
        out = agent._handle_error(RuntimeError("boom"), {"inputs": {}})
        assert out["success"] is False
        assert out["type"] == "RuntimeError"
        assert "boom" in out["error"]


class TestFullPayloadIsOptInAndScrubbed:
    """Full payloads are DEBUG **and** opt-in, per security.md § Secure-Default.

    Merely turning DEBUG on globally — extremely common in incident response —
    must not start dumping user data. The payload dump requires an explicit
    ``log_full_payloads=True``.
    """

    def test_debug_alone_does_not_dump_payloads(self, caplog):
        agent = _agent()  # log_full_payloads defaults False
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            agent._pre_execution_hook({"question": PII, "api_key": SECRET})
            agent._post_execution_hook({"answer": PII})

        text = _rendered(caplog.records)
        assert SECRET not in text, "DEBUG alone must not dump payloads"
        assert PII not in text, "DEBUG alone must not dump payloads"

    def test_opt_in_payload_is_credential_scrubbed(self, caplog):
        """Opt-in DEBUG dump still routes through the credential scrubber."""
        agent = _agent(log_full_payloads=True)
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            agent._pre_execution_hook({"question": PII, "api_key": SECRET})

        text = _rendered(caplog.records)
        assert SECRET not in text, "opt-in dump must still scrub credentials"
        # Honest contract, asserted rather than glossed: the scrubber claims
        # credential SHAPES, not arbitrary PII. The opt-in flag is what
        # protects PII — which is exactly why the flag defaults to False.
        assert PII in text, "opt-in dump is expected to render non-credential values"

    def test_opt_in_payload_absent_at_info(self, caplog):
        """Even opted in, the payload never appears at INFO."""
        agent = _agent(log_full_payloads=True)
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._pre_execution_hook({"question": PII, "api_key": SECRET})

        text = _rendered(caplog.records)
        assert PII not in text
        assert SECRET not in text


class TestResultKeyNamesAreBoundedAndScrubbed:
    """Result keys can be MODEL-controlled, so key names are not automatically safe.

    A strategy returns the model's parsed JSON verbatim when no signature field
    matches, and ``_validate_signature_output`` returns early on a ``response``
    key without inspecting the others. So a prompt-injected model can choose the
    key names that reach INFO.
    """

    def test_credential_shaped_key_name_is_scrubbed(self, caplog):
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._post_execution_hook({"response": "ok", SECRET: "value"})

        text = _rendered(caplog.records)
        assert SECRET not in text, "a credential-shaped KEY leaked at INFO"

    def test_key_count_is_capped(self, caplog):
        """A model returning thousands of keys must not amplify the log."""
        from kaizen.core._log_hygiene import MAX_SUMMARY_KEYS

        payload = {f"k{i:05d}": i for i in range(MAX_SUMMARY_KEYS + 500)}
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._post_execution_hook(payload)

        text = _rendered(caplog.records)
        assert "more" in text, "elision marker missing"
        assert f"k{MAX_SUMMARY_KEYS + 499:05d}" not in text, "cap not applied"
        # NEGATIVE CONTROL — the true total must still be reported.
        assert str(MAX_SUMMARY_KEYS + 500) in text, "true key count must survive"

    def test_long_key_is_truncated(self, caplog):
        from kaizen.core._log_hygiene import MAX_SUMMARY_KEY_LEN

        long_key = "z" * (MAX_SUMMARY_KEY_LEN * 4)
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._post_execution_hook({long_key: 1})

        text = _rendered(caplog.records)
        assert long_key not in text, "over-long key emitted in full"

    def test_nested_values_are_never_descended_into(self, caplog):
        agent = _agent()
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            agent._post_execution_hook({"outer": {"inner": SECRET}})

        text = _rendered(caplog.records)
        assert SECRET not in text
        assert "outer" in text, "top-level key must still be reported"


class TestLoggingDisabledStillSilent:
    """``logging_enabled=False`` remains a full opt-out (backward compat)."""

    @pytest.mark.parametrize(
        "hook,payload",
        [
            ("_pre_execution_hook", {"question": PII}),
            ("_post_execution_hook", {"answer": PII}),
        ],
    )
    def test_no_records_when_disabled(self, caplog, hook, payload):
        agent = _agent(logging_enabled=False)
        # Construction emits unrelated MCP DEBUG records on the same logger;
        # scope the assertion to the hook call itself.
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            getattr(agent, hook)(payload)

        assert not [r for r in caplog.records if r.name == LOGGER_NAME]
